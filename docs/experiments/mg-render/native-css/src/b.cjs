const fs=require('fs'),path=require('path');
const {bundle}=require('@remotion/bundler');
const {selectComposition,renderMedia,renderStill}=require('@remotion/renderer');
async function main(){
  const [version,mode,...frames]=process.argv.slice(2);
  const data=JSON.parse(fs.readFileSync('cache/data'+version+'.json'));
  const serveUrl=path.resolve('cache/bundle');
  if(!fs.existsSync(serveUrl+'/index.html'))await bundle({entryPoint:path.resolve('src/B.tsx'),outDir:serveUrl,rootDir:process.cwd(),publicDir:null,enableCaching:false});
  const opts={serveUrl,id:'Native',inputProps:{data,base:process.env.ASSET_URL},browserExecutable:process.env.CHROME,logLevel:'error'};
  const composition=await selectComposition(opts);
  if(mode==='still'){
    for(const k of frames)await renderStill({...opts,composition,frame:+k,output:'cache/B-'+k+'.png',imageFormat:'png'});
  }else await renderMedia({...opts,composition,codec:'h264',muted:true,crf:18,x264Preset:'veryfast',colorSpace:'bt709',imageFormat:'png',concurrency:2,offthreadVideoThreads:2,outputLocation:'cache/silent.mp4'});
}
main().catch(e=>{console.error(e);process.exitCode=1});
