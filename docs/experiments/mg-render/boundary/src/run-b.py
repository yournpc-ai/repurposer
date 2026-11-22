import os,sys,subprocess
from pathlib import Path
from bench import measure,server
server()
for mode in ('adts','m4a'):
    subprocess.run([sys.executable,'src/setup-probe.py',mode],check=True)
    os.environ['PROBE_BIN']=str((Path('cache')/mode).resolve())
    if measure(['node','src/b.cjs','evidence/B-'+mode+'.mp4'],'B-'+mode):sys.exit(1)
