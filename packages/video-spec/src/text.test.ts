import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { deriveTextPartFamilies } from "./text";
import type { TextPartKind } from "./text";

const fixture = JSON.parse(
  readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), "../fixtures/text_parts_golden.json"),
    "utf8",
  ),
);

test("TextPart derivation matches the shared Unicode-scalar golden law", () => {
  for (const c of fixture.cases) {
    const kinds = new Set<TextPartKind>(c.parts.map((part: { kind: TextPartKind }) => part.kind));
    assert.deepEqual(deriveTextPartFamilies(c.text, kinds), c.parts, c.name);
  }
});
