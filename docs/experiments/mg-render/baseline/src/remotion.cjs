const fs=require('fs'),path=require('path'),crypto=require('crypto');
const {bundle}=require('@remotion/bundler');
const {renderMedia,renderStill,selectComposition}=require('@remotion/renderer');
async function run(){
 const [route,v,output,mode]=process.argv.slice(2);
 const read=f=>JSON.parse(fs.readFileSync(f));
 const props=read('fixture/'+(route==='A'?'baked':'direct')+v+'.json');
 for(const track of props.spec.tracks)for(const clip of track.clips)if(clip.source)clip.source.url=process.env.ASSET_URL+'/'+clip.source.url;
 const req=read('fixture/request'+v+'.json');
 const title=route==='A'?'export const Title=()=>null;':req.project.files.find(x=>x.path==='Title.tsx').content;
 const h=crypto.createHash('sha256').update(title+fs.readFileSync('src/RemotionRoot.tsx')+fs.readFileSync('src/Video.tsx')).digest('hex');
 const base=path.resolve('cache',route+h.slice(0,16)), serveUrl=path.join(base,'dist');
 if(!fs.existsSync(path.join(base,'complete'))){
   fs.mkdirSync(base,{recursive:true});
   fs.copyFileSync('src/RemotionRoot.tsx',base+'/entry.tsx');fs.copyFileSync('src/Video.tsx',base+'/Video.tsx');fs.cpSync('src/video-spec',base+'/video-spec',{recursive:true});
   fs.writeFileSync(base+'/active-title.tsx',title);
   const t=Date.now();
   await bundle({entryPoint:base+'/entry.tsx',outDir:serveUrl,publicDir:null,enableCaching:false,rootDir:process.cwd()});
   fs.writeFileSync(base+'/complete','ok');console.log('bundle_ms',Date.now()-t);
 }
 const args={serveUrl,inputProps:props,browserExecutable:process.env.CHROME,logLevel:'error'};
 const composition=await selectComposition({...args,id:'Work'});
 if(mode==='preview') await renderStill({...args,composition,frame:60,imageFormat:'png',output:output});
 else await renderMedia({...args,composition,codec:'h264',outputLocation:output,crf:18,x264Preset:'veryfast',imageFormat:'png',pixelFormat:'yuv420p',concurrency:2,offthreadVideoThreads:2,sampleRate:48000,audioBitrate:'192k',colorSpace:'bt709'});
}
run().catch(e=>{console.error(e);process.exitCode=1});
