// Spike MG film engine — the component vocabulary is authored by us; the
// storyboard (scene order, copy, camera plan) is the spec an LLM would fill.
// Scenes: words / hero / ui / divider / reveal / end. Landscape 1920×1080@30.
import React from 'react';
import {
  AbsoluteFill, Composition, Img, Sequence, Easing, interpolate, spring,
  staticFile, useCurrentFrame, useVideoConfig, registerRoot,
} from 'remotion';

type Theme = { canvas: string; ink: string; accent: string };
const FONT = "-apple-system, 'Helvetica Neue', 'Segoe UI', Arial, sans-serif";

/** *word* → highlight chip (ink tile + canvas text — our monochrome accent). */
const accentize = (line: string, dark: boolean, theme: Theme) =>
  line.split(/\*([^*]+)\*/g).map((p, i) =>
    i % 2 ? (
      <span
        key={i}
        style={{
          background: dark ? theme.canvas : theme.ink,
          color: dark ? theme.ink : theme.canvas,
          borderRadius: '0.18em',
          padding: '0 0.22em',
        }}
      >
        {p}
      </span>
    ) : (
      p
    )
  );

const enter = (frame: number, delay: number, fps: number) => {
  const p = spring({ frame: frame - delay, fps, config: { damping: 200 } });
  return { opacity: p, transform: `translateY(${(1 - p) * 46}px)`, filter: `blur(${(1 - p) * 10}px)` };
};

const Words: React.FC<{ lines: string[]; dark: boolean; theme: Theme }> = ({ lines, dark, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: dark ? theme.ink : theme.canvas, justifyContent: 'center', paddingLeft: 220 }}>
      {lines.map((l, i) => (
        <div
          key={i}
          style={{
            fontFamily: FONT, fontWeight: 800, fontSize: 168, letterSpacing: '-0.035em',
            lineHeight: 1.04, color: dark ? theme.canvas : theme.ink, ...enter(frame, i * 8, fps),
          }}
        >
          {accentize(l, dark, theme)}
        </div>
      ))}
    </AbsoluteFill>
  );
};

const Hero: React.FC<{ word: string; sub: string; theme: Theme }> = ({ word, sub, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const settle = interpolate(frame, [0, 24], [1.07, 1], { extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) });
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 200, letterSpacing: '-0.04em', color: theme.ink, transform: `scale(${settle})` }}>
        {word}
      </div>
      <div style={{ fontFamily: FONT, fontSize: 44, color: '#6b6b6b', marginTop: 26, ...enter(frame, 10, fps) }}>{sub}</div>
    </AbsoluteFill>
  );
};

const Divider: React.FC<{ index: string; label: string; roll: string[]; theme: Theme }> = ({ index, label, roll, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const perWord = 13;
  return (
    <AbsoluteFill style={{ background: theme.ink }}>
      <div style={{ position: 'absolute', top: 110, left: 140, fontFamily: FONT, fontSize: 44, color: '#888' }}>{index}</div>
      <div style={{ position: 'absolute', top: 200, left: 220, fontFamily: FONT, fontSize: 54, fontWeight: 600, color: '#999', ...enter(frame, 0, fps) }}>
        {label}
      </div>
      <div style={{ position: 'absolute', top: 300, left: 220, right: 220, height: 220, overflow: 'hidden' }}>
        {roll.map((w, i) => {
          const start = i * perWord;
          const isLast = i === roll.length - 1;
          const p = spring({ frame: frame - start, fps, config: { damping: 200 } });
          const out = isLast ? 0 : spring({ frame: frame - (start + perWord), fps, config: { damping: 200 } });
          const y = (1 - p) * 90 - out * 90;
          const blur = Math.max(0, Math.max((1 - p) * 8, out * 8));
          if (frame < start - 1 || (!isLast && frame > start + perWord + 12)) return null;
          return (
            <div
              key={i}
              style={{
                position: 'absolute', fontFamily: FONT, fontWeight: 800, fontSize: 150, letterSpacing: '-0.03em',
                color: isLast ? theme.canvas : '#777', transform: `translateY(${y}px)`, filter: `blur(${blur}px)`, opacity: p - out,
              }}
            >
              {w}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const UI: React.FC<{
  image: string; url: string; theme: Theme; dur: number;
  focuses: { at: number; x: number; y: number; zoom: number }[];
  captions: { at: number; text: string }[];
}> = ({ image, url, theme, dur, focuses, captions }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const W = 1440, H = 900;
  const ts = focuses.map((f) => f.at);
  const x = interpolate(t, ts, focuses.map((f) => f.x), { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const y = interpolate(t, ts, focuses.map((f) => f.y), { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const z = interpolate(t, ts, focuses.map((f) => f.zoom), { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.inOut(Easing.cubic) });
  const inP = spring({ frame, fps, config: { damping: 200 } });
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: 'center', alignItems: 'center' }}>
      <div
        style={{
          width: W, background: 'white', borderRadius: 26, overflow: 'hidden',
          boxShadow: '0 40px 120px rgba(20,20,20,0.16), 0 4px 18px rgba(20,20,20,0.08)',
          border: '1px solid rgba(20,20,20,0.08)',
          transform: `translateY(${(1 - inP) * 60}px) scale(${0.96 + inP * 0.04})`, opacity: inP,
        }}
      >
        {/* browser chrome */}
        <div style={{ height: 58, display: 'flex', alignItems: 'center', gap: 10, padding: '0 22px', borderBottom: '1px solid rgba(20,20,20,0.07)', background: '#fbfbfa' }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ width: 16, height: 16, borderRadius: 99, background: '#e2e1de' }} />
          ))}
          <div style={{ marginLeft: 18, background: 'white', border: '1px solid rgba(20,20,20,0.08)', borderRadius: 12, padding: '6px 18px', fontFamily: FONT, fontSize: 22, color: '#666' }}>
            {url}
          </div>
        </div>
        {/* viewport with camera */}
        <div style={{ width: W, height: H, overflow: 'hidden', position: 'relative' }}>
          <Img
            src={staticFile(image)}
            style={{
              width: W, height: H, transformOrigin: '0 0',
              transform: `translate(${W / 2 - x * W * z}px, ${H / 2 - y * H * z}px) scale(${z})`,
            }}
          />
        </div>
      </div>
      {captions.map((c, i) => {
        const startF = c.at * fps;
        const endF = (captions[i + 1]?.at ?? dur / fps - 0.3) * fps;
        if (frame < startF - 1 || frame > endF) return null;
        const p = spring({ frame: frame - startF, fps, config: { damping: 200 } });
        const out = interpolate(frame, [endF - 8, endF], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
        return (
          <div
            key={i}
            style={{
              position: 'absolute', bottom: 44, left: 0, right: 0, display: 'flex', justifyContent: 'center',
              opacity: p * (1 - out), transform: `translateY(${(1 - p) * 30}px)`,
            }}
          >
            <div style={{ background: '#141414', color: '#f7f6f2', borderRadius: 999, padding: '16px 40px', fontFamily: FONT, fontSize: 34, fontWeight: 600 }}>
              {c.text}
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const Reveal: React.FC<{ lead: string; word: string; sub: string; theme: Theme }> = ({ lead, word, sub, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ fontFamily: FONT, fontSize: 40, color: '#8a8a8a', marginBottom: 30, ...enter(frame, 0, fps) }}>{lead}</div>
      <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 150, letterSpacing: '-0.03em', color: theme.ink, ...enter(frame, 6, fps) }}>
        {accentize(word, false, theme)}
      </div>
      <div style={{ fontFamily: FONT, fontSize: 40, color: '#6b6b6b', marginTop: 30, ...enter(frame, 14, fps) }}>{sub}</div>
    </AbsoluteFill>
  );
};

const End: React.FC<{ name: string; tagline: string; url: string; theme: Theme }> = ({ name, tagline, url, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: theme.canvas, justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 28, ...enter(frame, 0, fps) }}>
        <Img src={staticFile('favicon.svg')} style={{ width: 92, height: 92 }} />
        <div style={{ fontFamily: FONT, fontWeight: 800, fontSize: 110, letterSpacing: '-0.035em', color: theme.ink }}>{name}</div>
      </div>
      <div style={{ fontFamily: FONT, fontSize: 40, color: '#6b6b6b', marginTop: 26, ...enter(frame, 8, fps) }}>{tagline}</div>
      <div style={{ fontFamily: FONT, fontSize: 30, color: '#9a9a9a', marginTop: 54, ...enter(frame, 16, fps) }}>{url}</div>
    </AbsoluteFill>
  );
};

const Fade: React.FC<{ dur: number; children: React.ReactNode }> = ({ dur, children }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [0, 7], [0, 1], { extrapolateRight: 'clamp' });
  const out = interpolate(frame, [dur - 7, dur - 1], [1, 0], { extrapolateLeft: 'clamp' });
  return <AbsoluteFill style={{ opacity: Math.min(o, 1) * out }}>{children}</AbsoluteFill>;
};

const Film: React.FC<{ storyboard: any }> = ({ storyboard }) => {
  const { fps } = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={{ background: storyboard.theme.canvas }}>
      {storyboard.scenes.map((s: any, i: number) => {
        const start = cursor;
        const dur = Math.round(s.seconds * fps);
        cursor += dur;
        return (
          <Sequence key={i} from={start} durationInFrames={dur}>
            <Fade dur={dur}>
              {s.type === 'words' && <Words lines={s.lines} dark={s.dark} theme={storyboard.theme} />}
              {s.type === 'hero' && <Hero word={s.word} sub={s.sub} theme={storyboard.theme} />}
              {s.type === 'ui' && <UI image={s.image} url={s.url} focuses={s.focuses} captions={s.captions} theme={storyboard.theme} dur={dur} />}
              {s.type === 'divider' && <Divider index={s.index} label={s.label} roll={s.roll} theme={storyboard.theme} />}
              {s.type === 'reveal' && <Reveal lead={s.lead} word={s.word} sub={s.sub} theme={storyboard.theme} />}
              {s.type === 'end' && <End name={s.name} tagline={s.tagline} url={s.url} theme={storyboard.theme} />}
            </Fade>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

import storyboard from './storyboard.json';

const FPS = 30;
const totalFrames = Math.round(storyboard.scenes.reduce((a: number, s: any) => a + s.seconds, 0) * FPS);

const Root: React.FC = () => (
  <Composition
    id="LaunchFilm"
    component={Film as any}
    durationInFrames={totalFrames}
    fps={FPS}
    width={1920}
    height={1080}
    defaultProps={{ storyboard }}
  />
);

registerRoot(Root);
