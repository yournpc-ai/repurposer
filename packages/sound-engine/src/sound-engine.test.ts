import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  SOUND_RECIPES,
  canonicalSoundSpecJson,
  synthesizeWav,
} from "./index.js";

describe("@repurposer/sound-engine core contract", () => {
  it("renders all 6 recipes deterministically with zero clipping and valid acoustic cues", () => {
    assert.deepEqual(
      SOUND_RECIPES.map((r) => r.id),
      ["whoosh", "impact", "click", "riser", "stinger", "swoosh_cut"],
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

      // Sync cue sanity
      if (recipe.sync_cue === "onset") {
        assert.ok(a.acoustics.peak_offset_ms < a.acoustics.duration_ms * 0.35, `${recipe.id} onset peak`);
      } else if (recipe.sync_cue === "energy_peak") {
        assert.ok(
          a.acoustics.peak_offset_ms > a.acoustics.duration_ms * 0.25 &&
            a.acoustics.peak_offset_ms < a.acoustics.duration_ms * 0.75,
          `${recipe.id} midpoint peak`,
        );
      } else if (recipe.sync_cue === "end_peak") {
        assert.ok(a.acoustics.peak_offset_ms > a.acoustics.duration_ms * 0.65, `${recipe.id} end peak`);
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
