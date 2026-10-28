"""B-V generated-image journey guards: no DB, no network, no paid provider.

The first journey submits once, loses the response, and proves recovery cannot
replay the unconfirmed request. The second covers fixed media, actual usage,
ordinary reuse, explicit regeneration, and same-Run recovery.
"""
from __future__ import annotations

import base64
import hashlib
import io
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from PIL import Image

from app.editing.schemas import (
    Clip,
    GeneratedImageOutput,
    GeneratorObject,
    LayoutBox,
    TimeRange,
)
from app.pipeline.errors import USER_ERROR_LINES, user_error_line
from app.providers.llm import minimax as provider
from app.providers.llm.base import LLMError
from app.tools.video import generated_images as generated
from app.tools.video import preparation
from app.tools.video.generated_images import GeneratedImageOutcomeUnknown
from app.tools.video.production.node import ProduceVideo


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def exists(self, key: str | None) -> bool:
        return key in self.objects

    async def read(self, key: str) -> bytes:
        return self.objects[key]

    async def save(self, key: str, data: bytes, content_type: str | None = None) -> str:
        self.objects[key] = data
        return key


class FakeHttp:
    def __init__(self, *results: object) -> None:
        self.results = list(results)
        self.posts: list[dict] = []

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.posts.append(kwargs["json"])
        if not self.results:
            raise AssertionError("unexpected additional image-generation POST")
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        assert isinstance(result, httpx.Response)
        return result


def _clip() -> Clip:
    return Clip(
        clip_id="clp_generated_image",
        scene_id="scn_generated_image",
        range=TimeRange(start=0, end=360000),
        object=GeneratorObject(
            kind="generator",
            object_id="obj_generated_image",
            runtime="image-v1",
            prompt="A text-free sunrise over layered mountains",
            provider="minimax",
            model="image-01",
            output=GeneratedImageOutput(),
            layout=LayoutBox(x=0, y=0, width=1920, height=1080),
        ),
    )


def _encoded_image(color: str) -> str:
    output = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(output, format="JPEG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _success(encoded: str) -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://minimax.test/v1/image_generation"),
        json={
            "data": {"image_base64": [encoded]},
            "base_resp": {"status_code": 0},
        },
    )


def _install(monkeypatch: pytest.MonkeyPatch, *results: object):
    http = FakeHttp(*results)

    @asynccontextmanager
    async def pooled_client():
        yield http

    storage = MemoryStorage()
    usage: list[dict[str, float]] = []

    async def record_usage(units: dict[str, float]) -> None:
        usage.append(units)

    monkeypatch.setattr(provider, "_pooled_client", pooled_client)
    monkeypatch.setattr(generated.minimax_client, "api_key", "test-key")
    monkeypatch.setattr(generated.minimax_client, "base_url", "https://minimax.test/v1")
    monkeypatch.setattr(generated, "storage", storage)
    monkeypatch.setattr(preparation, "storage", storage)
    monkeypatch.setattr(generated, "record_media_usage", record_usage)
    return http, storage, usage


@pytest.mark.asyncio
async def test_response_timeout_never_auto_reposts_and_recovery_fails_closed(monkeypatch):
    http, storage, usage = _install(monkeypatch, httpx.ReadTimeout("response lost"))
    clip = _clip()
    execution_id = str(uuid4())
    composition_id = str(uuid4())

    with pytest.raises(LLMError) as caught:
        await generated.ensure_generated_image_clip(
            clip, execution_id=execution_id, composition_id=composition_id
        )

    assert len(http.posts) == 1
    assert caught.value.user_key == "provider_image_outcome_unknown"
    assert user_error_line(caught.value) == USER_ERROR_LINES[
        "provider_image_outcome_unknown"
    ]["en"]
    assert usage == []
    assert not any(key.startswith("source-snapshots/") for key in storage.objects)

    # This second call models worker/manual recovery of the same execution. The
    # durable submitted marker fails closed before another provider POST.
    with pytest.raises(GeneratedImageOutcomeUnknown) as recovered:
        await generated.ensure_generated_image_clip(
            clip, execution_id=execution_id, composition_id=composition_id
        )
    assert len(http.posts) == 1
    assert usage == []
    assert user_error_line(recovered.value) == USER_ERROR_LINES[
        "provider_image_outcome_unknown"
    ]["en"]
    assert ProduceVideo.retries == 0


@pytest.mark.asyncio
async def test_fixed_media_usage_regeneration_and_latest_reuse(monkeypatch):
    http, storage, usage = _install(
        monkeypatch,
        _success(_encoded_image("red")),
        _success(_encoded_image("blue")),
    )
    clip = _clip()
    composition_id = str(uuid4())
    first_run = str(uuid4())

    first = await generated.ensure_generated_image_clip(
        clip, execution_id=first_run, composition_id=composition_id
    )
    assert len(http.posts) == 1
    assert usage == [{"images": 1.0}]
    media = first["media"]
    assert hashlib.sha256(storage.objects[media["storage_key"]]).hexdigest() == media["digest"]
    assert first["execution_id"] == first_run
    assert first["usage"] == {"images": 1}

    # Same-Run recovery and ordinary production both reuse the fixed bytes.
    for run_id in (first_run, str(uuid4())):
        resumed = await generated.ensure_generated_image_clip(
            clip, execution_id=run_id, composition_id=composition_id
        )
        assert resumed["media"] == first["media"]
    assert len(http.posts) == 1
    assert usage == [{"images": 1.0}]

    regeneration_run = str(uuid4())
    regenerated = await generated.ensure_generated_image_clip(
        clip,
        execution_id=regeneration_run,
        composition_id=composition_id,
        regenerate=True,
    )
    assert len(http.posts) == 2
    assert usage == [{"images": 1.0}, {"images": 1.0}]
    assert regenerated["execution_id"] == regeneration_run
    assert regenerated["media"]["digest"] != first["media"]["digest"]

    # Retrying that explicit-regeneration Run cannot create a third request.
    regenerated_retry = await generated.ensure_generated_image_clip(
        clip,
        execution_id=regeneration_run,
        composition_id=composition_id,
        regenerate=True,
    )
    assert regenerated_retry["media"] == regenerated["media"]
    latest = await generated.ensure_generated_image_clip(
        clip, execution_id=str(uuid4()), composition_id=composition_id
    )
    assert latest["media"] == regenerated["media"]
    assert len(http.posts) == 2
    assert usage == [{"images": 1.0}, {"images": 1.0}]
