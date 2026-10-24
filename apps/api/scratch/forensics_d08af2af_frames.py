"""Download final incident output mp4 from TOS and dump mid-scene frames
(PyAV, pts-named, one dump, read-only forensics). No re-render, no paid calls.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import av  # PyAV
import boto3

KEY = "52037604-9321-4b70-9212-445ccf5ade60/outputs/projects/d08af2af-02d4-4a04-9483-4db03ff6ef0d/87c1aa61-56e3-470b-bb73-d2b993f5a717-1792606522.mp4"
OUT_DIR = "/tmp/d08af2af_frames_take1"
MP4 = "/tmp/d08af2af_final.mp4"

# scene windows (frames @30fps): s1 0-119, s2 120-269, s3 270-449, s4 450-599
MID_FRAMES = {"s1": 60, "s2": 195, "s3": 360, "s4": 525}


def download():
    from app.config import settings
    from app.providers.storage import _get_s3_download_client
    _get_s3_download_client().download_file(settings.s3_bucket_name, KEY, MP4)
    print("downloaded", os.path.getsize(MP4), "bytes")


def dump_frames():
    os.makedirs(OUT_DIR, exist_ok=True)
    container = av.open(MP4)
    stream = container.streams.video[0]
    fps = float(stream.average_rate)
    print("fps:", fps, "frames:", stream.frames, "duration:", float(stream.duration * stream.time_base))
    wanted = dict(MID_FRAMES)
    idx = -1
    for frame in container.decode(stream):
        idx += 1
        for tag, target in list(wanted.items()):
            if idx == target:
                pts_name = f"{tag}_f{idx:05d}_pts{frame.pts}.png"
                frame.to_image().save(os.path.join(OUT_DIR, pts_name))
                # brightness sample: mean luminance of the frame
                import numpy as np
                arr = frame.to_ndarray(format="gray")
                print(f"{tag} frame {idx}: mean_luma={arr.mean():.1f}")
                del wanted[tag]
        if not wanted:
            break
    container.close()
    print("missing:", wanted)


if not os.path.exists(MP4):
    download()
dump_frames()
