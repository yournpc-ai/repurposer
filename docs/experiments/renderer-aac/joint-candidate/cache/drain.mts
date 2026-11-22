import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
const base=process.env.LAB!, app=process.cwd(), old=path.join(base,'cache/v1/apps/render');
const spec=createRequire(path.join(app,'package.json'))('@repurposer/video-spec').videoSpecSchema.parse(JSON.parse(await fs.readFile(base+'/mac/mix.json','utf8')));
const ports=[49901,49902], servers=[], puts=[], events=[];
const hash=buf=>createHash('sha256').update(buf).digest('hex');
const sink=createServer(async(req,res)=>{const parts=[];for await(const b of req)parts.push(b);puts.push({method:req.method,key:req.url,sha:hash(Buffer.concat(parts))});res.end()});
await new Promise(ok=>sink.listen(49903,'127.0.0.1',ok));
const seed=async(root,id,file)=>{const {renderArtifacts}=await import(path.join(root,'src/artifacts.ts'));await renderArtifacts({id,spec},async dir=>{const videoPath=path.join(dir,'video.mp4');await fs.copyFile(file,videoPath);return {videoPath}});return hash(await fs.readFile(file))};
const req=async(i,id)=>{const r=await fetch('http://127.0.0.1:'+ports[i]+'/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({spec,render_id:id,outputs:{video:{key:id,create_only:true,upload_id:id,put_url:'http://127.0.0.1:49903/'+id}}})});events.push({id,version:i+1,status:r.status,response:await r.json(),puts:puts.length});return r.status};
try{
 for(const [i,root] of [old,app].entries()){
 const srv=spawn(app+'/node_modules/.bin/tsx',['src/server.ts'],{cwd:root,env:{...process.env,RENDER_PORT:String(ports[i])},detached:true,stdio:'ignore'});servers.push(srv);
 for(let a=0;a<100;a++){try{if((await fetch('http://127.0.0.1:'+ports[i]+'/health')).ok)break}catch{} await new Promise(ok=>setTimeout(ok,100))}
 }
 const oldSha=await seed(old,'old-prepared',process.env.OLD_MEDIA);
 if(await req(1,'old-prepared')!==409||puts.length)throw Error('expected clean cache miss');
 if(await req(0,'old-prepared')!==200||puts.length!==1||puts[0].sha!==oldSha)throw Error('drain failed');
 const newSha=await seed(app,'new-after-drain',base+'/mac/run/success/video.mp4');
 if(await req(1,'new-after-drain')!==200||puts.length!==2||puts[1].sha!==newSha)throw Error('new upload failed');
 console.log(JSON.stringify({events,puts,oldSha,newSha},null,2));
}finally{for(const srv of servers)process.kill(-srv.pid,'SIGTERM');sink.closeAllConnections();sink.close()}
