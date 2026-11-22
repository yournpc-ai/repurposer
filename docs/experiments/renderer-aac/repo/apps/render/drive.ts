import {renderVideo} from './src/video/index';
import {videoSpecSchema} from '@repurposer/video-spec';
import express from 'express';
import fs from 'node:fs';
const dir=process.env.LAB!, app=express();
app.use('/cache',express.static(process.env.TMPDIR+'/repurposer-source-cache'));app.use(express.static(dir+'/assets'));
const server=app.listen(49873,'127.0.0.1');
try{
for(const mode of process.argv.slice(2)){
 process.env.CASE=mode;fs.mkdirSync(dir+'/run/'+mode,{recursive:true});const start=Date.now();
 const spec=videoSpecSchema.parse(JSON.parse(fs.readFileSync(dir+'/'+(['noaudio','silence','shape'].includes(mode)?mode:'mix')+'.json','utf8')));
 const result=await renderVideo(spec,dir+'/run/'+mode,'video');
 console.log(JSON.stringify({mode,result,ms:Date.now()-start}));
}
}finally{server.closeAllConnections();server.close()}
