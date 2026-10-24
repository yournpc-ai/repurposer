// Film sequencer — lays the storyboard's scenes back-to-back on the output
// timeline, each under its own Fade veil. Durations are the spec's integer
// frames, summed as-is (allocation happened upstream; nothing is derived here).
//
// Audio (ADR-130): the music bed sits at the root (loop, gain from the
// spec — the clip family's ClipMusic semantics); each scene's narration
// rides an <Audio> INSIDE its Sequence, so the scene boundary trims the
// voiceover honestly. The narration's deterministic subtitle cues overlay
// the same scene window (the spec carries the cue times; no ASR here).
import React from "react";
import { AbsoluteFill, Audio, Sequence } from "remotion";

import { Captions, CompositeScene, Divider, End, Fade, Hero, Plate, Reveal, UiScene, Words } from "./components";
import type { FilmSpec } from "./schema";

export const Film: React.FC<{ spec: FilmSpec }> = ({ spec }) => {
  let cursor = 0;
  const musicVolume = Math.min(1, Math.pow(10, (spec.music?.gain_db ?? -20) / 20));
  // The reveal's black beat = the bed's REAL beat interval (ADR-130): bpm
  // when the grid carries it, else the beats array's median gap — the spec
  // rides the one resolved grid, so the renderer never re-analyzes. No bed
  // → 0: the lead hands straight to the word, no fabricated pause.
  const beatFrames = (() => {
    const m = spec.music;
    if (!m) return 0;
    if (m.bpm && m.bpm > 0) return Math.round((60 / m.bpm) * spec.fps);
    const beats = m.beats ?? [];
    if (beats.length >= 2) {
      const gaps = beats
        .slice(1)
        .map((b, i) => b - beats[i])
        .filter((g) => g > 0)
        .sort((a, b) => a - b);
      if (gaps.length) return Math.round(gaps[Math.floor(gaps.length / 2)] * spec.fps);
    }
    return 0;
  })();
  return (
    <AbsoluteFill style={{ background: spec.theme.canvas }}>
      {spec.music ? <Audio src={spec.music.url} volume={musicVolume} loop /> : null}
      {spec.scenes.map((s, i) => {
        const start = cursor;
        const dur = s.frames;
        cursor += dur;
        return (
          <Sequence key={i} from={start} durationInFrames={dur}>
            {s.audio ? <Audio src={s.audio} /> : null}
            {/* Words/composite scenes paint their polarity background at
                CONSTANT opacity outside the veil — the Fade covers only the
                content, so a dark scene's boundary never dips toward the
                white root canvas (a polarity flip reads as a hard cut; the
                text crossfades within its own scene). */}
            {s.type === "words" && (
              <AbsoluteFill
                style={{ background: s.dark ? spec.theme.ink : spec.theme.canvas }}
              />
            )}
            {s.type === "composite" && (
              <AbsoluteFill
                style={{ background: s.dark ? spec.theme.ink : spec.theme.canvas }}
              />
            )}
            {/* Veil ownership: a words plane with an EXPLICIT entrance
                (timing keys or enter_style) owns its in-edge, one with
                exit_duration owns its out-edge — the scene veil never
                doubles them. A composite scene's veil is PER-ELEMENT (inside
                CompositeScene), so one element's exit fade never washes its
                siblings; the scene-level veil steps aside there. */}
            <Fade
              dur={dur}
              fadeIn={
                s.type === "composite"
                  ? 0
                  : s.type === "words" &&
                      (s.enter_start != null ||
                        s.enter_interval != null ||
                        s.enter_duration != null ||
                        s.enter_hold_until != null ||
                        s.enter_style != null)
                    ? 0
                    : 7
              }
              fadeOut={
                s.type === "composite"
                  ? 0
                  : s.type === "words" && s.exit_duration != null
                    ? 0
                    : 7
              }
            >
              {s.type === "words" && (
                <Words
                  lines={s.lines}
                  dark={s.dark}
                  theme={spec.theme}
                  motion={s.motion}
                  enterMode={s.enter}
                  enterStart={s.enter_start}
                  enterInterval={s.enter_interval}
                  enterDuration={s.enter_duration}
                  enterHoldUntil={s.enter_hold_until}
                  motionStart={s.motion_start}
                  motionEnd={s.motion_end}
                  exitDuration={s.exit_duration}
                  motionScale={s.motion_scale}
                  align={s.align}
                  size={s.size}
                  accentStyle={s.accent_style}
                  enterStyle={s.enter_style}
                  dur={dur}
                />
              )}
              {s.type === "hero" && <Hero word={s.word} sub={s.sub} theme={spec.theme} />}
              {s.type === "ui" && (
                <UiScene
                  image={s.image}
                  url={s.url}
                  frame={s.frame}
                  focuses={s.focuses}
                  theme={spec.theme}
                  dur={dur}
                />
              )}
              {s.type === "divider" && (
                <Divider index={s.index} label={s.label} roll={s.roll} theme={spec.theme} />
              )}
              {s.type === "plate" && (
                <Plate title={s.title} cards={s.cards} backdrop={s.backdrop} />
              )}
              {s.type === "reveal" && (
                <Reveal lead={s.lead} leadFrames={s.lead_frames} word={s.word} sub={s.sub} theme={spec.theme} beatFrames={beatFrames} />
              )}
              {s.type === "composite" && (
                <CompositeScene
                  dark={s.dark}
                  elements={s.elements}
                  theme={spec.theme}
                  dur={dur}
                />
              )}
              {s.type === "end" && (
                <End name={s.name} tagline={s.tagline} url={s.url} logoUrl={s.logo_url} theme={spec.theme} />
              )}
            </Fade>
            {s.captions.length ? (
              // ``captions`` IS the narration cue track — the one and only
              // caption field (code-projected from the scene's narration).
              <Captions cues={s.captions} dur={dur} />
            ) : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
