export function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function easeOutQuart(t: number): number {
  const u = 1 - clamp01(t);
  return 1 - u * u * u * u;
}

export function easeOutCubic(t: number): number {
  const u = 1 - clamp01(t);
  return 1 - u * u * u;
}

export function easeOutExpo(t: number): number {
  const x = clamp01(t);
  return x >= 1 ? 1 : 1 - Math.pow(2, -10 * x);
}

export function easeInOutSine(t: number): number {
  return -(Math.cos(Math.PI * clamp01(t)) - 1) / 2;
}

/**
 * Closed-form damped harmonic spring evaluated purely from elapsed time `tSec`.
 * Zero state or rAF; deterministic frame-by-frame for Remotion & future Core C.
 */
export function springOut(tSec: number, omega = 13.0, zeta = 0.82): number {
  if (tSec <= 0) return 0;
  if (tSec > 2.5) return 1;
  const decay = Math.exp(-zeta * omega * tSec);
  if (zeta >= 1) {
    return clamp01(1 - decay * (1 + omega * tSec));
  }
  const wd = omega * Math.sqrt(1 - zeta * zeta);
  const val = 1 - decay * (Math.cos(wd * tSec) + (zeta / Math.sqrt(1 - zeta * zeta)) * Math.sin(wd * tSec));
  return Math.max(0, Math.min(1.03, val));
}

export function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace("#", "");
  if (clean.length !== 6) return `rgba(13, 148, 136, ${alpha})`;
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

export function lerp(from: number, to: number, t: number): number {
  return from + (to - from) * t;
}

export function remap(value: number, from: number, to: number, low = 0, high = 1): number {
  return lerp(low, high, clamp01((value - from) / (to - from)));
}

export function cueProgress(tSec: number, cueSec: number, durSec: number): number {
  return durSec > 0 ? remap(tSec, cueSec, cueSec + durSec) : Number(tSec >= cueSec);
}

export function easeInOutCubic(t: number): number {
  const p = clamp01(t);
  return p < 0.5 ? 4 * p ** 3 : 1 - ((2 - 2 * p) ** 3) / 2;
}

export function easeOutQuint(t: number): number {
  return 1 - (1 - clamp01(t)) ** 5;
}
