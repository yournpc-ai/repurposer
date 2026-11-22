import React from 'react';
import {createRoot} from 'react-dom/client';
import {Player, PlayerRef} from '@remotion/player';
import {Scene} from './scene';
const player=React.createRef<PlayerRef>();
(window as any).mount=(data:any)=>{
  const slider=document.querySelector('input')!;
  slider.oninput=()=>player.current!.seekTo(Number(slider.value));
  createRoot(document.querySelector('#view')!).render(<Player component={Scene} ref={player}
    compositionWidth={1920} compositionHeight={1080} fps={30} durationInFrames={240}
    style={{width:1920,height:1080}} inputProps={{data}}/>);
};
(window as any).current=()=>player.current?.getCurrentFrame();
