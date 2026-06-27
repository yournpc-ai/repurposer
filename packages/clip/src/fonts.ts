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

/** Resolve a brand font key to a loaded font-family, or sans-serif fallback. */
export function fontFamilyFor(key?: string | null): string {
  const load = key ? LOADERS[key] : undefined;
  if (!load) return "sans-serif";
  return load(undefined, OPTS).fontFamily;
}
