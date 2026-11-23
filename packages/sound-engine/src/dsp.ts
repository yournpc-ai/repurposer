import {
  CHANNELS,
  SAMPLE_RATE,
  type AcousticMetrics,
  type EnvelopeConfig,
  type FilterConfig,
  type Layer,
  type PanConfig,
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

class BiquadFilter {
  private z1 = 0;
  private z2 = 0;
  private b0 = 1;
  private b1 = 0;
  private b2 = 0;
  private a1 = 0;
  private a2 = 0;

  configure(kind: FilterConfig["kind"], freqHz: number, q: number): void {
    const clampedFreq = Math.min(SAMPLE_RATE * 0.45, Math.max(20, freqHz));
    const clampedQ = Math.max(0.2, Math.min(20, q));
    const w0 = (TWO_PI * clampedFreq) / SAMPLE_RATE;
    const cosW0 = Math.cos(w0);
    const alpha = Math.sin(w0) / (2 * clampedQ);

    let b0: number;
    let b1: number;
    let b2: number;
    const a0 = 1 + alpha;
    const a1 = -2 * cosW0;
    const a2 = 1 - alpha;

    if (kind === "lowpass") {
      b0 = (1 - cosW0) / 2;
      b1 = 1 - cosW0;
      b2 = (1 - cosW0) / 2;
    } else if (kind === "highpass") {
      b0 = (1 + cosW0) / 2;
      b1 = -(1 + cosW0);
      b2 = (1 + cosW0) / 2;
    } else {
      // Constant-0-dB-peak bandpass (Audio EQ Cookbook)
      b0 = alpha;
      b1 = 0;
      b2 = -alpha;
    }

    this.b0 = b0 / a0;
    this.b1 = b1 / a0;
    this.b2 = b2 / a0;
    this.a1 = a1 / a0;
    this.a2 = a2 / a0;
  }

  process(x: number): number {
    const y = this.b0 * x + this.z1;
    this.z1 = this.b1 * x - this.a1 * y + this.z2;
    this.z2 = this.b2 * x - this.a2 * y;
    return y;
  }
}

function evalEnvelope(env: EnvelopeConfig, tSec: number, durSec: number): number {
  if (durSec <= 0 || tSec < 0 || tSec > durSec) return 0;
  const u = tSec / durSec;

  if (env.bellPower !== undefined) {
    return Math.pow(Math.sin(Math.PI * u), env.bellPower);
  }
  if (env.risePower !== undefined) {
    const tailCut = durSec > 0.012 ? Math.min(1, (durSec - tSec) / 0.012) : 1;
    const headFade = durSec > 0.015 ? Math.min(1, tSec / 0.015) : 1;
    return Math.pow(u, env.risePower) * headFade * tailCut;
  }

  const attackSec = Math.max(0.0004, env.attackMs / 1000);
  const attackGain = 1 - Math.exp(-tSec / attackSec);

  const decaySec = Math.max(0.001, (env.decayMs ?? durSec * 1000) / 1000);
  const sustain = env.sustain ?? 0;
  const decayGain = sustain + (1 - sustain) * Math.exp(-tSec / decaySec);

  let releaseGain = 1;
  if (env.releaseMs && env.releaseMs > 0) {
    const relSec = env.releaseMs / 1000;
    const remaining = durSec - tSec;
    if (remaining < relSec) {
      const r = Math.max(0, remaining / relSec);
      releaseGain = Math.sin((Math.PI / 2) * r) ** 2;
    }
  }
  return attackGain * decayGain * releaseGain;
}

function evalPan(pan: PanConfig | undefined, u: number): [number, number] {
  const start = pan?.start ?? 0;
  const end = pan?.end ?? start;
  const p = Math.max(-1, Math.min(1, start + (end - start) * u));
  // Equal-power stereo panning
  const angle = ((p + 1) * Math.PI) / 4;
  return [Math.cos(angle), Math.sin(angle)];
}

function renderLayer(
  layer: Layer,
  totalSamples: number,
  left: Float32Array,
  right: Float32Array,
  layerSeed: number,
): void {
  const startSample = Math.max(0, Math.round(((layer.startMs ?? 0) * SAMPLE_RATE) / 1000));
  const layerSamples = Math.min(
    totalSamples - startSample,
    layer.durationMs !== undefined
      ? Math.max(1, Math.round((layer.durationMs * SAMPLE_RATE) / 1000))
      : totalSamples - startSample,
  );
  if (layerSamples <= 0) return;

  const durSec = layerSamples / SAMPLE_RATE;
  const filter = layer.filter ? new BiquadFilter() : null;
  const noise = layer.kind === "noise" ? createGaussianNoise(layerSeed) : null;
  let phase = 0;

  // Configure filter once if static, otherwise update every 16 samples for smooth sweep.
  const sweepFilter =
    layer.filter !== undefined &&
    layer.filter.freqEnd !== undefined &&
    layer.filter.freqEnd !== layer.filter.freqStart;
  if (filter && layer.filter && !sweepFilter) {
    filter.configure(layer.filter.kind, layer.filter.freqStart, layer.filter.q);
  }

  for (let i = 0; i < layerSamples; i++) {
    const tSec = i / SAMPLE_RATE;
    const u = layerSamples > 1 ? i / (layerSamples - 1) : 0;

    if (filter && layer.filter && sweepFilter && (i & 15) === 0) {
      const f0 = layer.filter.freqStart;
      const f1 = layer.filter.freqEnd!;
      // Log-frequency interpolation sounds musically linear
      const freq = f0 * Math.pow(f1 / f0, u);
      filter.configure(layer.filter.kind, freq, layer.filter.q);
    }

    let sample = 0;
    if (layer.kind === "oscillator") {
      let freq = layer.freqStart;
      if (layer.freqEnd !== undefined && layer.freqEnd !== layer.freqStart) {
        if (layer.pitchDecayRate !== undefined) {
          freq = layer.freqEnd + (layer.freqStart - layer.freqEnd) * Math.exp(-layer.pitchDecayRate * tSec);
        } else {
          freq = layer.freqStart * Math.pow(layer.freqEnd / layer.freqStart, u);
        }
      }
      phase += (TWO_PI * freq) / SAMPLE_RATE;
      if (phase > TWO_PI) phase -= TWO_PI * Math.floor(phase / TWO_PI);

      if (layer.waveform === "triangle") {
        sample = (2 / Math.PI) * Math.asin(Math.sin(phase));
      } else {
        sample = Math.sin(phase);
      }
    } else if (noise) {
      sample = noise();
    }

    if (filter) {
      sample = filter.process(sample);
    }

    const env = evalEnvelope(layer.envelope, tSec, durSec);
    const value = sample * env * layer.gain;
    const [gL, gR] = evalPan(layer.pan, u);
    const outIndex = startSample + i;
    left[outIndex] += value * gL;
    right[outIndex] += value * gR;
  }
}

export function renderGraph(graph: SoundGraph, seed: number): { left: Float32Array; right: Float32Array } {
  const totalSamples = Math.max(1, Math.round((graph.durationMs * SAMPLE_RATE) / 1000));
  const left = new Float32Array(totalSamples);
  const right = new Float32Array(totalSamples);

  for (let idx = 0; idx < graph.layers.length; idx++) {
    renderLayer(graph.layers[idx], totalSamples, left, right, (seed + Math.imul(idx + 1, 2654435761)) >>> 0);
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

  // Smooth tail fade to prevent click at buffer end
  const fadeSamples = Math.min(totalSamples, Math.round(((graph.tailFadeMs ?? 6) * SAMPLE_RATE) / 1000));
  for (let i = 0; i < fadeSamples; i++) {
    const r = i / Math.max(1, fadeSamples);
    const gain = Math.sin((Math.PI / 2) * r) ** 2;
    const idx = totalSamples - 1 - i;
    left[idx] *= gain;
    right[idx] *= gain;
  }

  // Soft-knee peak ceiling (< 0.96, zero clipping, linear below 0.72)
  const knee = 0.72;
  const headroom = 0.24; // 0.72 + 0.24 = 0.96 max asymptote
  const softLimit = (x: number): number => {
    const ax = Math.abs(x);
    if (ax <= knee) return x;
    return Math.sign(x) * (knee + headroom * Math.tanh((ax - knee) / headroom));
  };
  let peak = 0;
  for (let i = 0; i < totalSamples; i++) {
    const l = softLimit(left[i]);
    const r = softLimit(right[i]);
    left[i] = l;
    right[i] = r;
    const m = Math.max(Math.abs(l), Math.abs(r));
    if (m > peak) peak = m;
  }

  // Deterministic peak normalization to -2.0 dBFS (commercial SFX library standard, zero clipping)
  const targetPeak = Math.pow(10, -2.0 / 20);
  if (peak > 1e-6) {
    const normGain = targetPeak / peak;
    for (let i = 0; i < totalSamples; i++) {
      left[i] *= normGain;
      right[i] *= normGain;
    }
  }

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
      const m = 0.5 * (left[i] + right[i]);
      e += m * m;
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
