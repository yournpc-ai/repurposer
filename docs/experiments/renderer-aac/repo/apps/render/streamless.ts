import {normalizeLoudness} from './src/audio';
await normalizeLoudness(process.env.LAB+'/run/streamless/video.mp4');
console.log('streamless returned');
