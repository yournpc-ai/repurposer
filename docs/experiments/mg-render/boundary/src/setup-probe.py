import json,sys,os
from pathlib import Path
mode=sys.argv[1];root=Path('cache')/mode;root.mkdir(exist_ok=True);cap=Path('evidence')/mode;cap.mkdir(exist_ok=True)
bins=Path(os.environ['FFBIN']).resolve()
for p in bins.iterdir():
    dst=root/p.name
    if p.name!='ffmpeg' and not dst.exists():dst.symlink_to(p)
(root/'ffmpeg').write_text('#!'+sys.executable+'\n'+Path('src/audio_wrapper.py').read_text());(root/'ffmpeg').chmod(0o755)
(root/'probe.json').write_text(json.dumps(dict(ffmpeg=str(bins/'ffmpeg'),capture=str(cap.resolve()),m4a=mode=='m4a')))
