const cp=require('node:child_process'),fs=require('node:fs'),path=require('node:path');
const orig=cp.ChildProcess.prototype.spawn,base=process.env.LAB;
const log=o=>fs.appendFileSync(base+'/commands.jsonl',JSON.stringify(o)+'\n');
cp.ChildProcess.prototype.spawn=function(o){
 const mode=process.env.CASE||'boot', dir=base+'/run/'+mode, args=o.args.slice(), last=args.at(-1);
 const media=/ffmpeg|ffprobe/.test(path.basename(o.file));const target=args.at(-1);
 if(media){
 for(let i=0;i<args.length;i++){
  const arg=args[i];
  if(typeof arg!=='string'||!path.isAbsolute(arg)||!fs.existsSync(arg))continue;
  if(/remotion-complex-filter.*\.txt$/.test(arg))fs.copyFileSync(arg,dir+'/'+path.basename(args.at(-1))+'-filter.txt');
  if(args[i-1]==='-i' && /\/(audio|merged|[012])\.wav$/.test(arg))fs.copyFileSync(arg,dir+'/'+path.basename(arg));
 }

 if(args.includes('-i'))for(const name of ['pre-encode.mkv','mix.mov']){
 const src=args.find(a=>typeof a==='string'&&a.endsWith('/'+name)&&fs.existsSync(a));if(src)fs.copyFileSync(src,dir+'/'+name);
 }
 if(args.includes('stream=sample_rate,time_base,start_pts,duration_ts')&&fs.existsSync(target))fs.copyFileSync(target,dir+'/raw.mp4');
 for(const f of args)if(typeof f==='string'&&path.isAbsolute(f)&&/\/(merged\.wav|audio\.aac)$/.test(f)&&fs.existsSync(f))fs.copyFileSync(f,dir+'/'+path.basename(f));
 if(mode==='muxFail'&&args.includes('libfdk_aac')||mode==='measureFail'&&args.some(x=>typeof x==='string'&&x.includes('print_format=json'))||mode==='encodeFail'&&last.endsWith('.loudnorm.mp4'))o.args=[args[0],'-i8-injected-invalid-option',...args.slice(1)];
 log({mode,file:o.file,args:o.args,cwd:o.cwd,at:Date.now()});
 this.on('close',(code,signal)=>log({mode,file:o.file,code,signal,last,at:Date.now()}));
 }
 const ret=orig.call(this,o);
 if(media&&this.stderr && args.some(x=>typeof x==='string'&&x.includes('loudnorm=')))this.stderr.on('data',x=>fs.appendFileSync(dir+'/loudnorm.log',x));
 return ret
}
const rename=fs.promises.rename;fs.promises.rename=async function(a,b){if(process.env.CASE==='renameFail'&&a.endsWith('.loudnorm.mp4')){fs.accessSync(a);throw new Error('injected pre-rename failure')}return rename.call(this,a,b)}
