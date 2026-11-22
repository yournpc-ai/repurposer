import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { evaluateKeyframes, evaluateProperty } from "./animation";
import type { VideoKeyframe } from "./schema";

const fixture = JSON.parse(
  readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "../fixtures/animation_golden.json"),
    "utf8",
  ),
);

test("keyframe evaluation golden law", () => {
  for (const c of fixture.cases) {
    const tolerance = c.tolerance ?? 1e-9;
    for (const p of c.points) {
      const actual = evaluateKeyframes(c.keyframes as VideoKeyframe[], p.frame);
      if (Array.isArray(p.value)) {
        const vec = actual as number[];
        assert.ok(Array.isArray(actual) && vec.length === p.value.length, c.name);
        vec.forEach((v, i) =>
          assert.ok(
            Math.abs(v - (p.value as number[])[i]) <= tolerance,
            `${c.name} @${p.frame}[${i}]: got ${v}, want ${(p.value as number[])[i]}`,
          ),
        );
      } else {
        assert.ok(
          Math.abs((actual as number) - p.value) <= tolerance,
          `${c.name} @${p.frame}: got ${actual}, want ${p.value}`,
        );
      }
    }
  }
});

test("keyframes evaluate correctly even when declared out of order", () => {
  const value = evaluateKeyframes(
    [
      { at: 10, value: 100, easing: { kind: "linear" } },
      { at: 0, value: 0, easing: { kind: "linear" } },
    ],
    5,
  );
  assert.equal(value, 50);
});

test("evaluateProperty finds the (object, property) pair only", () => {
  const animations = [
    {
      target_object_id: "obj_a",
      property: "opacity",
      keyframes: [{ at: 0, value: 0.5, easing: { kind: "linear" as const } }],
    },
  ];
  assert.equal(evaluateProperty(animations, "obj_a", "opacity", 0), 0.5);
  assert.equal(evaluateProperty(animations, "obj_b", "opacity", 0), undefined);
  assert.equal(evaluateProperty(animations, "obj_a", "transform.scale", 0), undefined);
});

test("evaluateProperty selects a whole object or one explicit TextPart", () => {
  const animations = [
    {
      target_object_id: "obj_a",
      property: "opacity",
      keyframes: [{ at: 0, value: 0.25, easing: { kind: "linear" as const } }],
    },
    {
      target_object_id: "obj_a",
      target_text_part_id: "line:0:4:part",
      property: "opacity",
      keyframes: [{ at: 0, value: 0.75, easing: { kind: "linear" as const } }],
    },
  ];
  assert.equal(evaluateProperty(animations, "obj_a", "opacity", 0), 0.25);
  assert.equal(
    evaluateProperty(animations, "obj_a", "opacity", 0, "line:0:4:part"),
    0.75,
  );
  assert.equal(
    evaluateProperty(animations, "obj_a", "opacity", 0, "line:5:9:other"),
    undefined,
  );
});
