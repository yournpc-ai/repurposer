/**
 * Renderer-neutral TextPart derivation. Mirrors app/editing/animation.py:
 * Unicode-scalar ranges, explicit newline layout units and stable content/
 * range IDs. No DOM, React or Remotion participates in segmentation.
 */

export const SEGMENTATION_VERSION = "scalar-grapheme-v1";
export const LAYOUT_VERSION = "explicit-line-inline-v1";

export type TextPartKind = "line" | "word" | "grapheme";
export interface TextRange {
  start: number;
  end: number;
}
export interface TextPart {
  part_id: string;
  kind: TextPartKind;
  text: string;
  text_range: TextRange;
  layout_range: TextRange;
}

const MASK_64 = (1n << 64n) - 1n;

function fnv1a64(data: Uint8Array): string {
  let value = 0xcbf29ce484222325n;
  for (const byte of data) {
    value ^= BigInt(byte);
    value = (value * 0x100000001b3n) & MASK_64;
  }
  return value.toString(16).padStart(16, "0");
}

function part(
  kind: TextPartKind,
  chars: string[],
  start: number,
  end: number,
  line: TextRange,
): TextPart {
  const text = chars.slice(start, end).join("");
  const identity =
    `${SEGMENTATION_VERSION}|${kind}|${end - start}:${text}|` +
    `${start}|${end}|${line.start}|${line.end}`;
  return {
    part_id: `${kind}:${start}:${end}:${fnv1a64(new TextEncoder().encode(identity))}`,
    kind,
    text,
    text_range: { start, end },
    layout_range: { ...line },
  };
}

function lineRanges(chars: string[]): TextRange[] {
  const lines: TextRange[] = [];
  let start = 0;
  for (let index = 0; index < chars.length; index += 1) {
    const char = chars[index];
    if (char === "\n" || char === "\r") {
      lines.push({ start, end: index });
      if (char === "\r" && chars[index + 1] === "\n") index += 1;
      start = index + 1;
    }
  }
  lines.push({ start, end: chars.length });
  return lines;
}

const isMark = (char: string) => /^\p{Mark}$/u.test(char);
const isVariation = (char: string) => {
  const value = char.codePointAt(0)!;
  return (value >= 0xfe00 && value <= 0xfe0f) || (value >= 0xe0100 && value <= 0xe01ef);
};
const isEmojiModifier = (char: string) => {
  const value = char.codePointAt(0)!;
  return value >= 0x1f3fb && value <= 0x1f3ff;
};
const isRegionalIndicator = (char: string) => {
  const value = char.codePointAt(0)!;
  return value >= 0x1f1e6 && value <= 0x1f1ff;
};

function graphemes(chars: string[], line: TextRange): TextPart[] {
  const parts: TextPart[] = [];
  let index = line.start;
  while (index < line.end) {
    let end = index + 1;
    let regionalCount = isRegionalIndicator(chars[index]) ? 1 : 0;
    while (end < line.end) {
      const previous = chars[end - 1];
      const char = chars[end];
      if (
        previous === "‍" ||
        char === "‍" ||
        isMark(char) ||
        isVariation(char) ||
        isEmojiModifier(char)
      ) {
        end += 1;
        continue;
      }
      if (
        isRegionalIndicator(previous) &&
        isRegionalIndicator(char) &&
        regionalCount % 2 === 1
      ) {
        regionalCount += 1;
        end += 1;
        continue;
      }
      break;
    }
    parts.push(part("grapheme", chars, index, end, line));
    index = end;
  }
  return parts;
}

const isWord = (cluster: string) => /^[\p{L}\p{N}\p{M}]+$/u.test(cluster);
const isJoiner = (cluster: string) => ["'", "’", "-", "‐", "‑"].includes(cluster);

function words(chars: string[], line: TextRange): TextPart[] {
  const units = graphemes(chars, line);
  const result: TextPart[] = [];
  let openStart: number | null = null;
  let openEnd: number | null = null;
  const flush = () => {
    if (openStart !== null && openEnd !== null) {
      result.push(part("word", chars, openStart, openEnd, line));
    }
    openStart = openEnd = null;
  };
  units.forEach((grapheme, index) => {
    const { start, end } = grapheme.text_range;
    const cluster = grapheme.text;
    if (isWord(cluster)) {
      if (openStart === null) openStart = start;
      openEnd = end;
      return;
    }
    if (
      isJoiner(cluster) &&
      openStart !== null &&
      index + 1 < units.length &&
      isWord(units[index + 1].text)
    ) {
      openEnd = end;
      return;
    }
    flush();
    if (cluster && !/^\s+$/u.test(cluster)) {
      result.push(part("word", chars, start, end, line));
    }
  });
  flush();
  return result;
}

export function deriveTextParts(text: string, kind: TextPartKind): TextPart[] {
  const chars = Array.from(text);
  const lines = lineRanges(chars);
  if (kind === "line") {
    return lines.map((line) => part("line", chars, line.start, line.end, line));
  }
  if (kind === "grapheme") return lines.flatMap((line) => graphemes(chars, line));
  if (kind === "word") return lines.flatMap((line) => words(chars, line));
  throw new Error(`unsupported TextPart kind ${kind}`);
}

export function deriveTextPartFamilies(text: string, kinds: Set<TextPartKind>): TextPart[] {
  const parts = new Map<string, TextPart>();
  for (const item of deriveTextParts(text, "line")) parts.set(item.part_id, item);
  for (const kind of [...kinds].filter((kind) => kind !== "line").sort()) {
    for (const item of deriveTextParts(text, kind)) parts.set(item.part_id, item);
  }
  return [...parts.values()];
}
