import React from 'react';
import {Composition, registerRoot, Sequence, useCurrentFrame} from 'remotion';
import {Video} from './Video';
import {Title} from './active-title';
function LiveTitle({mg}:any) {
  return <div style={{position:'absolute',left:mg.layout.x,top:mg.layout.y}}><Title {...mg.props} frame={useCurrentFrame()}/></div>;
}
function Work({spec,mg}:any) {
  return <><Video spec={spec}/>{mg && <Sequence from={mg.start} durationInFrames={mg.end-mg.start}><LiveTitle mg={mg}/></Sequence>}</>;
}
registerRoot(()=> <Composition id="Work" component={Work} durationInFrames={240} width={1920} height={1080} fps={30} defaultProps={{}} calculateMetadata={({props}:any)=>({width:props.spec.width,height:props.spec.height,fps:props.spec.fps.num/props.spec.fps.den,durationInFrames:props.spec.duration_frames})}/>);
