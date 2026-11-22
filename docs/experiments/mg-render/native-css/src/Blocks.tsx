import React from 'react';

type Props = {frame:number, headline:string, ink:string, rate:number};

export function Sweep({frame, rate, ink}:Props) {
  return <div style={{position:'absolute', left:12, top:65, width:465, height:88,
    background:ink, opacity:.88,
    transform:`translateX(${32*Math.sin(frame*rate/13)}px) rotate(-7deg)`}}/>;
}

export function Readout({frame, headline, ink}:Props) {
  return <div style={{position:'absolute', top:157, left:14, padding:'12px 28px',
    backdropFilter:'blur(9px) saturate(2)', background:'rgba(12,36,43,.54)',
    borderLeft:`6px solid ${ink}`, color:ink, font:'bold 38px Arial',
    transform:`translateY(${10*Math.cos(frame/16)}px)`}}>{headline}</div>;
}
