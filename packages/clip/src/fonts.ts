/**
 * Brand caption fonts via @remotion/google-fonts. Maps the brand template's
 * font key (see apps/web/src/routes/brand-template.tsx `FONTS`) to a loaded
 * Google font family. loadFont() registers the @font-face and (in render) waits
 * for the font before painting; it's idempotent, so calling per-render is fine.
 *
 * NOTE: fonts are fetched from Google's CDN at render/preview time — a fully
 * offline renderer would instead bundle the .woff2 via @remotion/fonts.
 */
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadLilita } from "@remotion/google-fonts/LilitaOne";
import { loadFont as loadPlayfair } from "@remotion/google-fonts/PlayfairDisplay";
import { loadFont as loadSourceSerif } from "@remotion/google-fonts/SourceSerif4";

type FontOpts = { subsets?: string[]; ignoreTooManyRequestsWarning?: boolean };
type Loader = (style?: string, options?: FontOpts) => { fontFamily: string };

const LOADERS: Record<string, Loader> = {
  lilita: loadLilita as Loader,
  inter: loadInter as Loader,
  playfair: loadPlayfair as Loader,
  "source-serif": loadSourceSerif as Loader,
};

// Limit to the latin subset (keeps render-time font fetches modest across the
// fonts' many weights); the warning is just a perf hint.
const OPTS: FontOpts = { subsets: ["latin"], ignoreTooManyRequestsWarning: true };

/** The brand families above are Latin-only, and their @font-face declares a
 * latin unicode-range — so CJK codepoints never match them and fall through
 * the stack per character. This stack is what catches them:
 * 'Noto Sans SC' — the vendored OFL font the render container installs into
 * fontconfig (apps/render Dockerfile; WITHOUT it the slim image has zero CJK
 * glyphs and Chinese titles/captions bake as tofu 口口口), then the macOS /
 * Windows dev-machine fonts, then generic sans. */
export const CJK_FALLBACK_STACK =
  "'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', sans-serif";

/** Resolve a brand font key to a loaded font-family stack (CJK fallback
 * appended), or the CJK-safe sans stack when unbranded. */
export function fontFamilyFor(key?: string | null): string {
  const load = key ? LOADERS[key] : undefined;
  if (!load) return CJK_FALLBACK_STACK;
  return `${load(undefined, OPTS).fontFamily}, ${CJK_FALLBACK_STACK}`;
}
