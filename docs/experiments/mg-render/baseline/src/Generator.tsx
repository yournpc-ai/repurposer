import React from 'react';
import {Composition, registerRoot, useCurrentFrame} from 'remotion';
import {Title, type Ink} from './Title';
function TimedTitle(props:Ink) {return <Title {...props} frame={useCurrentFrame()}/>;}
registerRoot(()=> <Composition id="SignalTitle" component={TimedTitle} width={900} height={210} durationInFrames={150} fps={30} defaultProps={{headline:'Parallel signals',ink:'#e5d392',rate:1}}/>);
