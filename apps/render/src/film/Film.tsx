// Film sequencer — lays the storyboard's scenes back-to-back on the output
// timeline, each under its own Fade veil. Durations are the spec's integer
// frames, summed as-is (allocation happened upstream; nothing is derived here).
import React from "react";
import { AbsoluteFill, Sequence } from "remotion";

import { Divider, End, Fade, Hero, Reveal, UiScene, Words } from "./components";
import type { FilmSpec } from "./schema";

export const Film: React.FC<{ spec: FilmSpec }> = ({ spec }) => {
  let cursor = 0;
  return (
    <AbsoluteFill style={{ background: spec.theme.canvas }}>
      {spec.scenes.map((s, i) => {
        const start = cursor;
        const dur = s.frames;
        cursor += dur;
        return (
          <Sequence key={i} from={start} durationInFrames={dur}>
            <Fade dur={dur}>
              {s.type === "words" && <Words lines={s.lines} dark={s.dark} theme={spec.theme} />}
              {s.type === "hero" && <Hero word={s.word} sub={s.sub} theme={spec.theme} />}
              {s.type === "ui" && (
                <UiScene
                  image={s.image}
                  url={s.url}
                  focuses={s.focuses}
                  captions={s.captions}
                  theme={spec.theme}
                  dur={dur}
                />
              )}
              {s.type === "divider" && (
                <Divider index={s.index} label={s.label} roll={s.roll} theme={spec.theme} />
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
