import {
  CHANNELS,
  SAMPLE_RATE,
  type AcousticMetrics,
  type EnvelopeConfig,
  type FilterConfig,
  type Layer,
  type OscillatorLayer,
  type SoundGraph,
} from "./types.js";

const TWO_PI = Math.PI * 2;
const MIN_DB = -96;

/** Deterministic 32-bit PRNG (Mulberry32). Identical across Node and browsers. */
export function createPrng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function createGaussianNoise(seed: number): () => number {
  const next = createPrng(seed);
  let spare: number | null = null;
  return () => {
    if (spare !== null) {
      const value = spare;
      spare = null;
      return value;
    }
    const u1 = Math.max(1e-7, next());
    const u2 = next();
    const r = Math.sqrt(-2 * Math.log(u1));
    const theta = TWO_PI * u2;
    spare = r * Math.sin(theta);
    return r * Math.cos(theta);
  };
}

/** Kellet's seven-state approximation and leaky integration both start from silence. */
export function createNoise(color: "white" | "pink" | "brown", seed: number): () => number {
  const white = createGaussianNoise(seed);
  if (color === "white") return white;
  if (color === "brown") {
    let memory = 0;
    const leak = Math.exp(-TWO_PI * 12 / SAMPLE_RATE);
    return () => (memory = leak * memory + 0.065 * white());
  }

  // Poles and feed coefficients of the Kellet pinking filter.
  const poles = [0.99886, 0.99332, 0.969, 0.8665, 0.55, -0.7616];
  const feeds = [0.0555179, 0.0750759, 0.153852, 0.3104856, 0.5329522, -0.016898];
  const memory = new Float64Array(poles.length);
  let delayed = 0;
  return () => {
    const x = white();
    let y = 0.5362 * x + delayed;
    for (let j = 0; j < poles.length; j++) {
      memory[j] = poles[j] * memory[j] + feeds[j] * x;
      y += memory[j];
    }
    delayed = 0.115926 * x;
    return y * 0.24;
  };
}

class BiquadFilter {
  private z1 = 0;
  private z2 = 0;

  constructor(
    private b0 = 1, private b1 = 0, private b2 = 0,
    private a1 = 0, private a2 = 0,
  ) {}

  configure(kind: FilterConfig["kind"], frequency: number, q: number, gainDb = 0): void {
    const omega = TWO_PI * Math.max(1, Math.min(SAMPLE_RATE * 0.48, frequency)) / SAMPLE_RATE;
    const cosine = Math.cos(omega);
    const alpha = Math.sin(omega) / (2 * Math.max(0.2, Math.min(20, q)));
    const a = kind === "peaking" ? 10 ** (gainDb / 40) : 1;
    const a0 = 1 + alpha / a;
    this.a1 = -2 * cosine / a0;
    this.a2 = (1 - alpha / a) / a0;
    switch (kind) {
      case "highpass":
      case "lowpass": {
        const sign = kind === "lowpass" ? 1 : -1;
        this.b0 = this.b2 = (1 - sign * cosine) / (2 * a0);
        this.b1 = sign * 2 * this.b0;
        break;
      }
      case "bandpass":
        this.b0 = alpha / a0;
        this.b1 = 0;
        this.b2 = -this.b0;
        break;
      case "notch":
      case "peaking": {
        const boost = kind === "peaking" ? alpha * a : 0;
        this.b0 = (1 + boost) / a0;
        this.b1 = this.a1;
        this.b2 = (1 - boost) / a0;
        break;
      }
    }
  }

  process(x: number): number {
    const y = this.b0 * x + this.z1;
    this.z1 = this.b1 * x - this.a1 * y + this.z2;
    this.z2 = this.b2 * x - this.a2 * y;
    return y;
  }
}

function evalEnvelope(env: EnvelopeConfig, t: number, duration: number): number {
  if (t <= 0 || t >= duration) return 0;
  const u = t / duration;
  if (env.bellPower !== undefined) return Math.sin(Math.PI * u) ** env.bellPower;
  const release = Math.min(1, (duration - t) / Math.max(0.4, env.releaseMs ?? 12));
  const fade = Math.sin(Math.PI * release / 2) ** (env.releaseCurve ?? 2);
  if (env.risePower !== undefined) return u ** env.risePower * fade;

  const attack = Math.max(0.4, env.attackMs);
  const rise = env.riseMs ?? 0;
  const shoulder = rise > 0 ? 0.65 : 1;
  let level = 1;
  if (t < attack) {
    level = shoulder * (t / attack) ** (env.attackCurve ?? 1);
  } else if (t < attack + rise) {
    level = shoulder + (1 - shoulder) * ((t - attack) / rise) ** (env.riseCurve ?? 1);
  } else {
    const elapsed = Math.max(0, t - attack - rise - (env.holdMs ?? 0));
    const sustain = env.sustain ?? 0;
    level = sustain + (1 - sustain) * Math.exp(-((elapsed / Math.max(0.4, env.decayMs ?? duration)) ** (env.decayCurve ?? 1)));
  }
  return level * fade;
}

function polyBlep(phase: number, step: number): number {
  if (phase < step) return -((1 - phase / step) ** 2);
  if (phase > 1 - step) return ((phase - 1) / step + 1) ** 2;
  return 0;
}

export function oscillatorSample(wave: OscillatorLayer["waveform"], phase: number, step: number): number {
  switch (wave) {
    case "sine": return Math.sin(TWO_PI * phase);
    case "triangle": return 1 - 4 * Math.abs(phase - 0.5);
    case "sawtooth": return 2 * phase - 1 - polyBlep(phase, step);
    case "square":
      return (phase < 0.5 ? 1 : -1) + polyBlep(phase, step) - polyBlep((phase + 0.5) % 1, step);
  }
}

function renderLayer(
  layer: Layer, left: Float32Array, right: Float32Array, seed: number,
): void {
  const start = Math.max(0, Math.round((layer.startMs ?? 0) * SAMPLE_RATE / 1000));
  const count = Math.min(left.length - start, Math.round((layer.durationMs ?? Infinity) * SAMPLE_RATE / 1000));
  if (count < 2) return;
  const duration = (count - 1) * 1000 / SAMPLE_RATE;
  const osc = layer.kind === "oscillator" ? layer : undefined;
  const noise = layer.kind === "noise" ? createNoise(layer.color ?? "white", seed) : undefined;
  const voices = Math.min(8, Math.max(1, Math.round(osc?.voices ?? 1)));
  const cfg = layer.filter;
  const panStart = layer.pan?.start ?? 0;
  const panEnd = layer.pan?.end ?? panStart;
  for (let voice = 0; voice < voices; voice++) {
    const position = voices === 1 ? 0 : 2 * voice / (voices - 1) - 1;
    const ratio = 2 ** (position * (osc?.detune ?? 0) / 1200);
    let phase = 0;
    const filter = cfg ? new BiquadFilter() : undefined;
    for (let i = 0; i < count; i++) {
      const u = i / (count - 1);
      const t = i * 1000 / SAMPLE_RATE;
      if (cfg && filter && (i === 0 || (cfg.freqEnd !== undefined && (i & 15) === 0))) {
        const freq = cfg.freqStart * ((cfg.freqEnd ?? cfg.freqStart) / cfg.freqStart) ** (u ** (cfg.curve ?? 1));
        filter.configure(cfg.kind, freq, cfg.q, cfg.gainDb);
      }
      let sample: number;
      if (osc) {
        const end = osc.freqEnd ?? osc.freqStart;
        const hz = osc.pitchDecayRate === undefined
          ? osc.freqStart * (end / osc.freqStart) ** (u ** (osc.curve ?? 1))
          : end + (osc.freqStart - end) * Math.exp(-osc.pitchDecayRate * t / 1000);
        const step = Math.min(0.48, Math.max(1e-9, hz * ratio / SAMPLE_RATE));
        sample = oscillatorSample(osc.waveform, phase, step);
        phase += step;
        if (phase >= 1) phase--;
      } else {
        sample = noise!();
      }
      if (filter) sample = filter.process(sample);
      const value = sample * evalEnvelope(layer.envelope, t, duration) * layer.gain / voices;
      const pan = Math.max(-1, Math.min(1, panStart + (panEnd - panStart) * u + position * 0.7));
      const angle = (pan + 1) * Math.PI / 4;
      left[start + i] += value * Math.cos(angle);
      right[start + i] += value * Math.sin(angle);
    }
  }
}

// Delay lengths in samples at 48 kHz. Distinct primes disperse coincident echoes.
const ROOM_DELAYS = [
  { comb: [1217, 1559, 1877, 2203], diffuse: [347, 193] },
  { comb: [1277, 1601, 1931, 2281], diffuse: [367, 211] },
] as const;

function reverberate(channel: Float32Array, side: 0 | 1, room: NonNullable<SoundGraph["reverb"]>): void {
  const delay = Math.max(0, Math.round(room.predelayMs * SAMPLE_RATE / 1000));
  const wet = new Float32Array(channel.length);
  const damping = 1 - Math.exp(-TWO_PI * Math.max(1, room.dampHz) / SAMPLE_RATE);
  for (const length of ROOM_DELAYS[side].comb) {
    const line = new Float32Array(length);
    const feedback = 0.001 ** (length / (SAMPLE_RATE * Math.max(0.01, room.decaySec)));
    let low = 0;
    for (let i = delay; i < wet.length; i++) {
      const j = (i - delay) % length;
      const echo = line[j];
      low += damping * (echo - low);
      line[j] = channel[i - delay] + feedback * low;
      wet[i] += echo * 0.25;
    }
  }
  for (const length of ROOM_DELAYS[side].diffuse) {
    const line = new Float32Array(length);
    for (let i = 0; i < wet.length; i++) {
      const j = i % length;
      const output = line[j] - 0.57 * wet[i];
      line[j] = wet[i] + 0.57 * output;
      wet[i] = output;
    }
  }
  const mix = Math.max(0, Math.min(1, room.mix));
  for (let i = 0; i < channel.length; i++) channel[i] += mix * (wet[i] - channel[i]);
}

// Four reconstruction phases, including the original samples. Each fractional
// phase has unit DC gain and a Blackman-windowed sinc interpolation kernel.
const TP_RADIUS = 12;
const TP_PHASES = [0.25, 0.5, 0.75].map(fraction => {
  const taps = Array.from({ length: 2 * TP_RADIUS }, (_, j) => {
    const x = j - TP_RADIUS + 1 - fraction;
    const a = Math.PI * x / TP_RADIUS;
    return Math.sin(Math.PI * x) / (Math.PI * x) * (0.42 + 0.5 * Math.cos(a) + 0.08 * Math.cos(2 * a));
  });
  const sum = taps.reduce((a, b) => a + b);
  return taps.map(tap => tap / sum);
});

const LIMITER_BLOCK = 96; // 2 ms of lookahead at 48 kHz

function measurePeaks(channel: Float32Array, blockPeaks?: Float64Array): number {
  const padded = new Float32Array(channel.length + 2 * TP_RADIUS);
  padded.set(channel, TP_RADIUS);
  let peak = 0;
  for (let i = 0; i <= channel.length; i++) {
    let local = Math.abs(padded[i + TP_RADIUS - 1]);
    for (const taps of TP_PHASES) {
      let value = 0;
      for (let j = 0; j < taps.length; j++) value += padded[i + j] * taps[j];
      local = Math.max(local, Math.abs(value));
    }
    peak = Math.max(peak, local);
    if (blockPeaks) {
      const block = Math.floor(Math.max(0, i - 1) / LIMITER_BLOCK);
      blockPeaks[block] = Math.max(blockPeaks[block], local);
    }
  }
  return peak;
}

// A finite cut through a bass cycle can retain a small mean even after the
// bus high-pass. Distribute that residual over a raised cosine whose endpoints
// are silent. Preserve predelay and return the corrected sample peak for trim.
function centerChannel(channel: Float32Array): number {
  let first = channel.length;
  let last = 0;
  let sum = 0;
  for (let i = 0; i < channel.length; i++) {
    if (channel[i] === 0) continue;
    first = Math.min(first, i);
    last = i;
    sum += channel[i];
  }
  const span = last - first;
  const correction = span > 1 ? sum / span : 0;
  let peak = 0;
  for (let i = first; i <= last; i++) {
    if (correction) channel[i] -= correction * (1 - Math.cos(TWO_PI * (i - first) / span));
    peak = Math.max(peak, Math.abs(channel[i]));
  }
  return peak;
}

function master(left: Float32Array, right: Float32Array): void {
  const peaks = new Float64Array(Math.ceil(left.length / LIMITER_BLOCK));
  const peak = Math.max(measurePeaks(left, peaks), measurePeaks(right, peaks));
  if (peak === 0) return;

  // Link both channels. In the top 4 dB the quadratic knee gradually
  // increases gain reduction; the loudest crest receives 2 dB of reduction.
  const gains = peaks.map(p => {
    const above = Math.max(0, 4 + 20 * Math.log10(p / peak));
    return 10 ** (-above * above / 160);
  });
  const recovery = 1 - Math.exp(-LIMITER_BLOCK / (SAMPLE_RATE * 0.035));
  let last = gains[0];
  for (let block = 0; block < gains.length; block++) {
    const goal = Math.min(gains[block], gains[block + 1] ?? 1);
    const end = goal < last ? goal : last + recovery * (goal - last);
    const start = block * LIMITER_BLOCK;
    for (let i = start; i < Math.min(start + LIMITER_BLOCK, left.length); i++) {
      const u = (i - start) / LIMITER_BLOCK;
      const gain = last + (end - last) * u * u * (3 - 2 * u);
      left[i] *= gain;
      right[i] *= gain;
    }
    last = end;
  }
  // Meet the mixer's sample-peak target while reserving reconstructed
  // headroom. Re-measure after time-varying gain, including between samples.
  const samplePeak = Math.max(centerChannel(left), centerChannel(right));
  const truePeak = Math.max(measurePeaks(left), measurePeaks(right));
  const trim = Math.min(10 ** (-2 / 20) / samplePeak, 10 ** (-1.75 / 20) / truePeak);
  for (let i = 0; i < left.length; i++) {
    left[i] *= trim;
    right[i] *= trim;
  }
}

export function renderGraph(graph: SoundGraph, seed: number): { left: Float32Array; right: Float32Array } {
  const totalSamples = Math.max(1, Math.round((graph.durationMs * SAMPLE_RATE) / 1000));
  const left = new Float32Array(totalSamples);
  const right = new Float32Array(totalSamples);

  for (let idx = 0; idx < graph.layers.length; idx++) {
    renderLayer(graph.layers[idx], left, right, (seed + Math.imul(idx + 1, 2654435761)) >>> 0);
  }

  if (graph.reflections && graph.reflections.amount > 0 && graph.reflections.taps.length > 0) {
    const dryL = new Float32Array(left);
    const dryR = new Float32Array(right);
    const amount = Math.max(0, Math.min(1, graph.reflections.amount));
    for (const tap of graph.reflections.taps) {
      const shift = Math.round((tap.delayMs * SAMPLE_RATE) / 1000);
      if (shift <= 0 || shift >= totalSamples) continue;
      const src = tap.channel === 0 ? dryL : dryR;
      const dst = tap.channel === 0 ? left : right;
      const g = tap.gain * amount;
      // Gentle one-pole damping so reflections sit behind the dry body
      let lp = 0;
      for (let i = shift; i < totalSamples; i++) {
        lp = lp + 0.35 * (src[i - shift] - lp);
        dst[i] += lp * g;
      }
    }
  }

  for (const [side, channel] of [left, right].entries()) {
    if (graph.reverb && graph.reverb.mix > 0) reverberate(channel, side === 0 ? 0 : 1, graph.reverb);
    const highpass = new BiquadFilter();
    highpass.configure("highpass", graph.highpass ?? 24, Math.SQRT1_2);
    const lowpass = graph.lowpass ? new BiquadFilter() : undefined;
    lowpass?.configure("lowpass", graph.lowpass!, Math.SQRT1_2);
    for (let i = 0; i < totalSamples; i++) {
      const high = highpass.process(channel[i]);
      channel[i] = lowpass ? lowpass.process(high) : high;
    }
  }
  const width = graph.width ?? 1;
  for (let i = 0; i < totalSamples; i++) {
    const mid = (left[i] + right[i]) * 0.5;
    const side = (left[i] - right[i]) * 0.5 * width;
    left[i] = mid + side;
    right[i] = mid - side;
  }

  // Smooth tail fade to prevent click at buffer end
  const fadeSamples = Math.min(totalSamples, Math.round(((graph.tailFadeMs ?? 6) * SAMPLE_RATE) / 1000));
  for (let i = 0; i < fadeSamples; i++) {
    const r = i / Math.max(1, fadeSamples);
    const gain = Math.sin((Math.PI / 2) * r) ** 2;
    const idx = totalSamples - 1 - i;
    left[idx] *= gain;
    right[idx] *= gain;
  }

  master(left, right);
  return { left, right };
}

/** Deterministic in-place radix-2 Cooley-Tukey FFT (power-of-two N). */
function fftRealMagnitude(signal: Float64Array): Float64Array {
  const n = signal.length;
  const re = new Float64Array(n);
  const im = new Float64Array(n);
  for (let i = 0; i < n; i++) re[i] = signal[i];

  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    while (j & bit) {
      j ^= bit;
      bit >>= 1;
    }
    j ^= bit;
    if (i < j) {
      const tr = re[i];
      re[i] = re[j];
      re[j] = tr;
    }
  }

  for (let len = 2; len <= n; len <<= 1) {
    const ang = -TWO_PI / len;
    const wlenRe = Math.cos(ang);
    const wlenIm = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let wRe = 1;
      let wIm = 0;
      const half = len >> 1;
      for (let j = 0; j < half; j++) {
        const uRe = re[i + j];
        const uIm = im[i + j];
        const vRe = re[i + j + half] * wRe - im[i + j + half] * wIm;
        const vIm = re[i + j + half] * wIm + im[i + j + half] * wRe;
        re[i + j] = uRe + vRe;
        im[i + j] = uIm + vIm;
        re[i + j + half] = uRe - vRe;
        im[i + j + half] = uIm - vIm;
        const nextWRe = wRe * wlenRe - wIm * wlenIm;
        wIm = wRe * wlenIm + wIm * wlenRe;
        wRe = nextWRe;
      }
    }
  }

  const bins = (n >> 1) + 1;
  const mag = new Float64Array(bins);
  for (let k = 0; k < bins; k++) {
    mag[k] = Math.hypot(re[k], im[k]);
  }
  return mag;
}

function toDbfs(linear: number): number {
  if (!Number.isFinite(linear) || linear <= 1e-6) return MIN_DB;
  return Math.round(20 * Math.log10(linear) * 100) / 100;
}

// BS.1770-4, Annex 1, Tables 1 and 2 (fixed 48 kHz). For SFX shorter
// than a gating block, measure the clip followed by silence up to 400 ms.
function integratedLufs(left: Float32Array, right: Float32Array): number {
  const hop = SAMPLE_RATE / 10;
  const hops = Math.max(4, Math.floor(left.length / hop));
  const energy = new Float64Array(hops);
  for (const channel of [left, right]) {
    const shelf = new BiquadFilter(1.53512485958697, -2.69169618940638, 1.19839281085285,
      -1.69065929318241, 0.73248077421585);
    const rlb = new BiquadFilter(1, -2, 1, -1.99004745483398, 0.99007225036621);
    for (let h = 0; h < hops; h++) {
      let sum = 0;
      for (let i = h * hop; i < (h + 1) * hop; i++) {
        const y = rlb.process(shelf.process(channel[i] ?? 0));
        sum += y * y;
      }
      energy[h] += sum / (4 * hop);
    }
  }
  const absoluteGate = 10 ** ((-70 + 0.691) / 10);
  const blocks: number[] = [];
  for (let h = 3; h < hops; h++) {
    const block = energy[h] + energy[h - 1] + energy[h - 2] + energy[h - 3];
    if (block > absoluteGate) blocks.push(block);
  }
  if (!blocks.length) return MIN_DB;
  const mean = (values: number[]) => values.reduce((a, b) => a + b, 0) / values.length;
  const relativeGate = mean(blocks) * 0.1;
  return Math.round(100 * (-0.691 + 10 * Math.log10(mean(blocks.filter(b => b > relativeGate))))) / 100;
}

export function analyzeAcoustics(left: Float32Array, right: Float32Array): AcousticMetrics {
  const totalSamples = left.length;
  const durationMs = Math.round((totalSamples * 1000) / SAMPLE_RATE);

  let maxAbs = 0;
  let sumSq = 0;
  for (let i = 0; i < totalSamples; i++) {
    const l = left[i];
    const r = right[i];
    const al = Math.abs(l);
    const ar = Math.abs(r);
    if (al > maxAbs) maxAbs = al;
    if (ar > maxAbs) maxAbs = ar;
    sumSq += 0.5 * (l * l + r * r);
  }
  const rms = Math.sqrt(sumSq / Math.max(1, totalSamples));

  // Peak energy offset computed over 5ms RMS windows for perceptually accurate sync cues
  const winSamples = Math.max(1, Math.round(SAMPLE_RATE * 0.005));
  const hopSamples = Math.max(1, Math.round(winSamples / 2));
  let bestEnergy = -1;
  let bestCenter = 0;
  for (let start = 0; start < totalSamples; start += hopSamples) {
    const end = Math.min(totalSamples, start + winSamples);
    let e = 0;
    for (let i = start; i < end; i++) {
      e += 0.5 * (left[i] ** 2 + right[i] ** 2);
    }
    e /= Math.max(1, end - start);
    if (e > bestEnergy) {
      bestEnergy = e;
      bestCenter = start + (end - start) / 2;
    }
  }
  const peakOffsetMs = Math.round((bestCenter * 1000) / SAMPLE_RATE);

  // Spectral centroid over energy-weighted 2048-sample Hann frames across the clip
  const fftSize = 2048;
  const hop = 1024;
  const frame = new Float64Array(fftSize);
  let weightedFreqSum = 0;
  let totalMagSum = 0;
  const numFrames = Math.max(1, Math.ceil(totalSamples / hop));
  for (let f = 0; f < numFrames; f++) {
    const offset = f * hop;
    let frameEnergy = 0;
    for (let i = 0; i < fftSize; i++) {
      const idx = offset + i;
      const mono = idx < totalSamples ? 0.5 * (left[idx] + right[idx]) : 0;
      const w = 0.5 * (1 - Math.cos((TWO_PI * i) / (fftSize - 1)));
      const windowed = mono * w;
      frame[i] = windowed;
      frameEnergy += windowed * windowed;
    }
    if (frameEnergy < 1e-10) continue;
    const mag = fftRealMagnitude(frame);
    for (let k = 1; k < mag.length; k++) {
      const freq = (k * SAMPLE_RATE) / fftSize;
      const weight = mag[k] * mag[k];
      weightedFreqSum += freq * weight;
      totalMagSum += weight;
    }
  }
  const spectralCentroidHz = totalMagSum > 0 ? Math.round(weightedFreqSum / totalMagSum) : 0;

  // 32-bar normalized waveform peaks for chat playback surface
  const bars = 32;
  const waveformPeaks: number[] = [];
  for (let b = 0; b < bars; b++) {
    const s = Math.floor((b * totalSamples) / bars);
    const e = Math.max(s + 1, Math.floor(((b + 1) * totalSamples) / bars));
    let barPeak = 0;
    for (let i = s; i < Math.min(e, totalSamples); i++) {
      const m = Math.max(Math.abs(left[i]), Math.abs(right[i]));
      if (m > barPeak) barPeak = m;
    }
    waveformPeaks.push(Math.round((maxAbs > 1e-6 ? barPeak / maxAbs : 0) * 1000) / 1000);
  }

  return {
    sample_rate: SAMPLE_RATE,
    channels: CHANNELS,
    duration_ms: durationMs,
    peak_offset_ms: peakOffsetMs,
    peak_dbfs: toDbfs(maxAbs),
    rms_dbfs: toDbfs(rms),
    lufs: integratedLufs(left, right),
    spectral_centroid_hz: spectralCentroidHz,
    waveform_peaks: waveformPeaks,
  };
}

export function encodeWavPcm16(left: Float32Array, right: Float32Array): Uint8Array {
  const numFrames = left.length;
  const blockAlign = CHANNELS * 2;
  const dataSize = numFrames * blockAlign;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };

  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, CHANNELS, true);
  view.setUint32(24, SAMPLE_RATE, true);
  view.setUint32(28, SAMPLE_RATE * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < numFrames; i++) {
    const l = Math.max(-1, Math.min(1, left[i]));
    const r = Math.max(-1, Math.min(1, right[i]));
    view.setInt16(offset, Math.round(l * 32767), true);
    view.setInt16(offset + 2, Math.round(r * 32767), true);
    offset += 4;
  }

  return new Uint8Array(buffer);
}
