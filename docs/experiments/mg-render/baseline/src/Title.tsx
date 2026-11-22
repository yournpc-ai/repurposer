import React from 'react';

export type Ink = {headline:string, ink:string, rate:number};
export function Title({frame, headline, ink, rate}: Ink & {frame:number}) {
  const t = Math.min(1, frame * rate / 30);
  const rise = (1 - t) ** 3;
  const pulse = frame >= 30 && frame < 33;
  return <div style={{position:'relative',width:900,height:210,overflow:'hidden',background:'#142b30',color:'#f5f0da',fontFamily:'Arial',fontWeight:700}}>
    <div style={{position:'absolute',left:28,top:23,color:'#9cc7bd',fontSize:18,letterSpacing:3}}>FIELD NOTES　/　SIGNAL STUDY</div>
    <div style={{position:'absolute',left:28,top:59,width:840,height:91,clipPath:'inset(0 '+((1-t)*100)+'% 0 0)'}}>
      <div style={{fontSize:76,lineHeight:'91px',color:ink,transform:'translateY('+(rise*75)+'px)'}}>{headline}</div>
    </div>
    <div style={{position:'absolute',left:28,top:172,width:844,height:4,background:'#345458'}}>
      <div style={{width:(100*t)+'%',height:'100%',background:ink}}/>
    </div>
    <div style={{position:'absolute',right:30,top:24,width:22,height:22,background:pulse?'#ffffff':'#72928a'}}/>
  </div>;
}
