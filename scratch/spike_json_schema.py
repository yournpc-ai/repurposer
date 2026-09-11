"""Spike: MiniMax M3 hosted 是否支持 response_format: json_schema（ADR-071 ⑤
阶段2, T1 2026-09-12）。

既有事实（spike_native_toolcall 两轮 18 次）：tool_calls 通道可用、MiniMax
无 strict schema 强制。本探针补最后一个未知数——json_schema response
format（比 tool_calls 更小的迁移面：prose 通道不变、漏斗不变，只换
response_format）。

验证点：
1. 接受度：API 是否 4xx 拒绝 json_schema response_format；
2. 遵循度：prompt 故意【不写】形状规格（散文 spec 全删），模型的输出是否
   因 schema 到场而自动合法——特别盯 G-7 形状（constraints 对象数组 vs
   对象包数组）与 off-enum source；若 schema 不到场/不指导，此处必现
   形状错；
3. 流式：stream=True 下 json_schema 是否同样接受、内容是否正常分片。

只读探针，无 DB 无写盘。用法（apps/api/ 下）：
    uv run python ../../scratch/spike_json_schema.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.config import settings  # noqa: E402
from app.providers.llm.minimax import minimax_client  # noqa: E402


class SourcedConstraint(BaseModel):
    value: str
    source: str = "inferred"


class Verdict(BaseModel):
    action: str = Field(description="draft | ask | answer")
    answer: str | None = Field(default=None, description="user-facing reply; null for draft")
    tasks: list[dict] = Field(default_factory=list)
    constraints: list[SourcedConstraint] = Field(
        default_factory=list,
        description="hard requirements, ONE object per requirement",
    )


# 裸 prompt：只说任务，一个字的形状规格都不给。若 json_schema 真到场并指导
# 生成，输出应直接过 Pydantic；若它不到场/不指导，模型只能瞎猜形状。
MESSAGES = [
    {"role": "system", "content": "You are an intent parser for a content tool. Return JSON."},
    {
        "role": "user",
        "content": (
            "Turn my keynote into 3 vertical clips and a German post. "
            "Keep captions under 42 characters and never use stock music."
        ),
    },
]

PAYLOAD_BASE = {
    "model": settings.minimax_model,
    "messages": MESSAGES,
    "temperature": 0.2,
}
JSON_SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "verdict",
        "schema": Verdict.model_json_schema(),
    },
}


async def one_call(client: httpx.AsyncClient, *, stream: bool, tag: str) -> dict:
    payload = {**PAYLOAD_BASE, "response_format": JSON_SCHEMA_FORMAT, "stream": stream}
    if stream:
        payload["stream_options"] = {"include_usage": True}
    try:
        if not stream:
            r = await client.post(
                f"{settings.minimax_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.minimax_api_key}"},
                json=payload,
            )
            if r.status_code != 200:
                return {"tag": tag, "http": r.status_code, "body": r.text[:300]}
            content = r.json()["choices"][0]["message"]["content"]
        else:
            chunks: list[str] = []
            async with client.stream(
                "POST",
                f"{settings.minimax_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.minimax_api_key}"},
                json=payload,
            ) as r:
                if r.status_code != 200:
                    return {"tag": tag, "http": r.status_code, "body": (await r.aread())[:300]}
                async for line in r.aiter_lines():
                    if not line.startswith("data:") or line == "data: [DONE]":
                        continue
                    payload_chunk = json.loads(line[5:])
                    choices = payload_chunk.get("choices") or []
                    if not choices:
                        continue  # usage-only tail chunk (choice-less by design)
                    delta = choices[0].get("delta") or {}
                    if delta.get("content"):
                        chunks.append(delta["content"])
            content = "".join(chunks)
    except httpx.HTTPError as e:
        return {"tag": tag, "error": str(e)[:200]}

    cleaned = minimax_client._clean_json(content)  # 生产同款清洗（think/围栏）
    try:
        parsed = Verdict.model_validate_json(cleaned)
        verdict = "VALID"
        detail = f"action={parsed.action} constraints={len(parsed.constraints)}"
    except (ValidationError, ValueError) as e:
        verdict = f"INVALID: {str(e)[:200]}"
        detail = ""
    # G-7 形状盯梢：constraints 是否模型的自然写法（对象数组）
    natural = bool(re.search(r'"constraints"\s*:\s*\[\s*\{', cleaned))
    return {
        "tag": tag,
        "verdict": verdict,
        "detail": detail,
        "natural_constraint_shape": natural,
        "cleaned_head": cleaned[:200],
    }


async def main() -> None:
    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not configured")
        return
    async with httpx.AsyncClient(timeout=120) as client:
        results = [
            await one_call(client, stream=False, tag=f"nonstream-{i}")
            for i in range(3)
        ]
        results.append(await one_call(client, stream=True, tag="stream-0"))
    for r in results:
        print(json.dumps(r, ensure_ascii=False))


asyncio.run(main())
