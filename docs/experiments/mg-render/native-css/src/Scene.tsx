import React from 'react';
import {Readout,Sweep} from './Blocks';

import {aperture} from './aperture';

export function Scene({data,k,media}:any) {
  return <div style={{position:'absolute',inset:0,overflow:'hidden',isolation:'isolate',background:data.background}}>
    {data.tracks.filter((t:any)=>t.kind==='visual').slice().sort((a:any,b:any)=>a.order-b.order).flatMap((track:any)=>
      track.clips.filter((c:any)=>c.start_frame<=k && k<c.end_frame).map((c:any)=>{
        const o=c.object, frame=k-c.start_frame, box=o.layout;
        const mask=o.object_id===data.target ? aperture(frame) : {};
        const Block=o.entry==='Sweep' ? Sweep : Readout;
        return <div key={o.object_id} data-object={o.object_id} style={{position:'absolute',left:box.x,top:box.y,
          width:box.width,height:box.height,...mask,...(o.entry==='Sweep'?{mixBlendMode:'difference'}:{})}}>
          {o.kind==='video' ? media(c,frame) : <Block {...o.props} frame={frame}/>}
        </div>;
      }))}
  </div>;
}
