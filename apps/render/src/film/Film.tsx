// Film sequencer — lays the storyboard's scenes back-to-back on the output
// timeline, each under its own Fade veil. Durations are the spec's integer
// frames, summed as-is (allocation happened upstream; nothing is derived here).
//
// Audio (ADR-120 E2): the music bed sits at the root (loop, gain from the
// spec — the clip family's ClipMusic semantics); each scene's narration
// rides an <Audio> INSIDE its Sequence, so the scene boundary trims the
// voiceover honestly.
import React from "react";
import { AbsoluteFill, Audio, Sequence } from "remotion";

import { Divider, End, Fade, Hero, Plate, Reveal, UiScene, Words } from "./components";
import type { FilmSpec } from "./schema";

export const Film: React.FC<{ spec: FilmSpec }> = ({ spec }) => {
  let cursor = 0;
  const musicVolume = Math.min(1, Math.pow(10, (spec.music?.gain_db ?? -20) / 20));
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
            <Fade dur={dur}>
              {s.type === "words" && <Words lines={s.lines} dark={s.dark} theme={spec.theme} />}
              {s.type === "hero" && <Hero word={s.word} sub={s.sub} theme={spec.theme} />}
              {s.type === "ui" && (
                <UiScene
                  image={s.image}
                  url={s.url}
                  frame={s.frame}
                  focuses={s.focuses}
                  captions={s.captions}
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
                <Reveal lead={s.lead} word={s.word} sub={s.sub} theme={spec.theme} />
              )}
              {s.type === "end" && (
                <End name={s.name} tagline={s.tagline} url={s.url} logoUrl={s.logo_url} theme={spec.theme} />
              )}
            </Fade>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
