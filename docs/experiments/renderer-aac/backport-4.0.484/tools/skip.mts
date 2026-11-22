import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
const {normalizeLoudness} = await import(path.join(process.cwd(),'src/audio.ts'));
const root = process.env.LAB!;
const sha = async(p:string)=>createHash('sha256').update(await fs.readFile(p)).digest('hex');
for (const mode of ['absent','silent']) {
 process.env.CASE=mode;
 const file=path.join(root,'run',mode,'probe.mp4');
 const before=await sha(file);
 await normalizeLoudness(file,384000);
 const after=await sha(file);
 if(before!==after)throw Error(mode+' changed');
 console.log(JSON.stringify({mode,before,after,files:await fs.readdir(path.dirname(file))}));
}
