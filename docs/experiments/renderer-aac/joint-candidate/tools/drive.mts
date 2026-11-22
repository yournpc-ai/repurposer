import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=process.cwd(), dir=process.env.LAB!;
const require=createRequire(path.join(root,'package.json'));
const {renderVideo}=await import(pathToFileURL(path.join(root,'src/video/index.ts')).href);
const {videoSpecSchema}=require('@repurposer/video-spec'),express=require('express'),app=express();
app.use('/cache',express.static(path.join(process.env.TMPDIR!,'repurposer-source-cache')));
app.use(express.static(dir+'/assets'));
const server=app.listen(49873,'127.0.0.1');
try{
for(const mode of process.argv.slice(2)){
 process.env.CASE=mode; const out=dir+'/run/'+mode;fs.mkdirSync(out,{recursive:true}); const start=Date.now();
 const name=['edge','shape','silence','boundary'].includes(mode)?mode:'mix';
 const spec=videoSpecSchema.parse(JSON.parse(fs.readFileSync(dir+'/'+name+'.json','utf8')));
 try{const result=await renderVideo(spec,out,'video'); console.log(JSON.stringify({mode,result,ms:Date.now()-start,files:fs.readdirSync(out)}))}
 catch(error){console.error('FAILED',mode,error);process.exitCode=1;break}
}
}finally{server.closeAllConnections();server.close()}
