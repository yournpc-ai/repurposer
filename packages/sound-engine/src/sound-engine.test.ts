import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { analyzeAcoustics, createNoise, oscillatorSample, renderGraph } from "./dsp.js";
import { SAMPLE_RATE, type SoundGraph } from "./types.js";

import {
  SOUND_RECIPES,
  canonicalSoundSpecJson,
  synthesizeWav,
} from "./index.js";

describe("@repurposer/sound-engine core contract", () => {
  it("renders all 22 recipes deterministically with zero clipping and valid acoustic cues", () => {
    assert.deepEqual(
      SOUND_RECIPES.map((r) => r.id),
      ["whoosh", "impact", "click", "riser", "stinger", "swoosh_cut",
        "sub_swell", "shimmer_lift", "deep_hit", "sub_drop", "kinetic_thud",
        "velvet_pass", "page_turn", "title_bloom", "metric_chime", "callout_ping",
        "studio_air", "pulse_bed", "soft_pop", "toggle_on", "select_tick", "confirm_chime"],
    );

    for (const recipe of SOUND_RECIPES) {
      const a = synthesizeWav({ recipeId: recipe.id });
      const b = synthesizeWav({ recipeId: recipe.id });

      assert.equal(a.wav.byteLength, b.wav.byteLength);
      assert.ok(Buffer.from(a.wav).equals(Buffer.from(b.wav)), `${recipe.id} must be byte-identical`);
      assert.equal(Buffer.from(a.wav.slice(0, 4)).toString("ascii"), "RIFF");
      assert.equal(a.acoustics.sample_rate, 48000);
      assert.equal(a.acoustics.channels, 2);
      assert.ok(a.acoustics.peak_dbfs < 0, `${recipe.id} must not clip (peak=${a.acoustics.peak_dbfs})`);
      assert.ok(
        a.acoustics.peak_dbfs >= -2.5 && a.acoustics.peak_dbfs <= -1.5,
        `${recipe.id} must normalize near -2 dBFS (peak=${a.acoustics.peak_dbfs})`,
      );
      assert.ok(a.acoustics.spectral_centroid_hz > 40, `${recipe.id} spectral centroid must be positive`);
      assert.equal(a.acoustics.waveform_peaks.length, 32);

      assert.ok(a.acoustics.lufs > -35 && a.acoustics.lufs < -5, recipe.id);
      for (const channel of [a.left, a.right]) {
        assert.equal(Math.abs(channel[0]), 0);
        assert.equal(Math.abs(channel[channel.length - 1]), 0);
        assert.ok(channel.slice(-24).every(x => Math.abs(x) < 0.001), recipe.id);
        assert.ok(Math.abs(channel.reduce((sum, x) => sum + x, 0) / channel.length) < 0.000001, recipe.id);
      }

      let energy = 0;
      let moment = 0;
      for (let i = 0; i < a.left.length; i++) {
        const power = a.left[i] ** 2 + a.right[i] ** 2;
        energy += power;
        moment += i * power;
      }
      const center = moment / (energy * a.left.length);
      const peak = a.acoustics.peak_offset_ms / a.acoustics.duration_ms;
      const window = { onset: [0, 0.35], energy_peak: [0.25, 0.75], end_peak: [0.65, 1] }[recipe.sync_cue];
      for (const ratio of [peak, center]) {
        assert.ok(ratio > window[0] && ratio < window[1], `${recipe.id}: ${ratio} outside ${window}`);
      }
    }
  });

  it("reflects parameter edits acoustically and excludes discovery metadata from canonical spec", () => {
    const bright = synthesizeWav({ recipeId: "impact", params: { pitch: 145, tone: 75 } });
    const deep = synthesizeWav({ recipeId: "impact", params: { pitch: 65, tone: 25 } });

    assert.ok(
      deep.acoustics.spectral_centroid_hz < bright.acoustics.spectral_centroid_hz,
      `deep impact centroid (${deep.acoustics.spectral_centroid_hz}) < bright (${bright.acoustics.spectral_centroid_hz})`,
    );

    const specJson = canonicalSoundSpecJson(deep.spec);
    for (const forbidden of ["name", "desc", "domain", "category", "use_for", "avoid", "mix_hint"]) {
      assert.ok(!specJson.includes(`"${forbidden}"`), `canonical spec must exclude ${forbidden}`);
    }
  });
});

// Orthogonal projection on a DFT bin. Integer-cycle fixtures avoid leakage.
function binPower(samples: Float64Array, bin: number): number {
  let real = 0;
  let imag = 0;
  for (let i = 0; i < samples.length; i++) {
    const angle = 2 * Math.PI * i * bin / samples.length;
    real += samples[i] * Math.cos(angle);
    imag += samples[i] * Math.sin(angle);
  }
  return (real * real + imag * imag) / samples.length ** 2;
}

describe("DSP reference signals", () => {
  it("measures white, pink and brown power-density slopes across four octaves", () => {
    const size = 4096;
    for (const [color, target] of [["white", 0], ["pink", -3], ["brown", -6]] as const) {
      const noise = createNoise(color, 7391);
      const bands = [0, 0, 0, 0, 0];
      for (let frame = 0; frame < 16; frame++) {
        const samples = Float64Array.from({ length: size }, (_, i) =>
          noise() * (0.5 - 0.5 * Math.cos(2 * Math.PI * i / size)));
        for (let octave = 0; octave < bands.length; octave++) {
          for (const k of [19, 21, 23, 25]) bands[octave] += binPower(samples, k * 2 ** octave);
        }
      }
      const slope = bands.reduce((sum, power, octave) => sum + (octave - 2) * Math.log10(power), 0);
      assert.ok(Math.abs(slope - target) < 0.65, `${color}: ${slope} dB/octave`);
    }
  });

  it("reduces folded harmonics of both discontinuous waveforms", () => {
    const n = 4800;
    const fundamental = 610; // 6.1 kHz, exactly three harmonics below Nyquist
    const step = fundamental / n;
    for (const wave of ["sawtooth", "square"] as const) {
      const residual = (corrected: boolean) => {
        const samples = Float64Array.from({ length: n }, (_, i) => {
          const phase = ((i * fundamental) % n) / n;
          if (corrected) return oscillatorSample(wave, phase, step);
          return wave === "sawtooth" ? 2 * phase - 1 : phase < 0.5 ? 1 : -1;
        });
        const total = samples.reduce((sum, x) => sum + x * x, 0) / n;
        const legal = [1, 2, 3].reduce((sum, h) => sum + 2 * binPower(samples, h * fundamental), 0);
        return (total - legal) / legal;
      };
      assert.ok(residual(true) < residual(false) * 0.15, wave);
    }
  });

  it("produces a delayed, decaying stereo reverb tail and collapses it at zero width", () => {
    const graph: SoundGraph = {
      durationMs: 700, layers: [{
        kind: "noise", gain: 0.3, durationMs: 9, filter: { kind: "lowpass", freqStart: 5300, q: 0.7 },
        envelope: { attackMs: 1, releaseMs: 2 },
      }],
      reverb: { predelayMs: 19, decaySec: 0.32, dampHz: 2600, mix: 1 },
    };
    const wet = renderGraph(graph, 91);
    assert.ok(wet.left.subarray(0, 42 * 48).every(x => x === 0));
    const energy = (from: number, to: number) => wet.left.subarray(from * 48, to * 48)
      .reduce((sum, x) => sum + x * x, 0);
    const early = energy(60, 160);
    assert.ok(early > 0.1);
    assert.ok(energy(220, 320) > early * 1e-7 && energy(220, 320) < early * 0.1);
    assert.notDeepEqual(wet.left, wet.right);
    const mono = renderGraph({ ...graph, width: 0 }, 91);
    assert.deepEqual(mono.left, mono.right);
  });

  it("changes frequency balance with notch and peaking EQ, and spreads detuned voices", () => {
    const response = (kind: "peaking" | "notch", gainDb: number) => {
      const { left } = renderGraph({
        durationMs: 150, layers: [1000, 3000].map(freqStart => ({
          kind: "oscillator", waveform: "sine", freqStart, gain: 0.2,
          envelope: { attackMs: 2, sustain: 1 },
          filter: { kind, freqStart: 1000, q: 3, gainDb },
        })),
      }, 1);
      const steady = Float64Array.from(left.subarray(2400, 4800));
      return binPower(steady, 50) / binPower(steady, 150);
    };
    assert.ok(response("notch", 0) < 0.01);
    assert.ok(response("peaking", 6) > 3.4);

    const chord: SoundGraph = { durationMs: 300, layers: [{
      kind: "oscillator", waveform: "sawtooth", freqStart: 261, gain: 0.4,
      voices: 8, detune: 9, envelope: { attackMs: 8, sustain: 0.8 },
    }] };
    const stereo = renderGraph(chord, 1);
    const difference = stereo.left.reduce((sum, x, i) => sum + (x - stereo.right[i]) ** 2, 0);
    assert.ok(difference / stereo.left.length > 0.001);
  });

  it("holds a reconstructed 12 kHz crest below the true-peak ceiling", () => {
    const { left } = renderGraph({
      durationMs: 160, lowpass: 17000, layers: [{
        kind: "oscillator", waveform: "sine", freqStart: 12000, gain: 1,
        envelope: { attackMs: 10, sustain: 1, releaseMs: 12 },
      }],
    }, 0);
    // Adjacent steady-state samples are in quadrature at exactly Fs/4.
    const i = 48 * 50;
    const crest = Math.hypot(left[i], left[i + 1]);
    assert.ok(crest > 1.10 * Math.max(Math.abs(left[i]), Math.abs(left[i + 1])));
    assert.ok(crest > 0.75 && crest <= 10 ** (-1.70 / 20), String(crest));
  });

  it("meters a calibrated stereo tone, ignores gated silence and pads sub-block SFX", () => {
    const signal = new Float32Array(SAMPLE_RATE * 3);
    for (let i = 0; i < SAMPLE_RATE; i++) signal[i] = 0.1 * Math.sin(2 * Math.PI * 1000 * i / SAMPLE_RATE);
    const loudness = (x: Float32Array) => analyzeAcoustics(x, x).lufs;
    assert.ok(Math.abs(loudness(signal.subarray(0, SAMPLE_RATE)) + 20) < 0.15);
    assert.ok(Math.abs(loudness(signal) - loudness(signal.subarray(0, SAMPLE_RATE * 1.5))) < 0.01);
    const gated = loudness(signal);
    for (let i = SAMPLE_RATE; i < signal.length; i++) {
      signal[i] = 0.001 * Math.sin(2 * Math.PI * 1000 * i / SAMPLE_RATE);
    }
    assert.ok(Math.abs(loudness(signal) - gated) < 0.05);
    const short = signal.slice(0, SAMPLE_RATE / 10);
    const padded = new Float32Array(SAMPLE_RATE * 0.4);
    padded.set(short);
    assert.equal(loudness(short), loudness(padded));
    assert.ok(Math.abs(loudness(short) + 26) < 0.15);
  });
});
