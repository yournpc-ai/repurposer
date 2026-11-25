"""Compile catalog previews through the same video-spec compiler as saved works."""

from uuid import NAMESPACE_URL, uuid5

from app.editing.schemas import (
    Clip,
    CompositionContent,
    MotionBlockObject,
    TextObject,
    Track,
    VersionSettings,
)
from app.editing.text_presets import TEXT_STYLE_PRESETS, text_style_from_token
from app.editing.video_spec import compile_video_spec
from app.models.schemas import canonical_json_hash
from app.tools.video.presets import _preview_font, build_motion_preview_spec


def preview_spec(kind, key, props, needs_media=False):
    settings = VersionSettings(width=1280, height=720, fps={"num": 30}, background="#202327")
    layout = {"x": 0, "y": 0, "width": 1280, "height": 720}
    snapshots = {}
    if kind == "block":
        resources = []
        if needs_media:
            demo = build_motion_preview_spec("device_mockup:split_focus")
            resource = demo["tracks"][0]["clips"][0]["object"]["resources"][0]
            sid = uuid5(NAMESPACE_URL, resource["digest"])
            snapshots[sid] = {"storage_key": resource["url"], "digest": resource["digest"]}
            resources = [
                {
                    "snapshot_id": sid,
                    "snapshot_digest": resource["digest"],
                    "path": "media/screen.png",
                    "content_type": "image/png",
                }
            ]
        objects = [
            MotionBlockObject(
                kind="motion_block",
                object_id="sample",
                layout=layout,
                block_id=key,
                props=props,
                resources=resources,
            )
        ]
    elif kind == "transition":
        objects = [
            MotionBlockObject(
                kind="motion_block",
                object_id=f"card{i}",
                block_id="statement_hook",
                fit="cover",
                layout=layout,
                props={"headline": title, "theme": theme, "show_backdrop": True},
            )
            for i, (title, theme) in enumerate((("First light", "dark"), ("Afterglow", "light")))
        ]
    else:
        token = TEXT_STYLE_PRESETS[key]
        texts = [key.replace("_", " ").title()]
        objects = [
            TextObject(
                kind="text",
                object_id=f"text{i}",
                text=t,
                layout={**layout, "y": 290, "height": 190},
                style=text_style_from_token(token, font_size=70),
            )
            for i, t in enumerate(texts)
        ]
    ticks = round(3 * settings.timebase / len(objects))
    clips = [
        Clip(clip_id=f"clip{i}", object=obj, range={"start": i * ticks, "end": (i + 1) * ticks})
        for i, obj in enumerate(objects)
    ]
    transitions = (
        [
            {
                "transition_id": "cut",
                "from_clip_id": "clip0",
                "to_clip_id": "clip1",
                "kind": key,
                "duration": settings.timebase // 2,
            }
        ]
        if kind == "transition"
        else []
    )
    content = CompositionContent(
        settings=settings,
        sources=[
            {"snapshot_id": sid, "snapshot_digest": facts["digest"]}
            for sid, facts in snapshots.items()
        ],
        timeline={
            "tracks": [Track(track_id="main", kind="visual", role="main", order=0, clips=clips)],
            "transitions": transitions,
        },
    )
    digest = canonical_json_hash(content.model_dump(mode="json"))
    spec = compile_video_spec(
        content,
        snapshots,
        composition_id=uuid5(NAMESPACE_URL, key),
        version_id=uuid5(NAMESPACE_URL, digest),
        content_digest=digest,
    )
    if kind == "block" and needs_media:
        # The renderer stages object.resources directly. Mirroring the same inline
        # capture onto clip.source would serialize its full PNG a second time.
        spec["tracks"][0]["clips"][0]["source"] = None
    font = dict(_preview_font())
    if kind == "text_preset":
        import base64

        from app.editing.fonts import DISPLAY_FONTS
        from app.skills.slot_preview import FONTS_DIR

        ref = objects[0].style.font
        font.update(font_id=ref.font_id, font_set_digest=ref.digest, weight=objects[0].style.weight)
        if face := DISPLAY_FONTS.get(ref.font_id):
            data = (FONTS_DIR / face["filename"]).read_bytes()
            font.update(
                family=face["family"],
                format=face["format"],
                digest=face["digest"],
                url="data:font/ttf;base64," + base64.b64encode(data).decode(),
            )
    spec["fonts"] = [font]
    return spec
