import React from 'react';
import {OffthreadVideo, Sequence, useCurrentFrame} from 'remotion';
import {Video} from './Video';
import {Aperture,Caption} from './Boundary';

function Inset({data}:any) {
  const k=useCurrentFrame();
  const {pip,mg}=data;
  const local=k+pip.start_frame-mg.start;
  const {x,y,width,height}=pip.object.layout;
  const video=<OffthreadVideo src={pip.source.url} startFrom={pip.source.start_frame} muted style={{width,height,display:'block'}}/>;
  if(local<0 || local>=mg.end-mg.start)return <div style={{position:'absolute',left:x,top:y}}>{video}</div>;
  const props={...mg.props,frame:local};
  return <div style={{position:'absolute',left:mg.layout.x,top:mg.layout.y}}>
    <Aperture {...props}>{video}</Aperture><Caption {...props}/>
  </div>;
}
export function Scene({data}:any){
  const p=data.pip;
  return <><Video spec={data.spec}/><Sequence from={p.start_frame} durationInFrames={p.end_frame-p.start_frame}><Inset data={data}/></Sequence></>;
}
