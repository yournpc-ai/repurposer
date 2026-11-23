import assert from "node:assert/strict";
import test from "node:test";
import type { VideoSpec } from "@repurposer/video-spec";
import { stageVideoSpecSources } from "./index";

test("stageVideoSpecSources stages MotionBlockObject.resources[0..N] alongside clip sources and fonts", async () => {
  const stagedCalls: Array<{ url: string; digest?: string }> = [];
  const fakeStage = async (url: string, _cacheKey?: string, digest?: string) => {
    stagedCalls.push({ url, digest });
    return `http://127.0.0.1:3001/cache/${digest ?? "none"}`;
  };

  const d0 = "a".repeat(64);
  const d1 = "b".repeat(64);
  const df = "f".repeat(64);
  const spec: VideoSpec = {
    family: "video",
    format: 1,
    fps: { num: 30, den: 1 },
    width: 1920,
    height: 1080,
    background: "#070B11",
    sample_rate: 48000,
    duration_frames: 150,
    fonts: [
      {
        font_id: "noto-sans-sc",
        font_set_digest: df,
        family: "Noto Sans SC",
        weight: 700,
        format: "opentype",
        url: "https://tos.example/fonts/bold.otf",
        digest: df,
      },
    ],
    tracks: [
      {
        track_id: "trk_mg_main",
        kind: "visual",
        role: "main",
        order: 0,
        clips: [
          {
            clip_id: "clp_cta",
            start_frame: 0,
            end_frame: 150,
            scene_id: "scn_1",
            source: { url: "https://tos.example/img0.png", digest: d0 },
            object: {
              kind: "motion_block",
              object_id: "obj_cta",
              block_id: "closing_cta",
              block_version: 1,
              props: { brand_name: "OxValue.AI", tagline: "Evidence-first valuation", logo_surface: "light_pill" },
              resources: [
                { path: "media/img_0.png", url: "https://tos.example/img0.png", digest: d0, content_type: "image/png" },
                { path: "media/img_1.png", url: "https://tos.example/img1.png", digest: d1, content_type: "image/png" },
              ],
              layout: { x: 0, y: 0, width: 1920, height: 1080 },
              fit: "cover",
              transform: { x: 0, y: 0, scale: 1, rotation: 0, origin: "center" },
              opacity: 1,
            },
            animations: [],
          },
        ],
      },
    ],
    provenance: {
      composition_id: "11111111-1111-1111-1111-111111111111",
      composition_version_id: "22222222-2222-2222-2222-222222222222",
      content_digest: "c".repeat(64),
    },
  };

  const staged = await stageVideoSpecSources(spec, fakeStage);
  const clip = staged.tracks[0].clips[0];
  assert.equal(clip.object.kind, "motion_block");
  assert.equal(clip.object.resources[0].url, `http://127.0.0.1:3001/cache/${d0}`);
  assert.equal(clip.object.resources[1].url, `http://127.0.0.1:3001/cache/${d1}`);
  assert.equal(staged.fonts[0].url, `http://127.0.0.1:3001/cache/${df}`);
  assert.ok(stagedCalls.some((c) => c.url === "https://tos.example/img1.png" && c.digest === d1));
});
