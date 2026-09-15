"""A/B 探针（简报 T1 验收）：同一判决契约走两条线格式，行为等价性实证。

Tier 0 = ``generate``（json_object 散文载荷，现网形态）
Tier 1 = ``generate_with_tools``（原生 tool_calls，spike 已验通道）

同一 schema（``Verdict``）+ 同一 messages 喂两个通道，逐轮比对：
- 两条通道各自 schema-valid 的比率（Tier 1 的截断签名应走 LLMSchemaError
  浮出水面，而不是静默半截判决）
- 两侧判决的 action 一致率（线格式不得改变判决内容——层只换线格式，
  永不动判决契约）

只读探针，无 DB 无写盘。用法（apps/api/ 下）：
    uv run python ../../scratch/ab_tool_wire_probe.py [rounds]
"""

import asyncio
import sys

from pydantic import BaseModel, Field

from app.providers.llm.base import LLMError, LLMSchemaError
from app.providers.llm.minimax import minimax_client


class SourcedConstraint(BaseModel):
    value: str
    source: str = "inferred"


class Verdict(BaseModel):
    action: str
    answer: str | None = None
    tasks: list[dict] = Field(default_factory=list)
    constraints: list[SourcedConstraint] = Field(default_factory=list)


VERDICT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Submit the intent verdict for the user's request.",
            "parameters": Verdict.model_json_schema(),
        },
    }
]

SYSTEM = (
    "You are an intent parser. Reply with ONE short sentence saying what you "
    "understood, and the structured verdict. action is one of: ask (a "
    "clarifying question, put it in answer) / draft (a plan in tasks) / "
    "chat (pure conversation, put the reply in answer)."
)

PROMPTS = [
    "Caption my video in Chinese and French — Chinese bilingual — and dub a "
    "Spanish version in my own voice. Keep the 1:1 frame.",
    "把这条播客做成三篇 LinkedIn 长文，法语的。",
    "What can you do with a slide deck?",
]


def _messages(prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ]


async def one_tier0(prompt: str) -> tuple[str, Verdict | None, str | None]:
    """现网通道：json_object 散文载荷。返回 (channel, verdict, error_kind)。"""
    try:
        return "tier0", await minimax_client.generate(_messages(prompt), Verdict), None
    except LLMSchemaError:
        return "tier0", None, "schema"
    except LLMError as e:
        return "tier0", None, f"transport:{e.user_key}"


async def one_tier1(prompt: str) -> tuple[str, Verdict | None, str | None]:
    """新通道：原生 tool_calls。散文在 content 通道（本探针只读判决等价性，
    散文只印长度）；无 tool call = 线格式层面的 schema 类失败。"""
    try:
        result = await minimax_client.generate_with_tools(
            _messages(prompt), VERDICT_TOOL
        )
    except LLMSchemaError:
        return "tier1", None, "schema(truncated/malformed)"
    except LLMError as e:
        return "tier1", None, f"transport:{e.user_key}"
    calls = [c for c in result.tool_calls if c.name == "submit_verdict"]
    if not calls:
        print(f"  [tier1] prose-only ({len(result.content)} chars), no verdict call")
        return "tier1", None, "no_tool_call"
    try:
        return "tier1", Verdict.model_validate(calls[0].arguments), None
    except Exception:
        return "tier1", None, "contract"


async def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    rows: list[dict] = []
    for prompt in PROMPTS:
        for i in range(rounds):
            for probe in (one_tier0, one_tier1):
                channel, verdict, error = await probe(prompt)
                rows.append(
                    {
                        "prompt": prompt[:24],
                        "round": i,
                        "channel": channel,
                        "action": verdict.action if verdict else None,
                        "valid": verdict is not None,
                        "error": error,
                    }
                )
                print(rows[-1])

    print("\n=== SUMMARY ===")
    for channel in ("tier0", "tier1"):
        mine = [r for r in rows if r["channel"] == channel]
        valid = [r for r in mine if r["valid"]]
        print(f"{channel}: valid {len(valid)}/{len(mine)}")
        for r in mine:
            if not r["valid"]:
                print(f"  invalid: {r['error']}")
    # 判决内容等价性：同 prompt 同轮次两侧的 action 分布。
    for prompt in PROMPTS:
        key = prompt[:24]
        a = [r["action"] for r in rows if r["prompt"] == key and r["channel"] == "tier0" and r["valid"]]
        b = [r["action"] for r in rows if r["prompt"] == key and r["channel"] == "tier1" and r["valid"]]
        print(f"actions {key!r}: tier0={a} tier1={b}")


asyncio.run(main())
