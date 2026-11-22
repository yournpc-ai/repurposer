import {pathToFileURL} from 'node:url';
import fs from 'node:fs';
async function run(){
  const {bakeComponent}=await import(pathToFileURL(process.env.REP + '/apps/render/src/component-runtime/bake.ts').href);
  const req=JSON.parse(fs.readFileSync('fixture/request'+process.argv[2]+'.json','utf8'));
  const r:any=await bakeComponent(req);
  const stem='assets/'+r.program_digest;
  fs.writeFileSync(stem+'.tmp',Buffer.from(r.video_base64,'base64'));fs.renameSync(stem+'.tmp',stem+'.mp4');
  fs.writeFileSync('analysis/bake-'+r.program_digest+'.png',Buffer.from(r.preview_base64,'base64'));
  delete r.video_base64;delete r.preview_base64;
  fs.writeFileSync('logs/bake-'+r.program_digest+'.json',JSON.stringify(r,null,2));
}
run().catch(e=>{console.error(e);process.exitCode=1});
