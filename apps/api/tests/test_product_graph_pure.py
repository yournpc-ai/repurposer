"""Canonical Product Graph fixture (施工合同 §7 C-0; I-PFA-01/02/02a/03/04).

No DB, no LLM, no HTTP — plain dict rows against the pure contract module
``app.pipeline.product_graph``.

北极星场景的最小产品图（合同 §7 C-0 的 canonical graph）::

    Source Video ──text──► Transcript ──text──► ZH Subtitles ──text──► ZH Video
         │                 │                                          ▲
         │                 └──text──► FR Subtitles ──text──► FR Video ┤
         └──────────────────video────────────────► ZH Video ──────────┘
         └──────────────────video────────────────► FR Video

（asset→asm 的 video 边 = 装配站消费源素材，现行真实边，见 graph_fill 的
connect 座位；rank 由最长路径决定——asm = 3 层，不是 1 层。）

防「几何绿、语义错」假绿：本 fixture 同时断言五件事——① node membership、
② edge membership、③ rank、④ x 方向、⑤ sibling 序确定性；并带负例（丢
Transcript 层 / 反向边 / ctx 污染 / 执行概念渗漏），图本身错时 fixture
必须红。
"""

from __future__ import annotations

import itertools

from app.pipeline.product_graph import (
    PITCH,
    is_product_node,
    is_rank_edge,
    product_ranks,
    project_x,
    sibling_order,
    topological_order,
    validate_product_graph,
)


def _node(nid, type_, spec=None, y=None):
    layout = {"x": 0, "y": y} if y is not None else {}
    return {"id": nid, "type": type_, "spec": spec or {}, "layout": layout}


def _edge(src, dst, edge_type):
    return {"from_node": src, "to_node": dst, "edge_type": edge_type}


# ---- canonical fixture（北极星六节点 + 三个 decoy） ------------------------------

PRODUCT_IDS = ["src", "tr", "zh_doc", "fr_doc", "zh_asm", "fr_asm"]

NODES = [
    _node("src", "video", y=0),  # Source Video（源素材）
    _node("tr", "text", y=0),  # Transcript
    _node("zh_doc", "text", y=0),  # ZH Bilingual Subtitles（文档站）
    _node("fr_doc", "text", y=176),  # FR Subtitles
    _node("zh_asm", "video", y=0),  # ZH Video（装配站）
    _node("fr_asm", "video", y=560),  # FR Video
    # decoys —— 执行概念与过渡词永不是 product node（I-PFA-01）
    _node("book", "text", spec={"role": "task_book"}, y=0),  # B1-lite
    _node("mod", "modifier", spec={"tool": "reframe_clip"}, y=0),  # B4-lite
    _node("mystery", "worker"),  # 未知 type → default-deny 准入闸
]

EDGES = [
    _edge("src", "tr", "text"),
    _edge("tr", "zh_doc", "text"),
    _edge("tr", "fr_doc", "text"),
    _edge("zh_doc", "zh_asm", "text"),
    _edge("fr_doc", "fr_asm", "text"),
    _edge("src", "zh_asm", "video"),
    _edge("src", "fr_asm", "video"),
    # decoy edges —— ctx 引用流不入 rank（I-PFA-02a）；触碰隐藏节点的边
    # 永不入 Product DAG。
    _edge("book", "zh_asm", "ctx"),
    _edge("book", "fr_asm", "ctx"),
    _edge("mod", "zh_asm", "video"),  # 隐藏节点出发，整边排除
]

EXPECTED_RANKS = {
    "src": 0,
    "tr": 1,
    "zh_doc": 2,
    "fr_doc": 2,
    "zh_asm": 3,
    "fr_asm": 3,
}


# ---- ① node membership ----------------------------------------------------------


def test_node_membership_exactly_the_six_product_objects():
    visible = {
        str(n["id"])
        for n in NODES
        if is_product_node(n["type"], n["spec"])
    }
    assert visible == set(PRODUCT_IDS)


def test_hidden_role_and_lever_tool_and_unknown_type_are_denied():
    assert not is_product_node("text", {"role": "task_book"})
    assert not is_product_node("modifier", {"tool": "reframe_clip"})
    assert not is_product_node("modifier", {"tool": "add_music"})
    assert not is_product_node("modifier", {"tool": "remove_filler"})
    assert not is_product_node("materialize", {})  # 过渡词（I-PFA-01 明列）
    assert not is_product_node("worker", {})  # 未知 type → default-deny
    assert not is_product_node("checkpoint", {})


def test_media_five_and_legacy_read_tolerance_are_visible():
    for t in ("text", "table", "image", "video", "audio"):
        assert is_product_node(t, {})
    for t in ("asset", "document", "generator", "processor", "agent"):
        assert is_product_node(t, {})


# ---- ② edge membership ----------------------------------------------------------


def test_ctx_is_not_a_rank_edge():
    assert not is_rank_edge("ctx")
    for t in ("video", "audio", "text"):
        assert is_rank_edge(t)


def test_rank_edges_only_connect_product_nodes():
    # ctx 边与 mod→zh_asm 边对 rank 零贡献：把 task_book / modifier 从输入里
    # 物理删掉，rank 结果必须不变（它们从未进入 Product DAG）。
    ranks_full = product_ranks(NODES, EDGES)
    ranks_shaved = product_ranks(
        [n for n in NODES if n["id"] in PRODUCT_IDS],
        [e for e in EDGES if e["edge_type"] != "ctx" and e["from_node"] != "mod"],
    )
    assert ranks_full == ranks_shaved


# ---- ③ rank authority -----------------------------------------------------------


def test_canonical_ranks_are_0_1_2_2_3_3():
    assert product_ranks(NODES, EDGES) == EXPECTED_RANKS


def test_rank_never_comes_from_birth_order_or_layout():
    # 乱序 + 乱 y 座位 → rank 纹丝不动（rank 的唯一来源 = 拓扑）。
    shuffled = list(reversed(NODES))
    assert product_ranks(shuffled, list(reversed(EDGES))) == EXPECTED_RANKS


# ---- ④ x direction（direction invariant） ----------------------------------------


def test_direction_invariant_holds_on_the_canonical_graph():
    assert validate_product_graph(NODES, EDGES) == []
    ranks = product_ranks(NODES, EDGES)
    for e in EDGES:
        if not is_rank_edge(e["edge_type"]):
            continue
        s, d = e["from_node"], e["to_node"]
        if s not in ranks or d not in ranks:
            continue
        assert ranks[d] > ranks[s]
        assert project_x(ranks[d], PITCH) > project_x(ranks[s], PITCH)


# ---- ⑤ sibling order determinism ---------------------------------------------------


def test_sibling_order_is_insertion_order_independent():
    baseline = sibling_order(NODES)
    for perm in itertools.islice(itertools.permutations(NODES), 24):
        assert sibling_order(list(perm)) == baseline


def test_execution_order_is_dag_topology_never_layout_x():
    order = topological_order(NODES, EDGES)
    pos = {nid: i for i, nid in enumerate(order)}
    assert set(order) == set(PRODUCT_IDS)
    for e in EDGES:
        if not is_rank_edge(e["edge_type"]):
            continue
        s, d = e["from_node"], e["to_node"]
        if s in pos and d in pos:
            assert pos[s] < pos[d], f"producer {s} must precede consumer {d}"


# ---- 负例（图本身错时 fixture 必须红） ----------------------------------------------


def test_negative_missing_transcript_layer_changes_ranks():
    # Source 直挂 docs（丢 Transcript 层）→ rank 表必须变，否则 fixture 是瞎子。
    broken_edges = [e for e in EDGES if e["from_node"] != "tr" and e["to_node"] != "tr"]
    broken_edges += [_edge("src", "zh_doc", "text"), _edge("src", "fr_doc", "text")]
    broken_nodes = [n for n in NODES if n["id"] != "tr"]
    assert product_ranks(broken_nodes, broken_edges) != EXPECTED_RANKS


def test_negative_reversed_edge_is_a_named_violation():
    broken = EDGES + [_edge("zh_asm", "src", "video")]  # 消费者反哺源 → 环
    violations = validate_product_graph(NODES, broken)
    assert violations, "a reversed material-flow edge must be reported, not absorbed"
    assert any("zh_asm" in v and "src" in v for v in violations)


def test_negative_decoy_in_product_set_fails_membership():
    # 若执行概念被误判可见，membership 断言红（①的反向保险丝）。
    visible = {
        str(n["id"]) for n in NODES if is_product_node(n["type"], n["spec"])
    }
    assert "book" not in visible and "mod" not in visible and "mystery" not in visible


# ---- I-EXPLORE-01 rank/visibility blindness (ADR-088 §4; 2026-09-22 迭代一) ----


def test_exploration_family_fails_product_membership_default_deny():
    """探索族对 Product DAG 结构性盲: type="exploration" 不在媒介五值也
    不在 legacy 容忍表 — the predicate's default-deny IS the rank half of
    I-EXPLORE-01, and this lock keeps a future vocabulary addition from
    silently admitting the family into rank math."""
    spec = {"prototype": "exploration", "exploration_kind": "candidate_set"}
    assert is_product_node("exploration", spec) is False
    assert is_product_node("exploration", {}) is False


def test_product_ranks_never_return_an_exploration_rank():
    nodes = NODES + [
        {"id": "xcand", "type": "exploration",
         "spec": {"prototype": "exploration", "exploration_kind": "candidate_set"},
         "layout": {"x": -464, "y": 0, "w": 340, "h": 96}},
    ]
    ranks = product_ranks(nodes, EDGES)
    assert "xcand" not in ranks
