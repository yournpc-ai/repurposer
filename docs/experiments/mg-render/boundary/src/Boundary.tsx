import React from 'react';

export interface BoundaryProps {
  frame: number;
  headline: string;
  ink: string;
  rate: number;
}
export function Aperture({frame, rate, children}: Pick<BoundaryProps,'frame'|'rate'> & {children:React.ReactNode}) {
  const phase = frame * rate / 17;
  const cx = 49 + 22 * Math.sin(phase);
  const radius = 39 + 12 * Math.cos(phase * .8);
  return <div style={{position:'absolute',left:80,top:20,width:480,height:270,
    maskImage:`radial-gradient(ellipse at ${cx}% 49%, black ${radius}%, transparent ${radius + 17}%)`,
    clipPath:'polygon(0 0, 100% 0, 100% 73%, 84% 100%, 0 100%)'}}>{children}</div>;
}
export function Caption({frame,headline,ink}:BoundaryProps) {
  const progress=Math.max(0,Math.min(1,frame/18));
  return <svg width="580" height="310" style={{position:'absolute',inset:0}}>
    <defs><clipPath id="reveal"><rect x="8" y="170" width={425*progress} height="100"/></clipPath></defs>
    <g clipPath="url(#reveal)">
      <rect x="8" y="191" width="343" height="65" rx="8" fill="#09232d" fillOpacity=".76"/>
      <text x="23" y="235" fontFamily="Arial" fontWeight="700" fontSize="35" fill={ink}>{headline}</text>
    </g>
    <path d="M 55 171 L 86 142 L 137 142" fill="none" stroke={ink} opacity={progress} strokeWidth="3"/>
  </svg>;
}
