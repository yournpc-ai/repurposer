---
name: text-animation
description: First-version direction for a native text-animation video using exact user copy and content-driven native text and shape animation.
license: Proprietary
compatibility: Repurposer design_video native motion-graphics first design and native Preset expansion; optional video-template.json is not used.
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - text-animation
    - motion-graphics
    - native-preset
---

## Text-animation method

Turn the user's exact on-screen copy into a short sequence of readable native
text scenes. Establish one visual hierarchy, pace one thought per scene, and
choose independently timed native text blocks and geometric shapes to support the content.
Use text_beats for changing emphasis, spatial contrast and successive reading beats
inside a scene; avoid holding a whole paragraph as one uniformly animated block. Choose scene
boundaries, typography, palette, alignment, entrances and reading holds for this
work. Paragraph boundaries are not mandatory scene cuts; there is no fixed
three-act structure. Do not copy the sample film's dark background, accent,
second-scene emphasis, final typewriter or sound cue into every work.

The Director's native motion is used unless the user selects a Preset. A Preset
is an optional editable motion choice, not a mandatory treatment for this Skill.
Keep word and grapheme targeting compatible within each text object.

Keep every factual word grounded in the supplied copy. Do not add a product,
audience, platform, result, quotation, or call to action that the user did not
provide or request. Spoken narration is off unless the user explicitly asks
for it.

### Inputs and boundaries

- Requires the user's text or an explicitly requested distilled copy brief;
  it does not require a video-template.json file or any media material.
- Uses the native motion-graphics design path, with optional user-selected Preset expansion.
  There is no StylePack layer, second template language, component runtime,
  hidden execution tool, or renderer-specific field.
- The Skill guides only the first design. Later changes use revise_video;
  production consumes the saved CompositionVersion without reloading it.
