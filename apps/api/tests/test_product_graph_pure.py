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
    display_rank_projection,
    display_ranks,
    effective_rank_edges,
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


# ---- ADR-098 B1: effective_rank_edges（Effective Product Graph 唯一拓扑层） ----
#
# 事故同构 fixture（项目 62594b0b-c0fd-40a9-89fe-6e0a055f7265 的取证原型,
# dev DB 实录）: 素材 → 转写稿 → 金句卡（write_quotes draft）。持久边只有
# asset→transcript / asset→quotes（legacy stamp 把 transcript 留成 LEAF,
# consumers 从 asset 直连 = 执行真相）; 合成边 transcript→quotes 承载物料流
# 「源 → 文档 → 装配」三列阅读法。

A1, T1, Q1 = "asset-1", "transcript-1", "quotes-1"

EFF_NODES = [
    _node(A1, "asset", spec={"asset_id": "asset-row-1", "asset_type": "video"}, y=0),
    _node(T1, "document", spec={"role": "transcript", "asset_id": "asset-row-1"}, y=0),
    _node(Q1, "image", spec={"tool": "write_quotes"}, y=0),
]


def _pedge(src, dst, edge_type):
    """Persisted edge row shape — ports ride along (合成行的判别锚)。"""
    return {
        "from_node": src,
        "to_node": dst,
        "edge_type": edge_type,
        "from_port": f"out:{edge_type}",
        "to_port": f"in:{edge_type}",
    }


EFF_EDGES = [_pedge(A1, T1, "text"), _pedge(A1, Q1, "text")]


def test_effective_rank_edges_synthesizes_transcript_consumer_leg():
    eff = effective_rank_edges(EFF_NODES, EFF_EDGES)
    # 持久边先行、顺序保留; 合成行追加在后, dict 出生, 端口戳 out:text/in:text。
    assert eff[: len(EFF_EDGES)] == EFF_EDGES
    assert len(eff) == len(EFF_EDGES) + 1
    syn = eff[-1]
    assert (syn["from_node"], syn["to_node"], syn["edge_type"]) == (T1, Q1, "text")
    assert (syn["from_port"], syn["to_port"]) == ("out:text", "in:text")
    assert "id" in syn


def test_effective_rank_edges_never_mutates_inputs_and_excludes_self_loops():
    before = list(EFF_EDGES)
    eff = effective_rank_edges(EFF_NODES, EFF_EDGES)
    assert EFF_EDGES == before and eff is not EFF_EDGES
    # 自环排除: asset→transcript 的出边永不合成 transcript→transcript。
    assert all(
        not (e["from_node"] == T1 and e["to_node"] == T1)
        for e in eff[len(EFF_EDGES):]
    )


def test_effective_rank_edges_no_asset_link_no_synthesis():
    # transcript 缺 asset_id / asset 节点缺 asset_id → 合成规则不触发
    #（graph_store 岛测试的既有 fixture 形态——零资产链接, 零合成）。
    nodes = [
        _node("a", "asset", spec={"asset_type": "video"}),
        _node("t", "document", spec={"role": "transcript"}),
        _node("c", "text"),
    ]
    edges = [_pedge("a", "t", "text"), _pedge("a", "c", "text")]
    assert effective_rank_edges(nodes, edges) == edges


def test_lineage_edge_never_occupies_the_dedup_triple():
    """ADR-098 §1 铁律②（律法先于首例——2026-10-01 dev DB 实测 lineage 边
    全库零行）: artifact 盖章链的 deliverable 自己的血缘边
    （transcript→deliverable, 端口戳 out:lineage）**永不占合成去重三元组**
    ——否则合成边被顶掉, deliverable 深度退回 1, 与 writer 队列裂带。"""
    d = "deliverable-1"
    nodes = EFF_NODES[:2] + [_node(d, "video", spec={"tool": "select_clips"})]
    edges = [
        _pedge(A1, T1, "text"),
        _pedge(A1, d, "video"),
        {
            "from_node": T1,
            "to_node": d,
            "edge_type": "text",
            "from_port": "out:lineage",
            "to_port": "in:lineage",
        },
    ]
    eff = effective_rank_edges(nodes, edges)
    syn = [e for e in eff if e.get("from_port") == "out:text" and e not in edges]
    assert len(syn) == 1
    assert (syn[0]["from_node"], syn[0]["to_node"]) == (T1, d)
    # 合成边生效: deliverable 的 effective 深度 = 2（血缘边永不入 rank）。
    assert product_ranks(nodes, eff)[d] == 2


def test_real_text_edge_still_dedups_synthesis():
    """rank 合法真边照常占位: canonical 出生边（graph_fill stamp 的 doc 站
    腿）在场时, 同一 leg 永不double-render（A3-lite 与真边两源去重）。"""
    d = "asm-1"
    nodes = EFF_NODES[:2] + [_node(d, "video")]
    edges = [_pedge(A1, T1, "text"), _pedge(A1, d, "video"), _pedge(T1, d, "text")]
    assert len(effective_rank_edges(nodes, edges)) == 3


def test_execution_side_never_consumes_effective_edges():
    """B1 探针锁（执行侧零消费）: 同一 fixture 下, RunOp 闭包 / stale 传播 /
    工作流编译吃**持久边**（ungated product_ranks 的输入永是持久集）——合成
    边永不过界（显示/空间事实 ≠ 执行事实, ADR-086; ADR-098 §1）。"""
    exec_ranks = product_ranks(EFF_NODES, EFF_EDGES, gated=False)
    assert exec_ranks[Q1] == 1  # 持久边只有 asset→quotes —— 执行拓扑不变
    eff = effective_rank_edges(EFF_NODES, EFF_EDGES)
    assert product_ranks(EFF_NODES, eff, gated=False)[Q1] == 2  # 显示层吃 effective
    # 无岛时 display = raw: 新链读面 rank = 0/1/2（事故形状的 B1 后形态）。
    assert display_ranks(EFF_NODES, eff, []) == {
        A1: 0,
        T1: 1,
        Q1: 2,
    }


def test_display_ranks_writers_share_one_island_band():
    """B1 验收②: transcript + 3 writers——三 writer 共享一个 effective rank
    与一个 effective 父签名 → 同岛同列同 rank; transcript 单成员家庭不生岛,
    带 1 零廊道预留（writers 的 band origin 不被推高）。"""
    ws = ["w1", "w2", "w3"]
    nodes = EFF_NODES[:2] + [
        _node(w, "text", spec={"tool": "write_post"}, y=0) for w in ws
    ]
    edges = [_pedge(A1, T1, "text")] + [_pedge(A1, w, "text") for w in ws]
    eff = effective_rank_edges(nodes, edges)
    island = {
        "id": "isl-1",
        "depth": 2,
        "cols": 2,
        "cap": 4,
        "origin_x": 2 * PITCH,
        "origin_y": -176,
        "row_h": 576,
    }
    seated = []
    for n in nodes:
        n = dict(n)
        if n["id"] in ws:
            n["island_id"] = "isl-1"
            n["island_seq"] = ws.index(n["id"])
        seated.append(n)
    ranks = display_ranks(seated, eff, [island])
    assert ranks[T1] == 1
    assert [ranks[w] for w in ws] == [2, 2, 2]


# ---- ADR-098 B3: legacy mixed island 读时归一（cohort 拆分 + seq 重定基） ------
#
# B1 前出生的岛按写时拓扑归组（transcript 与 consumer 同代）; 读时 effective
# rank 把成员裂到不同带 —— 混合岛逐 cohort 判定: ≥2 享 corridor（重定基
# seq）, 单成员 corridor 全死（slots 不记 / 无 col 加成 / spec.island 不戳）。
# 零迁移: 存储帧不动, 读时归一即修复。


def _island(iid, depth, cols=2, cap=4):
    return {
        "id": iid,
        "depth": depth,
        "cols": cols,
        "cap": cap,
        "origin_x": depth * PITCH,
        "origin_y": -88,
        "row_h": 576,
    }


def _seat(node, iid, seq):
    n = dict(node)
    n["island_id"] = iid
    n["island_seq"] = seq
    return n


def test_accident_isomorph_mixed_island_both_cohorts_dead():
    """总验收 A（事故同构, 项目 62594b0b 实录形状）: 岛 {transcript seq0,
    quotes seq1} cols=2 depth=1（写时同代出生）。读时 effective rank 裂开
    （1 vs 2）→ 两个单成员 cohort 全死 → 无 slots 预留、无 col 加成、
    无 spec.island 戳（dead 集）; rank 0/1/2 → x 0/524/1048, 合成边
    B→C 方向不变量成立。"""
    island = _island("isl-accident", depth=1, cols=2)
    seated = [
        EFF_NODES[0],
        _seat(EFF_NODES[1], "isl-accident", 0),
        _seat(EFF_NODES[2], "isl-accident", 1),
    ]
    eff = effective_rank_edges(seated, EFF_EDGES)
    ranks, dead = display_rank_projection(seated, eff, [island])
    assert ranks == {A1: 0, T1: 1, Q1: 2}
    assert [project_x(ranks[n], PITCH) for n in (A1, T1, Q1)] == [0, PITCH, 2 * PITCH]
    assert dead == frozenset({T1, Q1})  # 两者的 corridor 全死 → 读面不戳岛
    assert validate_product_graph(seated, eff) == []  # E: 方向不变量零违规
    # display_ranks 包装器与同 fixture 同数。
    assert display_ranks(seated, eff, [island]) == ranks


def test_legacy_mixed_island_writers_cohort_keeps_corridor():
    """B3 验收②: legacy 混合岛 {transcript + 3 writers} —— transcript cohort
    死（单成员）, writers cohort 保 corridor（同 rank 2 同 col 0）; 带 1 的
    死廊道不再推高后续带（writers band_origin(2)=2 而非 3）; 更深带只被
    writers 岛的活廊道抬高（+1）。"""
    ws = ["w1", "w2", "w3"]
    d3 = "downstream-1"
    nodes = (
        EFF_NODES[:2]
        + [_node(w, "text", spec={"tool": "write_post"}, y=0) for w in ws]
        + [_node(d3, "video", spec={"tool": "select_clips"}, y=0)]
    )
    edges = (
        [_pedge(A1, T1, "text")]
        + [_pedge(A1, w, "text") for w in ws]
        + [_pedge("w1", d3, "video")]
    )
    island = _island("isl-legacy", depth=1, cols=2)
    seated = [nodes[0], _seat(nodes[1], "isl-legacy", 0)] + [
        _seat(n, "isl-legacy", i + 1) for i, n in enumerate(nodes[2:5])
    ] + [nodes[5]]
    eff = effective_rank_edges(seated, edges)
    ranks, dead = display_rank_projection(seated, eff, [island])
    assert dead == frozenset({T1})
    assert ranks[T1] == 1
    assert [ranks[w] for w in ws] == [2, 2, 2]
    # writers 岛在带 2 的活廊道（cols=2）抬高更深带: raw 3 → 显示 4。
    assert ranks[d3] == 4


def test_legacy_mixed_island_fifth_writer_lands_next_column():
    """总验收 C: 第 5 writer 到来 → cohort 内重定基 seq 4 → col 1 进下一列;
    既有四卡 x 不动（重定基保序 —— append-only 回归断言）; transcript 的
    死 corridor 不受影响。"""
    ws = ["w1", "w2", "w3", "w4", "w5"]
    nodes = EFF_NODES[:2] + [
        _node(w, "text", spec={"tool": "write_post"}, y=0) for w in ws
    ]
    edges = [_pedge(A1, T1, "text")] + [_pedge(A1, w, "text") for w in ws]
    island = _island("isl-legacy", depth=1, cols=2)
    seated = [nodes[0], _seat(nodes[1], "isl-legacy", 0)] + [
        _seat(n, "isl-legacy", i + 1) for i, n in enumerate(nodes[2:])
    ]
    eff = effective_rank_edges(seated, edges)
    ranks, dead = display_rank_projection(seated, eff, [island])
    assert dead == frozenset({T1})
    assert [ranks[w] for w in ws[:4]] == [2, 2, 2, 2]  # 既有四卡不动
    assert ranks["w5"] == 3  # 第 5 writer → 岛第二列（cap=4 → seq 4 // 4 = 1）


def test_shelf_island_fifth_asset_never_moves_downstream():
    """总验收 D: 货架岛（多素材同带同父签名）加第 5 成员 —— 岛的 cols 出生
    定格, slots 记账不变, 全部下游 x 不动（append-only）。"""
    assets = [
        _node(f"a{i}", "asset", spec={"asset_id": f"row-{i}", "asset_type": "video"}, y=0)
        for i in range(4)
    ]
    consumer = _node("c1", "video", spec={"tool": "select_clips"}, y=0)
    edges = [_pedge("a0", "c1", "video")]

    def ranks_with(member_count):
        island = _island("isl-shelf", depth=0, cols=2)
        seated = [
            _seat(n, "isl-shelf", i) for i, n in enumerate(assets[:member_count])
        ] + [consumer]
        eff = effective_rank_edges(seated, edges)
        return display_rank_projection(seated, eff, [island])

    before, dead_before = ranks_with(4)
    a5 = _node("a4", "asset", spec={"asset_id": "row-4", "asset_type": "video"}, y=0)
    seated5 = [_seat(n, "isl-shelf", i) for i, n in enumerate(assets)] + [
        _seat(a5, "isl-shelf", 4),
        consumer,
    ]
    after, dead_after = display_rank_projection(
        seated5, effective_rank_edges(seated5, edges), [_island("isl-shelf", depth=0, cols=2)]
    )
    assert dead_before == frozenset() and dead_after == frozenset()  # 单 cohort 不动
    assert after["c1"] == before["c1"]  # 下游 x 不动
    assert [after[f"a{i}"] for i in range(4)] == [before[f"a{i}"] for i in range(4)]
    assert after["a4"] == 1  # 第 5 成员进岛第二列（带 0 + col 1）


def test_single_cohort_island_keeps_legacy_behavior():
    """单 cohort 岛 = 现行行为不动（即使只剩一个成员——第二次 promotion 出生
    的岛被删到单员时, 廊道预留照旧; raw island_seq // cap, 不重定基）。"""
    nodes = [
        _node("src", "asset", spec={"asset_id": "row-x", "asset_type": "video"}, y=0),
        _node("lone", "text", y=0),
        _node("deep", "text", y=0),
    ]
    edges = [_pedge("src", "lone", "text"), _pedge("lone", "deep", "text")]
    island = _island("isl-lone", depth=1, cols=2)
    seated = [nodes[0], _seat(nodes[1], "isl-lone", 0), nodes[2]]
    ranks, dead = display_rank_projection(seated, edges, [island])
    assert dead == frozenset()
    assert ranks["lone"] == 1
    # 廊道预留照旧撑开更深带: raw 2 → band_origin(2) = 2 + (2-1) = 3。
    assert ranks["deep"] == 3


def test_asset_deletion_reflows_surviving_consumers():
    """ADR-098 §3 显式 lifecycle reflow 例外（命名, 非 regression）: 素材删除
    （remove_asset_node 杀素材孪生 + 转写稿, 边结构级联; 消费者 spec 无
    asset_id 故幸存）→ 幸存消费者 rank 重算左移（可掉 0）。本测试只断言
    行为发生且被命名, 不断言不动。"""
    eff = effective_rank_edges(EFF_NODES, EFF_EDGES)
    assert display_ranks(EFF_NODES, eff, [])[Q1] == 2
    # remove_asset_node 之后: asset + transcript 及其边级联消失, quotes 幸存。
    survivors = [EFF_NODES[2]]
    assert display_ranks(survivors, [], [])[Q1] == 0  # 左移 = 显式后果
