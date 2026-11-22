"""Replay the archived study in scratch space. Print a machine-readable receipt."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import av
import numpy as np
import PIL

from inspect_audio import decode, wav
from render import RATE, pcm_wave

ARCHIVE = Path(__file__).resolve().parent
REPO = Path(os.environ.get("REP_REPO", ARCHIVE.parents[3])).resolve()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replay(work):
    for name in ("catalog.py", "render.py", "sync.py", "inspect_audio.py"):
        shutil.copyfile(ARCHIVE / name, work / name)

    def run(script):
        subprocess.run([sys.executable, "-B", script], cwd=work, check=True,
                       env={**os.environ, "REP_REPO": str(REPO)}, stdout=sys.stderr)

    sources = json.loads((ARCHIVE / "sources.json").read_text())
    results = {}
    for _ in range(2):
        run("render.py")
        for name in sources:
            path = work / (name + ".wav")
            assert sha(path.read_bytes()) == sources[name]["wav_sha256"]
            _, decoded = decode(path)
            original = wav(ARCHIVE / path.name)
            np.testing.assert_array_equal(decoded, original)
            samples = np.rint(original * 32768).astype("<i2")
            results[name] = dict(pcm_sha256=sha(samples.tobytes()),
                                 dc_fs=original.mean(axis=0).tolist(),
                                 max_step_fs=float(np.abs(np.diff(original, axis=0)).max()))
    run("inspect_audio.py")
    run("sync.py")
    for name in ("sources.json", "catalog.json", "measurements.json", "sync.json", "sync.mp4"):
        assert (work / name).read_bytes() == (ARCHIVE / name).read_bytes(), name

    # Independent cue sheet, in 48 kHz samples. Compare actual decoded mix with
    # the known stems, including their contribution inside the overlap window.
    fixture = REPO / "docs/tasks/agent-editor-evidence/iteration-6"
    schedule = [
        (fixture / "sample-generate_music.wav", 0, 0.20),
        (fixture / "sample-generate_voice.mp3", 36480, 0.72),
        (work / "whoosh-default.wav", 43200, 0.58),
        (work / "impact-default.wav", 67200, 0.55),
        (work / "click-default.wav", 104000, 0.68),
    ]
    frames = 144000
    mix = np.zeros((frames, 2))
    stems = {}
    for path, start, gain in schedule:
        _, signal = decode(path)
        signal = signal[:frames-start].astype(float) * gain
        stems[path.stem] = np.zeros_like(mix)
        stems[path.stem][start:start+len(signal)] = signal
        mix += stems[path.stem]
    pcm = pcm_wave(mix)
    (work / "reference.wav").write_bytes(pcm)
    start, actual = decode(work / "sync.mp4")
    assert start == 0 and len(actual) >= frames
    with av.open(str(work / "sync.mp4")) as container:
        sample = 0
        for frame in container.decode(audio=0):
            assert frame.pts * frame.time_base * RATE == sample
            sample += frame.samples
    overlap = slice(67200, 70080)
    reference = wav(work / "reference.wav")[overlap]
    residual = actual[overlap] - reference
    error = np.mean(residual**2)
    improvements = {}
    for name in ("whoosh-default", "impact-default", "sample-generate_voice", "sample-generate_music"):
        omitted = residual + stems[name][overlap]
        improvements[name] = float(10 * np.log10(np.mean(omitted**2) / error))
        assert improvements[name] > 0, name
    return dict(wavs=results, overlap_samples=[overlap.start, overlap.stop],
                overlap_error_increase_db_if_omitted=improvements,
                reference_wav_sha256=sha(pcm), sync_sha256=sha((work / "sync.mp4").read_bytes()),
                ffmpeg_libraries=av.library_versions, pillow=PIL.__version__, pyav=av.__version__)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as scratch:
        print(json.dumps(replay(Path(scratch)), indent=2, sort_keys=True))
