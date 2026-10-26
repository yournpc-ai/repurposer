---
name: launch-film
description: Launch-film direction craft — pillar picking, hook writing, citation discipline, narration voice, naming. The film's structure is code-owned (fixed skeleton); this pack guides the slots the director answers. Woven into the launch_film tool's director prompt at assembly time; the model never loads it at runtime.
license: Proprietary
compatibility: Repurposer launch_film tool (film_director agent prompt injection).
allowed-tools:
  - launch_film
metadata:
  version: "1.2.0"
  author: repurposer
  tags:
    - launch-film
    - storyboard
    - web-page-film
---

## Launch-film direction craft

A launch film is **an evidence-led telling**: within ninety seconds the
viewer must be able to answer "what is this, what does it do for me, where
do I go next". The film's skeleton is fixed — a quiet cold open, the hero
card, a walk of the home page, one chapter per pillar (a divider, then a
walk; a numbers plate after chapter 1 when the page carries numbers), the
reveal, a proof walk, the closing card, 70–118 seconds in all. Everything
on screen is one of those elements — motion text, the brand hero, camera
walks over the page's real screenshots, chapter cards, a numbers-evidence
plate, the reveal and the closing card, plus the music bed, the spoken
narration and independent visible subtitles; the film never shows live-action footage,
staged scenes or camera work beyond these walks. You never
arrange scenes. Your craft is: **which chapters the film tells, which lines
carry the factual beats, how their short display titles read, where each
page walk focuses, what the creative channel says, and what the narration
and subtitles say.**

### Camera focus (the page walks)

- The home overview is a static establishing card: the system holds the wide fold for a short beat, no camera, no target. Your `camera_focuses` cover the chapter walks and the proof walk only — never name `home`.
- Judge the actual attached shot, the walk's chapter and its subtitle together. The right target is the element whose content best carries that beat, not simply the first recognized control.
- Keep meaningful reading context around the push. A small action label earns the focus when that action is the point of the beat; otherwise choose the copy or visual that explains the feature.

### Pillars (the chapters)

- Pick 3–5 pillars: the things the site itself leads with — its h1/h2/h3
  headings, not your taxonomy of the product. If the site leads with three
  ideas, three chapters it is.
- Their order is your narrative: strongest hook first, the most
  consequential claim last (the reveal lives right after).
- A long or flat pillar heading still works: the citation preserves its full
  source meaning, while your paired `chapter_titles` entry supplies a
  complete display title of at most 20 characters. Condense faithfully;
  never cut a heading into an unfinished clause.

### Citation craft (factual slots)

- `hero_word` / `reveal_word` must be **short enough to shout** — usually
  the product's name as the site writes it, brand casing intact. Long lines
  belong in `sub`.
- Prefer h1/h2/button lines for screen beats — they are written to be
  glanced; paragraphs are narration fuel, rarely screen copy.
- The reveal cites something true the site states but does not lead with:
  a free tier, a number, an integration, a surprising capability.
- Fit honestly: if the perfect line is a few characters over the cap, a
  `head`/`tail` fit that keeps a whole clause reads fine; if it would cut
  mid-thought, cite a different line.

### The creative channel (hooks, lead-ins — never claims)

- The cold open is the film's own voice: 1–3 lines, at most 3 words each
  (CJK: 8 characters). Rhythm, a question, a tease — the tension the page
  promises to resolve. It never states a product fact: no features,
  numbers, customers or promises. If a line could be fact-checked against
  the site, it does not belong here.
- `reveal_lead` is a lead-in, not a claim. Write a fresh, short transition
  suited to this film's tone and language; never lean on a stock catchphrase
  or leave the slot null. A factual tease is not a lead-in.
- Accent sparingly: one emphasized word per resolved line, the word that
  carries the beat.

### Narration (the spoken channel)

- Speech rephrases the page's facts into natural spoken language — TRUE to
  the manifest, in the film's language, never a claim the page does not
  make.
- The hero, the walks, the reveal and the end carry the story; dividers and
  the cold open usually play better silent.
- One thought per scene. ≤ 20 characters per second of the scene (CJK: ≈5
  characters per second — each glyph speaks a syllable). A line that cannot
  be read inside its scene's window is REJECTED at design time — write a
  shorter line or leave the scene silent; the scene's window never
  stretches for the words.

### Subtitles (the independent visible channel)

- New web films default to subtitles ON, with or without voiceover. Write
  one concise, complete `subtitle_lines` entry for every chapter walk, the
  proof walk and any numbers plate; these explanations still appear when
  the film has no spoken narration.
- Cold-open words, the hero, the home overview, chapter dividers, the
  reveal and the closing card already carry the introduction or typography
  as the picture. Omit their subtitle keys by default so they play without
  a duplicate text layer; an explicit user request can still add a subtitle
  to a named scene.
- Subtitle copy supports the picture instead of mechanically repeating its
  largest heading. Keep it true to the cited page and in the film's language.
- Author text only. The system owns cue splitting, timing and the default
  black-background / white-text style; never invent timestamps or tracks.

### Naming

- `name` is the film's display name: read the page's temperament and coin a
  short one (≤ 24 chars); if nothing earns it, null — the system falls
  back to an honest parametric label, never a hard-coded one.
