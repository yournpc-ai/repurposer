const esbuild=require('esbuild'),fs=require('fs'),path=require('path');
const base=process.argv[2], v=process.argv[3];
const req=JSON.parse(fs.readFileSync('fixture/request'+v+'.json'));
fs.mkdirSync(base,{recursive:true});
fs.copyFileSync('src/Direct.tsx',base+'/entry.tsx');
fs.writeFileSync(base+'/active-title.tsx',req.project.files.find(f=>f.path==='Title.tsx').content);
esbuild.buildSync({entryPoints:[base+'/entry.tsx'],bundle:true,outfile:base+'/app.js',define:{'process.env.NODE_ENV':'"production"'}});
