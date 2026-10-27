import { registerRoot } from "remotion";

import { VideoRoot } from "./Root";

// Entry point the render service bundles for the video family
// (see ../index.ts). The composition id is "Video".
registerRoot(VideoRoot);
