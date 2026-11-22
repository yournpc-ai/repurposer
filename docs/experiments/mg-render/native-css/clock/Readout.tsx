import React, {useLayoutEffect, useRef} from 'react';

// Chromium interpolates the clip frame as a number. CSS evaluates V7's curve.
CSS.registerProperty({name:'--title-frame', syntax:'<number>', inherits:false, initialValue:'0'});

type Props = {
  length:number, fps:{num:number, den:number}, headline:string, ink:string
};

export function Readout({length, fps, headline, ink}:Props) {
  const node = useRef<HTMLDivElement>(null);
  const ms = 1000 * fps.den / fps.num;
  useLayoutEffect(() => {
    const effect = new KeyframeEffect(node.current, [
      {'--title-frame':'0'}, {'--title-frame':String(length)}
    ], {duration:length * ms, fill:'both', easing:'linear'});
    const a = new Animation(effect, document.timeline);
    a.pause();
    a.currentTime = 0;
    return () => a.cancel();
  }, [length, ms]);
  return <div ref={node} style={{position:'absolute', top:157, left:14, padding:'12px 28px',
    backdropFilter:'blur(9px) saturate(2)', background:'rgba(12,36,43,.54)',
    borderLeft:`6px solid ${ink}`, color:ink, font:'bold 38px Arial',
    transform:'translateY(calc(10px * cos(calc(var(--title-frame) * 1rad / 16))))'}}>{headline}</div>;
}
