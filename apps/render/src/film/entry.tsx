import { registerRoot } from "remotion";

import { FilmRoot } from "./Root";

// Entry point the render service bundles for the film family
// (`@remotion/bundler`, see film/render.ts). The composition id is "Film".
registerRoot(FilmRoot);
