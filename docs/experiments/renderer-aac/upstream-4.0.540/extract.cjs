const fs=require('node:fs');const path=require('node:path');
const [dist,src,out]=process.argv.slice(2);const {startLongRunningCompositor}=require(path.resolve(dist,'compositor/compositor.js'));
const c=startLongRunningCompositor({extraThreads:1,maximumFrameCacheItemsInBytes:null,indent:false,logLevel:'error',binariesDirectory:null});
(async()=>{try{fs.writeFileSync(out,await c.executeCommand('ExtractFrame',{src,original_src:src,time:0.5,transparent:false,tone_mapped:true}));}finally{await c.shutDownOrKill()}})().catch(e=>{console.error(e);process.exitCode=1});
