---
name: launch-film
description: Launch-film storyboard craft — scene semantics, pacing rhythm, citation discipline, camera storytelling over a page screenshot, naming. Woven into the launch_film tool's storyboarder prompt at assembly time; the model never loads it at runtime.
license: Proprietary
compatibility: Repurposer launch_film tool (film_storyboarder agent prompt injection).
allowed-tools:
  - launch_film
metadata:
  version: "1.1.0"
  author: repurposer
  tags:
    - launch-film
    - storyboard
    - web-page-film
---

## Launch-film storyboard craft

A launch film is **an evidence-led telling**: within ninety seconds the
viewer must be able to answer "what is this, what does it do for me, where
do I go next". You are the editor, not the copywriter — every on-screen
word already exists on the page; your craft is choosing which line carries
each beat, and what the voiceover says while it shows.

### The narrative arc (the default scene order)

Target 75–95 seconds, 10–16 scenes, shaped as **pillar iteration**:

1. **Cold open** (1–2 `words` scenes): the page's most tension-loaded line,
   hammered out word by word, as few characters as possible.
2. **hero**: the product name + its tagline — one beat that stands.
3. **First ui**: the fold screenshot as the evidence shot.
4. **Pillar loop** (the page's claims decomposed into 2–4 pillars; one group
   per pillar): `divider` announces the chapter (the ordinal breathes) →
   `ui` proves it (the section shot where that pillar lives) → if the page
   carries numbers or specs for the pillar, insert one `plate`; skip it
   otherwise.
5. **Close**: `reveal` calls back the opening claim (optionally one more
   `ui` to cash the reveal's suspense) → `end` gives the name and where to
   go.

This is a default shape, not a cage — the material's character may rewrite
it (a pure-copy page may have no `ui` at all).

### Rhythm

- 75–95 seconds total: never shorter than 75 — a film that can't develop a
   single pillar is worse than none.
- The first 3 seconds decide everything: the cold-open `words` scenes get
   the shortest durations and the fewest characters.
- `ui` scenes are the film's slowest shots (the viewer is reading a
   screenshot): give them 6–10 seconds, and never chain two without a text
   scene to breathe between them.
- `plate` is scarce (at most 2 per film): only when the page truly offers
   numbers/specs; cards carry numbers and short labels, never sentences.
- The `end` card must hold: name + tagline, no third piece of information.

### Camera storytelling (ui scenes: focuses and frame)

- `focuses` are **the path of the gaze**: 1–3 per scene, opening wide then
  pushing into the region that is speaking; leave at least 2 seconds of air
  between two pushes.
- `frame` is a narrative choice: `frame: false` is the full-bleed immersive
  push (the page fills the canvas — the evidence climax); `frame: true` is
  the browser-chrome card (the "this is a real page" credibility beat).
  Mix both within one film.
- A caption landing exactly as the camera arrives at its subject reads best
  — where the camera goes, the words follow.
- Never move for motion's sake: one meaningful push beats three pans.

### Citation craft (choosing lines)

- `words` / `hero` / `reveal` lines must be **short enough to shout**;
  long lines belong in `sub`.
- Prefer h1/h2/button lines for text beats — they are written to be
  glanced; paragraphs are narration fuel, rarely screen copy.
- The divider `roll` is a same-semantic-plane enumeration (feature names /
  section headings), never a sentence.
- `plate` cards: `big` is a number or a very short mark ("256 B",
  "RFC 9180"), `label` one small line; no numbers on the page means no
  plate.
- A line appears once in the whole film — except a deliberate echo
  (opening hook → reveal callback), and an echo changes scene type rather
  than replaying the same one.
- Fit honestly: if the perfect line is a few characters over the cap, a
  `head`/`tail` fit that keeps a whole clause reads fine; if it would cut
  mid-thought, cite a different line.

### Naming

- `name` is the film's display name: read the page's temperament and coin a
  short one (≤ 24 chars); if nothing earns it, null — the system falls
  back to an honest parametric label, never a hard-coded one.
