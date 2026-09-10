"""Spike: MiniMax M3 原生工具调用（OpenAI 兼容 tools + stream）可行性验证。

背景：用户判词「JSON-in-prompt 是在裸 JSON 流上徒手重建原生 text/tool_use
交错通道」。若 M3 hosted API 支持流式 tool_calls——散文走 delta.content
原生通道、判决走 tool_call.arguments 累积——则 ProseDeltaExtractor /
AskObjectWatcher / 计划数组流拍一整套徒手装置可退役，打字机免费，
schema 校验面收窄到 tool arguments（簿记错不再炸掉已送达散文）。

验证点：
1. delta.content 散文是否先于/独立于 tool_calls 流式到达（原生交错）
2. tool_calls[].function.arguments 分片累积后是否合法 JSON
3. arguments 是否过 Pydantic 校验（含「对象数组」形状的 constraints——
   顺手验证顺形 schema：模型自然写法直接合法）
4. 第二次调用：模型自由决定是否说话（无强制先散文）

只读探针，无 DB 无写盘。用法（apps/api/ 下）：
    uv run python ../../scratch/spike_native_toolcall.py
"""

import asyncio
import json

import httpx
from pydantic import BaseModel, Field

from app.config import settings

# 顺形 schema 试验田：constraints = 来源化条目的数组（模型在真实故障中的
# 第一直觉写法），不再是「对象包数组」。
class SourcedConstraint(BaseModel):
    value: str
    source: str = "inferred"


class Verdict(BaseModel):
    action: str
    tasks: list[dict] = Field(default_factory=list)
    constraints: list[SourcedConstraint] = Field(default_factory=list)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Submit the intent verdict for the user's request.",
            "parameters": Verdict.model_json_schema(),
        },
    }
]

MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are an intent parser. First speak to the user in one short "
            "sentence (what you understood and will do), THEN call "
            "submit_verdict with the structured verdict."
        ),
    },
    {
        "role": "user",
        "content": (
            "Caption my video in Chinese and French — Chinese bilingual — "
            "and dub a Spanish version in my own voice. Keep the 1:1 frame."
        ),
    },
]


async def one_round(tag: str, max_tokens: int | None = None) -> dict:
    payload = {
        "model": settings.minimax_model,
        "messages": MESSAGES,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.2,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    text_parts: list[str] = []
    arg_parts: dict[int, list[str]] = {}
    tool_name: str | None = None
    finish_reason: str | None = None
    usage: dict | None = None
    first_text_at: float | None = None
    first_tool_at: float | None = None
    t0 = asyncio.get_event_loop().time()

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{settings.minimax_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.minimax_api_key}"},
            json=payload,
        ) as resp:
            if resp.status_code != 200:
                print(f"[{tag}] HTTP {resp.status_code}: {(await resp.aread()).decode()[:300]}")
                return {"tag": tag, "error": resp.status_code}
            async for line in resp.aiter_lines():
                if not line.startswith("data:") or line == "data: [DONE]":
                    continue
                chunk = json.loads(line[5:].strip())
                if chunk.get("usage"):
                    usage = chunk["usage"]
                for choice in chunk.get("choices", []):
                    if choice.get("finish_reason"):
                        finish_reason = choice["finish_reason"]
                    delta = choice.get("delta", {})
                    if delta.get("content"):
                        if first_text_at is None:
                            first_text_at = asyncio.get_event_loop().time() - t0
                        text_parts.append(delta["content"])
                    for tc in delta.get("tool_calls") or []:
                        if first_tool_at is None:
                            first_tool_at = asyncio.get_event_loop().time() - t0
                        idx = tc.get("index", 0)
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_name = fn["name"]
                        if fn.get("arguments"):
                            arg_parts.setdefault(idx, []).append(fn["arguments"])

    prose = "".join(text_parts)
    raw_args = "".join(arg_parts.get(0, []))
    # 思考块占用：think 内字符数（截断案的嫌疑犯——巨块吃预算）。
    think_chars = 0
    if "<think>" in prose:
        after_open = prose.split("<think>", 1)[1]
        think_chars = len(after_open.split("</think>", 1)[0])
    try:
        Verdict.model_validate_json(raw_args)
        valid = True
    except Exception as e:
        valid = False
        print(f"[{tag}] VALIDATION FAIL: {str(e)[:200]}")
    row = {
        "tag": tag,
        "max_tokens": max_tokens,
        "first_text_at": round(first_text_at or -1, 2),
        "first_tool_at": round(first_tool_at or -1, 2),
        "finish_reason": finish_reason,
        "completion_tokens": (usage or {}).get("completion_tokens"),
        "prose_chars": len(prose),
        "think_chars": think_chars,
        "args_chars": len(raw_args),
        "valid": valid,
    }
    print(f"[{tag}] {row}")
    return row


async def main() -> None:
    """二轮 spike：表征首轮 1/6 的 arguments 截断。判别式 =
    finish_reason（length = 预算问题；tool_calls 但 args 残缺 = provider
    侧 bug）× max_tokens 显式预算（8192）是否消除截断。"""
    rows = []
    for i in range(6):
        rows.append(await one_round(f"default-{i}"))
    for i in range(6):
        rows.append(await one_round(f"cap8192-{i}", max_tokens=8192))
    trunc = [r for r in rows if not r.get("valid")]
    print("\n=== SUMMARY ===")
    print(f"rounds={len(rows)} truncated={len(trunc)}")
    for r in trunc:
        print("TRUNCATED:", r)
    think_sizes = sorted(r.get("think_chars", 0) for r in rows)
    print(f"think_chars distribution: {think_sizes}")


asyncio.run(main())
