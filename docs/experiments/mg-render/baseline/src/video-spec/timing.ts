/**
 * Time law mirror of apps/api/app/editing/timing.py — one law, two
 * implementations, pinned to the same numbers by
 * fixtures/timing_golden.json. Times are integer ticks at a rate; every
 * range is [start, end); frames derive through ONE quantize formula
 * (exact round-half-up). Number math is exact here: realistic values stay
 * far below 2^53.
 */

/** Ticks → output frame number: floor(ticks * fps / rate + 1/2), integer math. */
export function ticksToFrames(
  ticks: number,
  rate: number,
  fpsNum: number,
  fpsDen = 1,
): number {
  if (!Number.isInteger(ticks) || ticks < 0) throw new Error("ticks must be a non-negative integer");
  return Math.floor((2 * ticks * fpsNum + rate * fpsDen) / (2 * rate * fpsDen));
}

/** Seconds → ticks, round-half-up (decimal inputs only; the API side parses
 * via exact rationals — fixtures keep the two honest). */
export function secondsToTicks(seconds: number, rate: number): number {
  if (!(seconds >= 0)) throw new Error("seconds must be non-negative");
  return Math.round(seconds * rate);
}

/** Ticks → seconds (display only; never a stored truth). */
export function ticksToSeconds(ticks: number, rate: number): number {
  return ticks / rate;
}
