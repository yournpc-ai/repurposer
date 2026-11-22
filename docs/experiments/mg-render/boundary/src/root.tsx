import React from 'react';
import {Composition,registerRoot} from 'remotion';
import {Scene} from './scene';
registerRoot(()=> <Composition id="Boundary" component={Scene} durationInFrames={240} width={1920} height={1080} fps={30} defaultProps={{}}/>);
