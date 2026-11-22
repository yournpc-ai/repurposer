"""Pixel oracle for the archived V7 scene. Run through run.sh."""

import base64
import csv
import hashlib
import io
import json
import os
import sys
import time
import uuid
from copy import deepcopy
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

from audio_oracle import pcm
from c import CHECK, frame_url, source_index
from verify import code

ARCHIVE = Path(os.environ["CLOCK"]).parent / "evidence"
OUT = Path("evidence")
TARGET = "signal-title"
META = {"id", "version", "base_version_id", "composition_id", "content_digest"}


def read(path):
    return json.loads(Path(path).read_text())


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def target(content):
    return next(
        c["object"]
        for t in content["timeline"]["tracks"]
        for c in t["clips"]
        if c["object"]["object_id"] == TARGET
    )


def prepare():
    from app.editing.schemas import CompositionContent
    from app.editing.store import content_digest_of
    from app.editing.validators import validate_content

    sources = {
        uuid.UUID(k): v for k, v in read(Path(os.environ["MG"]) / "baseline/fixture/sources3.json").items()
    }
    parent = read(ARCHIVE / "v7.json")
    body = {k: v for k, v in parent.items() if k not in META}
    project = target(body)["project"]
    src = Path("src/Readout.tsx").read_text()
    project["entry"] = "Readout.tsx"
    project["files"][0] = dict(path="Readout.tsx", content=src, digest=digest(src.encode()))
    for number in (8, 9):
        if number == 9:
            project["props"]["ink"] = "#8acdf5"
        content = CompositionContent.model_validate(body)
        validate_content(content, sources)
        key = content_digest_of(content)
        version = dict(
            **body,
            version=number,
            composition_id=parent["composition_id"],
            base_version_id=parent["id"],
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
            content_digest=key,
        )
        write(f"v{number}.json", version)
        parent = version

    spec = read("cache/data7.json")
    frames = source_index([c for t in spec["tracks"] for c in t["clips"] if c["object"]["kind"] == "video"])
    write(
        "inputs.json",
        dict(
            source_frames={k: len(v) for k, v in frames.items()},
            source_cache_bytes=sum(
                p.stat().st_size for p in Path("cache/frames").rglob("*") if p.is_file()
            ),
            bundle_bytes=Path("cache/clock.js").stat().st_size,
            chromium_sha256=digest(Path(os.environ["CHROME"]).read_bytes()),
        ),
    )


def projection(number):
    # Original prepare.py compiled V7. Verify the exact allowed delta before reusing its tracks.
    spec = read("cache/data7.json")
    version = read(OUT / f"v{number}.json")
    if number == 9:
        prior = read(OUT / "v8.json")
        reverted = deepcopy(version)
        target(reverted)["project"]["props"]["ink"] = target(prior)["project"]["props"]["ink"]
        assert version["base_version_id"] == prior["id"]
        assert {k: v for k, v in reverted.items() if k not in META} == {
            k: v for k, v in prior.items() if k not in META
        }
    restored = deepcopy(version)
    old = read(ARCHIVE / "v7.json")
    target(restored)["project"] = target(old)["project"]
    assert {k: v for k, v in restored.items() if k not in META} == {
        k: v for k, v in old.items() if k not in META
    }
    obj = next(
        c["object"] for t in spec["tracks"] for c in t["clips"] if c["object"]["object_id"] == TARGET
    )
    obj["props"] = target(version)["project"]["props"]
    spec["provenance"].update(
        content_digest=version["content_digest"], composition_version_id=version["id"]
    )
    return spec


def capture(session):
    png = session.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(png["data"]))).convert("RGB"))


def run(phase):
    data, edited = projection(8), projection(9)
    fps = Fraction(data["fps"]["num"], data["fps"]["den"])
    clips = [c for t in data["tracks"] for c in t["clips"] if c["object"]["kind"] == "video"]
    index = source_index(clips)
    source_ids = {
        int(row["frame"]): row
        for row in csv.DictReader((ARCHIVE / "source-ids.csv").open())
        if row["version"] == "7"
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ["CHROME"], chromium_sandbox=True)

        def open_page(name):
            p = browser.new_page(
                viewport=dict(width=data["width"], height=data["height"]), device_scale_factor=1
            )
            p.goto(Path(f"cache/{name}.html").resolve().as_uri())
            return p, p.context.new_cdp_session(p)

        page, session = open_page("clock")

        def paint(frame, spec=data, p=page, s=session):
            urls = {
                c["object"]["object_id"]: frame_url(c, frame, fps, index)
                for c in clips
                if c["start_frame"] <= frame < c["end_frame"]
            }
            p.evaluate("v => window.paint(v)", dict(data=spec, k=frame, urls=urls))
            return capture(s)

        if phase == "sequence":
            v7 = read("cache/data7.json")
            original, original_session = open_page("original")
            edit_page, edit_session = open_page("clock")
            rows = []
            for k in range(data["duration_frames"]):
                pixels = paint(k)
                reference = paint(k, v7, original, original_session)
                change = paint(k, edited, edit_page, edit_session)
                main = code(pixels, 0, 32, 2)
                pip = code(pixels, 1330, 104, 1) if 15 <= k < 210 else None
                assert main == int(source_ids[k]["main_expected"])
                assert pip == (
                    int(source_ids[k]["pip_expected"]) if source_ids[k]["pip_expected"] else None
                )
                y, x = np.where(np.any(change != pixels, axis=2))
                bounds = [int(x.min()), int(y.min()), int(x.max()), int(y.max())] if x.size else None
                assert bool(x.size) == (30 <= k < 180), (k, bounds)
                if bounds:
                    rect = edit_page.locator('[data-object="signal-title"] > div').bounding_box()
                    assert np.floor(rect["x"]) <= x.min() <= x.max() < np.ceil(rect["x"] + rect["width"])
                    assert np.floor(rect["y"]) <= y.min() <= y.max() < np.ceil(rect["y"] + rect["height"])
                rows.append(
                    dict(
                        frame=k,
                        rgb=digest(pixels.data),
                        reference=digest(reference.data),
                        reference_changed_pixels=int(np.any(pixels != reference, axis=2).sum()),
                        edit=digest(change.data),
                        edit_bounds=bounds,
                        main=main,
                        pip=pip,
                    )
                )
            write("sequence.json", rows)
            assert all(row["rgb"] == row["reference"] for row in rows), "V7 visual parity"
            audio = [
                np.round(pcm(spec) * 32767).astype("<i2")
                for spec in (read("cache/data7.json"), data, edited)
            ]
            assert all(np.array_equal(audio[0], a) for a in audio[1:])
            write(
                "audio.json",
                dict(
                    samples_per_channel=len(audio[0]),
                    channels=audio[0].shape[1],
                    pcm_s16le=[digest(a.data) for a in audio],
                ),
            )
        else:
            expected = read(OUT / "sequence.json")
            rows = []
            order = CHECK + [72, 72, 30, 72] if phase == "seek" else reversed(range(len(expected)))
            for k in order:
                h = digest(paint(k).data)
                assert h == expected[k]["rgb"], (phase, k, h, expected[k])
                rows.append([k, h])
            write(phase + ".json", rows)
            if phase == "seek":
                waits = []
                for delay in (0, 0.12, 0.53):
                    # Perturb capture AFTER paint without re-seeking.
                    start = time.monotonic()
                    time.sleep(delay)
                    h = digest(capture(session).data)
                    state = page.evaluate(
                        "() => document.getAnimations().map(a => [a.playState,a.currentTime])"
                    )
                    assert h == expected[72]["rgb"] and state == [["paused", 1400]]
                    waits.append(dict(elapsed_s=time.monotonic() - start, rgb=h, state=state))
                write("hold.json", waits)
                # Replay the archived uncontrolled image fade; wait for its semantic end.
                before = digest(capture(session).data)
                # Same Readout handle, same Composition frame, but let the document clock drive it.
                page.evaluate("""async () => {
                    const a = document.getAnimations()[0];
                    a.play();
                    await a.finished;
                }""")
                running_title = digest(capture(session).data)
                assert running_title != before
                page.evaluate(
                    "async () => {const a = document.getAnimations()[0]; a.pause(); await a.ready;}"
                )
                assert digest(paint(72).data) == before
                page.evaluate("""async () => {
                    const a = document.querySelector('img').animate([{opacity:1},{opacity:0}],
                        {duration:5000, fill:'forwards'});
                    await a.finished;
                }""")
                after = digest(capture(session).data)
                page.evaluate("() => document.querySelector('img').getAnimations()[0].cancel()")
                repaired = digest(paint(72).data)
                assert repaired == before
                assert before != after
                write(
                    "uncontrolled.json",
                    dict(
                        frame=72,
                        paused=before,
                        autoplay_title_end=running_title,
                        autoplay_image_end=after,
                        controlled=repaired,
                    ),
                )
        browser.close()


if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    else:
        run(sys.argv[1])
