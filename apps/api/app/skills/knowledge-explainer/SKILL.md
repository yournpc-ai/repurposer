---
name: knowledge-explainer
description: First-version direction for a script-led knowledge explainer using READY narration alignment, word anchors, native Presets, and controlled draw-2d or remotion-project Generators.
license: Proprietary
compatibility: Repurposer design_video READY source-aligned narration, bounded draw-2d, or an isolated remotion-project runner when the deployment enables one.
metadata:
  version: "1.0.0"
  author: repurposer
  tags:
    - knowledge-explainer
    - narration-alignment
    - draw-2d
    - remotion-project
---

## Knowledge-explainer method

Explain the knowledge in the user's script, or in a clearly disclosed simulated
knowledge script supplied for a demo. Organize the explanation into a coherent
visual progression from the central idea to its supporting points. Use a
controlled Generator to explain the concepts rather than add unrelated
decoration. Keep important standalone labels, captions, narration, and sound as
native editable objects. A simulated script is a creative demo input, not an
interview, research citation, or factual source.

For a final recording with its exact script, use a READY NarrationAlignment.
Select real sentence ids and emphasis_word_ids from that alignment; the system
resolves immutable audio ranges and word anchors. Native caption-phrases and
text-impact expansions may use those facts directly. Never estimate a word
time, invent a word id, or treat PENDING, PROCESSING, or review_required as
READY. Include exactly one explanatory Generator in the scene that carries the
central concept; the server owns its output window and saves the source for review; execution waits for authorized production.
Use draw-2d for relationships its four primitives express well. When an active
isolated component runner is available, use remotion-project for precise
layouts, multi-stage transformations, or richer motion that needs controlled
TSX. Necessary graphic-bound labels may live inside that visual, but they do
not become independently editable native text.

When the requested picture needs a simple animated diagram and no suitable
READY alignment exists, use draw-2d with declared commands and bounded output.
For a complete multi-scene explanation or a continuous longer transformation,
component mode can organize ordinary Composition scenes when the isolated
runner is active. Preserve important explanatory text as native objects where
the design contract supports it.

### Inputs and boundaries

- The knowledge itself may be the only content input; real image, video,
  webpage, interview, or other evidence assets are not required. A
  source-aligned design requires fixed audio, its verbatim final script, and a
  READY alignment.
- remotion-project requires both the API opt-in and a render runner that
  reports active isolation. When either is absent, do not imply that TSX
  component authoring is live; choose draw-2d only when it can honestly express
  the picture, or state the specific capability gap.
- No interface, dataset, quotation, user material, narration timing, or media
  asset may be invented. Diagram relationships must explain the supplied
  knowledge. The Skill grants no tool, network, file, production, or billing
  permission and is not reloaded for revision or a Run.
