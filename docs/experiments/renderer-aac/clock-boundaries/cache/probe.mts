import * as v1 from './v1';
import * as v2 from './v2';
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
const root=process.env.FIXTURE!, repo=path.join(root,'repo/apps/render');
const require=createRequire(path.join(repo,'package.json'));
const {videoSpecSchema}=require('@repurposer/video-spec');
const spec=videoSpecSchema.parse(JSON.parse(await fs.readFile(path.join(root,'mix.json'),'utf8')));
const id={id:'isolated-cache-cutover',spec};let puts=0;
const sink=createServer((req,res)=>{req.resume();req.on('end',()=>{puts++;res.end()})});
await new Promise(ok=>sink.listen(49892,'127.0.0.1',ok));
const srv=spawn('./node_modules/.bin/tsx',['src/server.ts'],{cwd:repo,env:{...process.env,RENDER_PORT:'49891'},detached:true,stdio:'ignore'});
const sleep=(ms:number)=>new Promise(ok=>setTimeout(ok,ms));
const seed=(version,output)=>version.renderArtifacts(id,async dir=>{
 const videoPath=path.join(dir,'video.mp4');await fs.copyFile(path.join(root,'run',output,'video.mp4'),videoPath);return {videoPath};
});
const upload=async()=>{
 const r=await fetch('http://127.0.0.1:49891/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({render_id:id.id,spec,outputs:{video:{key:'fixture.mp4',put_url:'http://127.0.0.1:49892/fixture.mp4'}}})});
 return {status:r.status,body:await r.json(),puts};
};
try{
 for(let i=0;i<100;i++){try{await fetch('http://127.0.0.1:49891/health');break}catch{await sleep(100)}}
 const old=await seed(v1,'oldFirst');const miss=await v2.cachedArtifacts(id);const first=await upload();
 const next=await seed(v2,'newFirst');const second=await upload();
 if(miss!==null||first.status!==409||first.puts!==0||second.status!==200||puts!==1) throw Error(JSON.stringify({first,second}));
 const hash=async(p)=>createHash('sha256').update(await fs.readFile(p)).digest('hex');
 console.log(JSON.stringify({oldKey:path.basename(path.dirname(old.videoPath)),newKey:path.basename(path.dirname(next.videoPath)),oldStillPresent:await hash(old.videoPath),newSha:await hash(next.videoPath),first,second},null,2));
}finally{process.kill(-srv.pid!,'SIGTERM');sink.closeAllConnections();sink.close()}
