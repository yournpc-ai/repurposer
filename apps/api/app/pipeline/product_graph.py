"""The Product Graph contract (I-PFA-01 / I-PFA-02 / I-PFA-02a / I-PFA-03 /
I-PFA-04, ADR-086; 施工合同 ``docs/tasks/product-flow-alignment.md`` §7 C-0).

四层分离（本条是前两层的唯一定义家）:

    Product Graph  ≠  Execution Graph  ≠  Frame/Layout  ≠  Reveal Animation

- **Product DAG** = read-face 后的用户可见图: product nodes（用户拥有、
  消费、验证或可能修改的产品对象）+ product edges（表达当前生产/消费关系
  的物料流边）。``task_book / preprocess / understand / plan / materialize /
  render / verify / checkpoint / worker / queue / retry`` 类概念永不是
  product node（I-PFA-01）——执行组（app.pipeline.*）本就不 stamp 节点，
  渗漏面 = task_book 文档与 morph modifier 两个既有 read-face 过滤，本模块
  把它们追认为**声明式 membership 谓词**。
- **rank** = Product DAG 上的拓扑深度（longest-path），是唯一的用户可见
  空间权威（I-PFA-02）。**输入边界（I-PFA-02a）**：只消费 ``video`` /
  ``audio`` / ``text`` 物料流边（含读时合成边中表达真实物料流的 A3-lite
  transcript→consumer 边——合成边是 rank 的合法输入，不是「读时补丁」）；
  ``ctx`` 引用流（task_book → 消费者的上下文边）**不参与** rank。当前
  图里不存在 lineage / presentation-only 边词（版本血缘住节点
  ``spec.output_ids``，从不是边）——若未来出生，它们同样不入 rank。
- **layout projection** = rank × PITCH 给出 x；y 座位 / w·h 预留 / 稳定锚
  沿用既有服务端帧（append-only 不变）。**layout 是 Product Graph 的
  projection，不是 Product Graph 本身。**
- **execution order**（I-PFA-04 的 C-2 消费点）= 同一 Product DAG 的拓扑
  序——``topological_order`` 与 rank 同一事实源，视觉坐标永不做执行依据。

**product visibility 准入闸（I-PFA-01，等效机制）**：visibility 声明在
**type 层**（媒介五值 = 产品对象，ADR-076 的 type 轴本来就是产品对象轴；
tool 是执行身份，永不是卡面身份），例外走 role/tool 两个显式枚举；
**未知 type 默认隐藏**（default-deny——新图节点类型不登记就不上画布）。
现行 read-face（B1-lite / B4-lite / ``_read_face`` 一帧映射）是本谓词的
执行机制，不是第二套规则。

Pure module: no DB, no ORM imports — node/edge inputs are duck-typed (ORM
rows or plain dicts, the read path carries both after A3-lite synthesis).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# ---- 词表（声明，非映射表——与 ADR-076 三轴对齐） -----------------------------

#: 媒介五值（ADR-076 词表 v3）——出生即产品对象的 type。
MEDIA_TYPES = frozenset({"text", "table", "image", "video", "audio"})

#: 过渡词（批 B4 / 历史清理收编中）——永不是产品对象：modifier = 装配卡上的
#: 杠杆（B4-lite），materialize = 执行概念（I-PFA-01 明列），只随 legacy
#: 读面一帧映射存活，formal 收编归各自历史批次，不在本契约激活。
TRANSITIONAL_TYPES = frozenset({"modifier", "materialize"})

#: legacy 出生词（读容忍——旧行的产品对象身份由 _read_face 一帧映射维持）。
#: generator/processor/agent 三死词的 legacy 行持有真实产物，按现行读面
#: 可见；它们永不再出生（AddNodeOp 词表已拒）。
LEGACY_VISIBLE_TYPES = frozenset({"asset", "document", "generator", "processor", "agent"})

#: role 层的隐藏枚举（B1-lite 的声明式形态）——task_book = 执行簿记，确认
#: 拍的座位是 dock pill（ADR-070），永不上画布。
HIDDEN_ROLES = frozenset({"task_book"})

#: tool 层的杠杆枚举（B4-lite 的声明式形态）——morph modifier 改写其生产者
#: 的同一批 output 行，终形态 = 装配卡上的杠杆，永不是节点。读面 B4-lite
#: 的「产物必须有人认领才隐藏」安全闸留在读路径（产物永不从画布消失），
#: 本谓词只声明 tool 集。
LEVER_TOOLS = frozenset({"reframe_clip", "add_music", "remove_filler"})

#: rank 的输入边界（I-PFA-02a）——物料流三值。``ctx`` 是上下文引用流
#: （task_book → 消费者），不是生产/消费关系，永不参与 rank。
RANK_EDGE_TYPES = frozenset({"video", "audio", "text"})

#: 投影律的横向间距（合同 §3 I-PFA-03：MIN_GAP 初值 = _PITCH）。镜像
#: graph_store._PITCH（464 = 最宽帧类 400 + _GAP_MAIN 64）——两镜像互引，
#: 禁第三份拷贝；取值以参数传入，本常量仅供契约文档与 fixture 引用。
PITCH = 464


# ---- duck-typed accessors（ORM 行与合成 dict 同吃） ----------------------------


def _get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _spec_of(node: Any) -> dict:
    spec = _get(node, "spec") or {}
    return dict(spec) if isinstance(spec, Mapping) else {}


# ---- membership 谓词（I-PFA-01） ----------------------------------------------


def is_product_node(row_type: str, spec: Mapping[str, Any] | None) -> bool:
    """One graph row's product visibility（声明式，读面 B1-lite/B4-lite 与
    _read_face 映射的契约形态）。

    - ``spec.role ∈ HIDDEN_ROLES`` → hidden（task_book，B1-lite）。
    - ``spec.tool ∈ LEVER_TOOLS`` → hidden（morph modifier，B4-lite；读路径
      的产物认领安全闸与本谓词叠加，不在此复制）。
    - ``type ∈ MEDIA_TYPES`` → visible（出生词表即产品对象）。
    - ``type ∈ TRANSITIONAL_TYPES`` → hidden（modifier/materialize 过渡词）。
    - ``type ∈ LEGACY_VISIBLE_TYPES`` → visible（读容忍：legacy 行持有真实
      产品对象——asset = 源素材、document = 转写稿/文档、generator 三死词
      的旧产物行）。
    - 其他（未知 / 未来 type）→ **hidden（准入闸 default-deny）**。
    """
    spec = spec or {}
    if str(spec.get("role") or "") in HIDDEN_ROLES:
        return False
    if str(spec.get("tool") or "") in LEVER_TOOLS:
        return False
    if row_type in MEDIA_TYPES:
        return True
    if row_type in LEGACY_VISIBLE_TYPES:
        return True
    return False


def is_rank_edge(edge_type: str) -> bool:
    """rank 的输入边界谓词（I-PFA-02a）：只认物料流三值。调用方负责先按
    is_product_node 过滤两端节点——触碰隐藏节点的边永不入 Product DAG。"""
    return edge_type in RANK_EDGE_TYPES


# ---- rank 与拓扑序（I-PFA-02 / I-PFA-04） --------------------------------------


def _rank_inputs(
    nodes: Iterable[Any], edges: Iterable[Any], gated: bool
) -> tuple[list[str], dict[str, list[str]]]:
    """(visible node ids, parents-by-child over rank edges) — the Product DAG
    in its rank-consumable form. Deterministic: ids sort by str."""
    visible = {
        str(_get(n, "id"))
        for n in nodes
        if not gated or is_product_node(str(_get(n, "type") or ""), _spec_of(n))
    }
    parents: dict[str, list[str]] = {nid: [] for nid in visible}
    for e in edges:
        if not is_rank_edge(str(_get(e, "edge_type") or "")):
            continue
        src, dst = str(_get(e, "from_node")), str(_get(e, "to_node"))
        if src in visible and dst in visible and src != dst:
            parents[dst].append(src)
    return sorted(visible), parents


def product_ranks(
    nodes: Iterable[Any], edges: Iterable[Any], *, gated: bool = True
) -> dict[str, int]:
    """Product DAG 的拓扑深度（longest-path over rank edges）——唯一的用户
    可见空间权威（I-PFA-02）。环防御：输入按契约是 DAG，但永不信任输入
    （layout.ts depthOf 同款 cycle guard）；成环节点回落 0 并被
    ``validate_product_graph`` 显式报出。

    ``gated=False`` = 执行拓扑消费（I-PFA-04，C-2 的 RunOp 座位）：visibility
    闸是画布准入门（I-PFA-01），不是执行拓扑过滤器——morph modifier 对画布
    隐藏但**是可执行步骤**，必须排在它的生产者与消费者之间；边输入边界
    （物料流三值）两种模式完全一致，只有节点过滤不同。"""
    visible, parents = _rank_inputs(nodes, edges, gated)
    memo: dict[str, int] = {}

    def depth(nid: str, trail: frozenset[str]) -> int:
        if nid in memo:
            return memo[nid]
        if nid in trail:
            return 0  # cycle guard — the validator names it
        ups = parents.get(nid, [])
        d = 0 if not ups else max(depth(u, trail | {nid}) for u in ups) + 1
        memo[nid] = d
        return d

    return {nid: depth(nid, frozenset()) for nid in visible}


def topological_order(nodes: Iterable[Any], edges: Iterable[Any]) -> list[str]:
    """执行序 = Product DAG 拓扑序（I-PFA-04 的 C-2 消费点）：rank 升序、
    同 rank 内按 id 字典序（确定性，不依赖 birth order / 插入序 / layout.x）。
    生产者恒先于消费者。"""
    ranks = product_ranks(nodes, edges)
    return sorted(ranks, key=lambda nid: (ranks[nid], nid))


# ---- projection 与 sibling 序（I-PFA-03） --------------------------------------


def project_x(rank: int, pitch: int = PITCH) -> int:
    """显示 x = rank 的投影（I-PFA-02：服务端出生帧的 x 不再是显示依据）。"""
    return rank * pitch


def sibling_order(nodes: Iterable[Any]) -> list[str]:
    """同 rank 列内的确定性 y 序（I-PFA-03：sibling 序稳定，不依赖 birth
    order）。键 = (帧 y 座位〔无座位置 +∞〕, id 字典序)——append-only 的
    服务端帧 y 是第一键（既有座位永不移动），id 是永确定的总序兜底。"""
    def key(n: Any) -> tuple[float, str]:
        layout = _get(n, "layout") or {}
        y = layout.get("y") if isinstance(layout, Mapping) else None
        return (float(y) if isinstance(y, (int, float)) else float("inf"), str(_get(n, "id")))

    return [str(_get(n, "id")) for n in sorted(nodes, key=key)]


# ---- 不变量校验（I-PFA-03；fixture 与 C-1 投影层共用） --------------------------


def validate_product_graph(
    nodes: Iterable[Any], edges: Iterable[Any], pitch: int = PITCH
) -> list[str]:
    """The direction invariant as an explicit violation list（空 = 绿）:

    - 每条 product edge 满足 ``rank(target) > rank(source)``；
    - 投影满足 ``x(target) > x(source)``（x = rank × PITCH，PITCH = MIN_GAP
      初值——同 rank 永不发生，故严格大于恒成立）；
    - 成环（输入违约）显式报出——cycle guard 的静默回落永不当绿。
    """
    node_list = list(nodes)
    ranks = product_ranks(node_list, edges)
    visible = set(ranks)
    violations: list[str] = []
    for e in edges:
        if not is_rank_edge(str(_get(e, "edge_type") or "")):
            continue
        src, dst = str(_get(e, "from_node")), str(_get(e, "to_node"))
        if src not in visible or dst not in visible or src == dst:
            continue
        if ranks[dst] <= ranks[src]:
            violations.append(
                f"rank violation: {src} (rank {ranks[src]}) -> "
                f"{dst} (rank {ranks[dst]})"
            )
        if project_x(ranks[dst], pitch) <= project_x(ranks[src], pitch):
            violations.append(
                f"projection violation: {src} (x {project_x(ranks[src], pitch)}) "
                f"-> {dst} (x {project_x(ranks[dst], pitch)})"
            )
    # 环侦测：任一 product edge 两端 rank 相等且互达 = cycle guard 吸收过。
    # （longest-path 在 DAG 上恒给严格大于；等号只可能来自成环回落。）
    return violations


__all__ = [
    "HIDDEN_ROLES",
    "LEGACY_VISIBLE_TYPES",
    "LEVER_TOOLS",
    "MEDIA_TYPES",
    "PITCH",
    "RANK_EDGE_TYPES",
    "TRANSITIONAL_TYPES",
    "is_product_node",
    "is_rank_edge",
    "product_ranks",
    "project_x",
    "sibling_order",
    "topological_order",
    "validate_product_graph",
]
