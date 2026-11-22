import sys,os,subprocess,json
from pathlib import Path
from bench import measure,server
import imageio_ffmpeg
def prepare():
    root=Path('cache/equal-encoder').resolve();root.mkdir(exist_ok=True)
    for p in Path(os.environ['FFBIN']).iterdir():
        t=root/p.name
        if p.name!='ffmpeg' and not t.exists():t.symlink_to(p)
    ff=imageio_ffmpeg.get_ffmpeg_exe()
    (root/'ffmpeg').write_text('''#!/bin/bash
args=()
for arg in "$@"; do
    if [[ "$arg" == "libfdk_aac" ]]; then arg=aac; fi
    if [[ "$arg" == "-filter_script:a" ]]; then arg="-/filter:a"; fi
    if [[ "$arg" == "-filter_complex_script" ]]; then arg="-/filter_complex"; fi
    args+=("$arg")
done
printf '%q ' "${args[@]}" >> "$CONTROL_ARG_LOG"
printf '\\n' >> "$CONTROL_ARG_LOG"
exec "'''+ff+'''" "${args[@]}"
''')
    (root/'ffmpeg').chmod(0o755)
    base=Path('src/remotion.cjs').read_text().replace('const args={serveUrl,','const args={binariesDirectory:process.env.CONTROL_BIN,serveUrl,').replace("audioBitrate:'192k',","audioBitrate:'192k',ffmpegOverride:({args})=>{const i=args.findIndex(a=>a==='libx264');if(i<0)return args;const out=[...args];out.splice(i+1,0,'-threads','2');return out;},")
    Path('cache/same-encoder.cjs').write_text(base)
    os.environ['CONTROL_BIN']=str(root);os.environ['CONTROL_ARG_LOG']=str(Path('logs/encoder-args.log').resolve())
if __name__=='__main__':
    prepare();server()
    for i,order in enumerate(('BC','CB','BC'),1):
        for r in order:
            out=f'results/control-{r}-{i}.mp4'
            cmd=(['node','cache/same-encoder.cjs','B','3',out] if r=='B' else [sys.executable,'src/chromium.py','3',out])
            if measure(cmd,f'control-{r}-{i}'):sys.exit(1)
