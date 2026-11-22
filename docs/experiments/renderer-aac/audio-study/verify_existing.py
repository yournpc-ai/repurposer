"""Invoke only the repository's pure bytes analyzer; no DB, storage, or provider."""
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from render import dump,digest
from app.tools.video.media_analysis import analyze_audio_bytes

reports={}
for p in sorted(Path('.').glob('*.wav')):
    data=p.read_bytes()
    sha=digest(data)
    report=analyze_audio_bytes(data,snapshot_id=str(uuid5(NAMESPACE_URL,'isolated-research:'+sha)),source_digest=sha)
    reports[p.name]=report.model_dump(mode="json")
dump("existing-analysis.json",reports)
