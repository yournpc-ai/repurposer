import React from 'react';
import {Composition,OffthreadVideo,Sequence,registerRoot,useCurrentFrame} from 'remotion';
import {Scene} from './Scene';

function Reference({data,base}:any) {
  return <Scene data={data} k={useCurrentFrame()} media={(c:any)=>
    <Sequence from={c.start_frame} layout="none">
      <OffthreadVideo muted src={base+'/'+c.source.url} startFrom={c.source.start_frame}
        style={{width:'100%',height:'100%',display:'block'}}/>
    </Sequence>}/>;
}
registerRoot(()=> <Composition id="Native" component={Reference} width={1920} height={1080}
  durationInFrames={240} fps={30} defaultProps={{}}/>);
