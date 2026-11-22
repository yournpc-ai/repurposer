const fs=require('fs'),build=require('esbuild'),path=require('path');
const base='cache/player';fs.mkdirSync(base,{recursive:true});
const original=fs.readFileSync('src/RemotionRoot.tsx','utf8').split('registerRoot(()=>')[0].replace("'./Video'","'../../src/Video'").replace("'./active-title'","'../../src/TitleV2'");
const body=`
import {Player} from '@remotion/player';
import {createRoot} from 'react-dom/client';
const ref=React.createRef<any>();
window.mount=(props)=>createRoot(document.getElementById('root')).render(<Player ref={ref} component={Work} durationInFrames={props.spec.duration_frames} fps={30} compositionWidth={1920} compositionHeight={1080} initialFrame={60} inputProps={props} style={{width:1920,height:1080}}/>);
window.move=(n)=>ref.current.seekTo(n);
window.current=()=>ref.current?.getCurrentFrame();
`;
fs.writeFileSync(base+'/entry.tsx',original+body);
build.buildSync({entryPoints:[base+'/entry.tsx'],bundle:true,outfile:base+'/player.js',define:{'process.env.NODE_ENV':'"production"'}});
