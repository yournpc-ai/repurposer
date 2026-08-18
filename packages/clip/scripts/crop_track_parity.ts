/**
 * crop_track parity harness (ADR-045): read {spec, times} JSON from argv[2],
 * print the TS sampler's crop values as JSON. Driven by
 * apps/api/scripts/crop_track_parity.py — the two samplers must agree
 * EXACTLY (both f64, same op order).
 */
import { readFileSync } from "node:fs";

import { sampleCrop, type ClipSpec } from "../src/types";

const input = JSON.parse(readFileSync(process.argv[2], "utf-8")) as {
  spec: ClipSpec;
  times: number[];
};
const out = input.times.map((t) => sampleCrop(input.spec, t));
process.stdout.write(JSON.stringify(out));
