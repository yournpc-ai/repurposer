"""One paired warm-source benchmark using the same final encoder build."""
import json,os,sys
from pathlib import Path
import imageio_ffmpeg
from bench import server,measure

root=Path('cache/equal').resolve();root.mkdir(exist_ok=True)
for p in Path(os.environ['FFBIN']).iterdir():
    t=root/p.name
    if p.name!='ffmpeg' and not t.exists():t.symlink_to(p)
# Remotion clears subprocess env; put the absolute executable and log in this workdir's shim.
config={'binary':imageio_ffmpeg.get_ffmpeg_exe(),'log':str(Path('evidence/equal-args.jsonl').resolve())}
(root/'ffmpeg').write_text('#!'+sys.executable+'\n'+'''
import json,os,sys
from pathlib import Path
cfg=json.loads(Path(__file__).with_name('control.json').read_text())
mapping={'libfdk_aac':'aac','-filter_script:a':'-/filter:a','-filter_complex_script':'-/filter_complex','adts':'mp4'}
args=[mapping.get(arg,arg) for arg in sys.argv[1:]]
if 'libx264' in args:
    pos=args.index('libx264')+1
    args[pos:pos]=['-threads','2']
with open(cfg['log'],'a') as f:f.write(json.dumps(args)+'\\n')
os.execv(cfg['binary'],[cfg['binary'],*args])
''')
(root/'ffmpeg').chmod(0o755);(root/'control.json').write_text(json.dumps(config))
os.environ['PROBE_BIN']=str(root)
server()
if measure(['node','src/b.cjs','evidence/B-equal.mp4'],'equal-B'):sys.exit(1)
if measure([sys.executable,'src/c.py','evidence/C-equal.mp4'],'equal-C'):sys.exit(1)
