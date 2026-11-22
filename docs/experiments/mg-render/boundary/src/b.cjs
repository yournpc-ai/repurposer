const fs=require('fs'),path=require('path');
const {bundle}=require('@remotion/bundler');
const {selectComposition,renderMedia,renderStill}=require('@remotion/renderer');
async function run(){
  const data=JSON.parse(fs.readFileSync('evidence/data.json'));
  for(const c of [data.pip,...data.spec.tracks.flatMap(t=>t.clips)])c.source.url=process.env.ASSET_URL+'/'+c.source.url;
  const base=path.resolve('cache/bundle');
  if(!fs.existsSync(base+'/index.html'))await bundle({entryPoint:path.resolve('src/root.tsx'),outDir:base,rootDir:process.cwd(),enableCaching:false,publicDir:null});
  const args={serveUrl:base,inputProps:{data},browserExecutable:process.env.CHROME,logLevel:'error',binariesDirectory:process.env.PROBE_BIN};
  const composition=await selectComposition({...args,id:'Boundary'});
  if(process.argv[2]==='still'){
    for(const k of process.argv.slice(3).map(Number))await renderStill({...args,composition,frame:k,imageFormat:'png',output:'cache/B-'+k+'.png'});
  }else await renderMedia({...args,composition,outputLocation:process.argv[2],codec:'h264',crf:18,x264Preset:'veryfast',imageFormat:'png',concurrency:2,offthreadVideoThreads:2,audioBitrate:'192k',sampleRate:48000,colorSpace:'bt709'});
}
run().catch(e=>{console.error(e);process.exitCode=1});
