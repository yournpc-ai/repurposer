"""Decode the retained media and compare to the fixed MG source clocks (Python, PyAV, NumPy)."""
import hashlib
import json
import sys
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audio_reference(spec, assets):
    fps = Fraction(spec["fps"]["num"], spec["fps"]["den"])
    step = Fraction(48000, fps)
    result = np.zeros(round(spec["duration_frames"] * step))
    stems = {}
    for track in spec["tracks"]:
        if track["kind"] != "audio":
            continue
        for clip in track["clips"]:
            audio = assets / Path(clip["source"]["url"]).name
            assert digest(audio) == clip["source"]["digest"]
            start = round(clip["start_frame"] * step)
            length = round(clip["end_frame"] * step) - start
            stem = np.zeros_like(result)
            with wave.open(str(audio)) as source:
                assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (48000, 1, 2)
                source.setpos(round(clip["source"]["start_frame"] * step))
                samples = np.frombuffer(source.readframes(length), "<i2") / 32768
            gain = 10 ** (clip["object"]["gain_db"] / 20) / np.sqrt(2)
            stem[start:start + len(samples)] = samples * gain
            stems[clip["clip_id"]] = stem
            result += stem
    return result, stems


def lag(reference, timeline):
    size = 1 << (len(reference) + len(timeline) - 1).bit_length()
    scores = np.fft.irfft(np.fft.rfft(reference, size).conj() * np.fft.rfft(timeline, size), size)
    offsets = np.arange(-5000, 5001)
    return int(offsets[np.argmax(scores[offsets])])


def inspect(path, spec, assets):
    result = {"sha256": digest(path)}
    fps = Fraction(spec["fps"]["num"], spec["fps"]["den"])
    shape = spec["tracks"][0]["clips"][0]["object"]["kind"] == "shape"
    with av.open(str(path)) as movie:
        result["container"] = movie.format.name
        has_video, has_audio = bool(movie.streams.video), bool(movie.streams.audio)
    if has_video:
        with av.open(str(assets / "main.mp4")) as src:
            source_clock = [f.pts * f.time_base for f in src.decode(video=0)]
        with av.open(str(path)) as movie:
            video = movie.streams.video[0]
            packet_hash = hashlib.sha256()
            for packet in movie.demux(video):
                if packet.size:
                    packet_hash.update(packet.size.to_bytes(4, "big") + bytes(packet))
        frames = []
        with av.open(str(path)) as movie:
            video = movie.streams.video[0]
            for i, frame in enumerate(movie.decode(video=0)):
                pixels = frame.to_ndarray(format="gray")
                if shape:
                    actual, expected = int(pixels[100, 100] > 127), int(i >= 20)
                else:
                    actual = sum(int(pixels[32, 2 * (16 + j * 12)] > 127) << j for j in range(10))
                    target = (i + spec["tracks"][0]["clips"][0]["source"]["start_frame"]) / fps
                    expected = min(range(len(source_clock)), key=lambda j: (abs(source_clock[j] - target), -j))
                frames.append([i, frame.pts, actual, expected])
            tb = video.time_base
            errors = [abs(p * tb - i / fps) for i, p, _, _ in frames]
            result["video"] = dict(timebase=str(tb), packetSHA=packet_hash.hexdigest(),
                                   frames=frames, ptsErrors=sum(bool(e) for e in errors),
                                   maxError=str(max(errors)), idErrors=sum(a != b for _, _, a, b in frames))
    if has_audio:
        with av.open(str(path)) as movie:
            s = movie.streams.audio[0]
            packet = next(p for p in movie.demux(s) if p.size)
            meta = dict(pts=packet.pts, dts=packet.dts, timebase=str(s.time_base),
                        side=[(v.data_type, bytes(v).hex()) for v in packet.iter_sidedata()],
                        valid=round(s.duration * s.time_base * 48000))
        with av.open(str(path)) as movie:
            blocks = []
            for frame in movie.decode(audio=0):
                assert frame.sample_rate == 48000
                data = frame.to_ndarray()
                mono = data[0] if frame.format.is_planar else data.reshape(frame.samples, -1)[:, 0]
                if np.issubdtype(mono.dtype, np.integer):
                    mono = mono.astype(np.float64) / (np.iinfo(mono.dtype).max + 1)
                blocks.append((round(frame.pts * frame.time_base * 48000), mono))
        timeline = np.zeros(max(start + len(x) for start, x in blocks))
        for start, samples in blocks:
            timeline[start:start+len(samples)] = samples
        meta.update(decoded=sum(len(x) for _, x in blocks),
                    gaps=[(a+len(x), b) for (a,x),(b,_) in zip(blocks,blocks[1:]) if a+len(x)!=b])
        timeline = timeline[:meta["valid"]]
        meta["peak"] = float(np.max(np.abs(timeline)))
        ref, stems = audio_reference(spec, assets)
        if np.any(ref):
            tail = np.zeros_like(ref)
            end = np.flatnonzero(abs(stems["voice"]) > 1e-4)[-1]+1
            tail[end-4800:end] = ref[end-4800:end]
            meta.update(lag=lag(ref,timeline), stems={k:lag(x,timeline) for k,x in stems.items()},
                        tail=lag(tail,timeline))
        result["audio"] = meta
    return result


if __name__ == "__main__":
    spec_path, asset_dir, *media = map(Path, sys.argv[1:])
    spec = json.loads(spec_path.read_text())
    print(json.dumps({str(p):inspect(p,spec,asset_dir) for p in media}, indent=2))
