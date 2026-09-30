"""The Product Graph contract (I-PFA-01 / I-PFA-02 / I-PFA-02a / I-PFA-03 /
I-PFA-04, ADR-086; 施工合同 ``docs/tasks/product-flow-alignment.md`` §7 C-0).

四层分离（本条是前两层的唯一定义家）:

    Product Graph  ≠  Execution Graph  ≠  Frame/Layout  ≠  Reveal Animation

- **Product DAG** = read-face 后的用户可见图: product nodes（用户拥有、
  消费、验证或可能修改的产品对象）+ product edges（表达当前生产/消费关系
  的物料流边）。``task_book / preprocess / understand / plan / materialize /
  render / verify / checkpoint / worker / queue / retry`` 类概念永不是
  product node（I-PFA-01）——执行组（app.pipeline.*）本就不 stamp 节点；
  task_book 的生产已止（v4.2 C1-b de-stamp，2026-09-26 封板），渗漏面 =
  它的 legacy 存量行与 morph modifier 两个 read-face 过滤，本模块把它们
  追认为**声明式 membership 谓词**。
- **rank** = Product DAG 上的拓扑深度（longest-path），是唯一的用户可见
  空间权威（I-PFA-02）。**输入边界（I-PFA-02a）**：只消费 ``video`` /
  ``audio`` / ``text`` 物料流边（含读时合成边中表达真实物料流的 A3-lite
  transcript→consumer 边——合成边是 rank 的合法输入，不是「读时补丁」）；
  ``ctx`` 引用流（task_book → 消费者的上下文边）**不参与** rank。lineage /
  presentation-only 边词同样**永不入 rank**（ADR-097 §9 的 transcript→
  deliverable 真边已出生——端口标记 ``out:lineage``，``_rank_inputs`` 显式
  排除；版本血缘的另一半住节点 ``spec.output_ids``，从不是边）。
- **layout projection** = rank × PITCH 给出 x；y 座位 / w·h 预留 / 稳定锚
  沿用既有服务端帧（append-only 不变）。**layout 是 Product Graph 的
  projection，不是 Product Graph 本身。**
- **execution order**（I-PFA-04 的 C-2 消费点）= 同一 Product DAG 的拓扑
  序——``topological_order`` 与 rank 同一事实源，视觉坐标永不做执行依据。

**同一事实源 + 消费面 gate（2026-09-18 用户钉死）**：rank 算法/拓扑事实源
只有一个；但消费面允许有不同的 gate——Canvas 吃 gated rank（visibility
准入门过滤后），RunOp 吃 ungated rank（modifier 是隐藏但可执行的步骤）。
**gate 不得改变 Product DAG 的生产依赖事实**——它只决定「谁被那个消费面
看见/排序」，永不增删边、永不改写依赖。看到 ``gated=False`` 不要问
「为什么两个消费面不用同一个 nodes」——答案是它们用同一个 DAG，
只是过了不同的门。

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

#: role 层的隐藏枚举——task_book = 执行簿记，确认拍的座位是 dock pill
#: （ADR-070），永不上画布。生产已止（v4.2 C1-b de-stamp，2026-09-26 封板）——
#: 本词只服务 legacy 行的读面/迁移期闸门。
HIDDEN_ROLES = frozenset({"task_book"})

#: tool 层的杠杆枚举（B4-lite 的声明式形态）——morph modifier 改写其生产者
#: 的同一批 output 行，终形态 = 装配卡上的杠杆，永不是节点。读面 B4-lite
#: 的「产物必须有人认领才隐藏」安全闸留在读路径（产物永不从画布消失），
#: 本谓词只声明 tool 集。
LEVER_TOOLS = frozenset({"reframe_clip", "add_music", "remove_filler"})

#: rank 的输入边界（I-PFA-02a）——物料流三值。``ctx`` 是上下文引用流
#: （task_book → 消费者），不是生产/消费关系，永不参与 rank。
RANK_EDGE_TYPES = frozenset({"video", "audio", "text"})

#: 探索族（ADR-088 §4，NAMING N-55）——Candidate Set / Select / Content Plan
#: 的家族词。Workspace 合同 v4.2 C1 (2026-09-26 封板): 探索族永不进图——
#: 家族的新家 = exploration_rows 表（spec.prototype 仍带本词），
#: EXPLORATION_NODE_TYPE 只剩两个读面座位：/graph 与 chat context 对
#: legacy ``type="exploration"`` 图行的读过滤，以及执行写门
#: （graph_store）对 legacy 行的反门卫兵。I-EXPLORE-01 现在结构性成立
#: （探索产物根本不是图行）。叶子座位不变：两门的共享词汇不落任一门内，
#: 防环。
EXPLORATION_PROTOTYPE = "exploration"
EXPLORATION_NODE_TYPE = "exploration"

#: 投影律的横向间距（合同 §3 I-PFA-03：MIN_GAP 初值 = _PITCH）。镜像
#: graph_store._PITCH（524 = 最宽帧类 400 + _GAP_MAIN 124）——两镜像互引，
#: 禁第三份拷贝；取值以参数传入，本常量仅供契约文档与 fixture 引用。
PITCH = 524


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
        # lineage 边永不入 rank（ADR-097 §5 — display-only 真边, 端口标记;
        # 它表达作品血缘, 不是生产/消费的物料流）。
        if is_lineage_edge(e):
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


def display_ranks(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    islands: Iterable[Any],
    *,
    gated: bool = True,
) -> dict[str, int]:
    """画布显示 rank（I-PFA-02 的岛化扩展, Workspace 合同 v4.2 C6）——
    /graph 读面的唯一 rank 来源.

    岛 = 局部打包域: a sibling group's island reserves ``cols`` consecutive
    rank SLOTS at its band, frozen at birth (the growth corridor). Members
    take ``band_origin + (seq // cap)``; a band's slot width = its widest
    island's reserved cols (default 1 — the legacy 1:1 depth↔rank mapping
    is the island-free special case). The corridor inflates LATER bands'
    origins read-time — a retroactive island born with deeper bands already
    settled freezes at cols=1 (graph_store._assign_islands' birth clamp),
    so existing nodes' display x NEVER moves (append-only 保序律 in rank
    space, not just frame space).

    Direction invariant holds by construction: slots ≥ 1 per band, so
    rank(to) > rank(from) for every product edge. ``gated`` mirrors
    product_ranks; the RunOp execution topology (gated=False) stays on raw
    product_ranks — islands are a DISPLAY concern, never execution."""
    raw = product_ranks(nodes, edges, gated=gated)
    node_list = list(nodes)
    islands_by_id = {str(_get(i, "id")): i for i in islands}
    island_of: dict[str, Any] = {}
    for n in node_list:
        iid = _get(n, "island_id")
        if iid is not None and str(iid) in islands_by_id:
            island_of[str(_get(n, "id"))] = islands_by_id[str(iid)]
    if not island_of:
        return raw
    # The island's band = its members' shared raw rank (siblings share a
    # topological generation by construction); members absent from the
    # gated read frame contribute nothing.
    slots: dict[int, int] = {}
    for nid, isl in island_of.items():
        d = raw.get(nid)
        if d is None:
            continue
        slots[d] = max(slots.get(d, 1), int(_get(isl, "cols") or 1))
    if not slots:
        return raw

    def band_origin(d: int) -> int:
        return d + sum(s - 1 for b, s in slots.items() if b < d)

    nodes_by_id = {str(_get(n, "id")): n for n in node_list}
    out: dict[str, int] = {}
    for nid, d in raw.items():
        isl = island_of.get(nid)
        col = 0
        if isl is not None:
            cap = max(1, int(_get(isl, "cap") or 1))
            cols = max(1, int(_get(isl, "cols") or 1))
            seq = int(_get(nodes_by_id[nid], "island_seq") or 0)
            col = min(seq // cap, cols - 1)
        out[nid] = band_origin(d) + col
    return out


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
        # ADR-097 §5: lineage 血缘边永不是 product edge——方向不变量不适
        # 用 (display-only, 零 rank 权威; 一条律两镜像 = layout.ts
        # projectSettledFrames 的豁免)。
        if is_lineage_edge(e):
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


# ---- Product Artifact Ontology（ADR-097 Phase 1 — canonical 四字段 + 两层门） ----
#
# 身份 = 编译期 stamp 进 spec JSONB 的事实（canonical 四字段 work_key /
# artifact_key / artifact_name / artifact_role），读面**永不推断**成员
# （ADR-097 §2 第一承重条款：禁从 rank / 邻接 / step 序 / 深度 / created_at /
# output 归属 / 尾位 / 相同 output_ids / fill_key 相似性猜测）。本节的内核：
#
# - ``assign_artifact_groups`` — 编译期分组（graph_fill stamp core 的唯一座
#   位）：从 run 内编译的 step-input 家族 DAG 分配 (slot, role)。这是编译器
#   的**分配**行为不是读时推断——分派随降生凝固进 spec，此后一切读取只认
#   key。第二层门：``is_product_node`` 零改动，角色投影独立。
# - ``artifact_fields_for_birth`` — stamp 甄别真值表：出生写入 / key 冻结 /
#   legacy 永不补写 / draft 永不盖章。
# - ``project_artifacts`` — 读面投影（/graph artifacts 块）：成员只认
#   stamped key；live output 唯一归属读物化写者事实
#   （``outputs.workflow_step_id`` ∈ 成员的 ``spec.step_ids``——直接 FK
#   事实，不是推断）。

#: work_key 形态 — ``work:<uuid>``（禁裸 uuid）；run stamp = ``work:<run.id>``。
WORK_KEY_PREFIX = "work:"

#: artifact_key 形态 — ``artifact:<work uuid 尾部>:<slot 序号>``。
ARTIFACT_KEY_PREFIX = "artifact:"

#: artifact_role 词表。``reference`` 本批预留（素材 / 转写稿不盖章——
#: 无 key 节点读作 unknown 直通，永不猜）。
ARTIFACT_ROLES = frozenset({"deliverable", "facet", "companion", "reference"})

#: lineage 真边的端口标记（ADR-097 §5）——edge_type 沿用 text，端口词是唯
#: 一的机器可辨标记。rank 输入（_rank_inputs）/ RunOp 下游闭包
#: （graph_store）/ /graph 默认边载荷三处显式排除：新真边零编排语义，调度
#: 事实源恒为 run 内编译的 step inputs。
LINEAGE_EDGE_PORT = "lineage"

#: 隐藏 modifier 的 facet 表面标记（读面投影附加；LEVER_TOOLS 零改动——
#: 两层门不合并）。
HIDDEN_MODIFIER_SURFACE = "hidden_modifier"


def is_lineage_edge(edge: Any) -> bool:
    """display-only lineage 真边的机器判别（端口标记——edge_type 沿用
    text，类型层不可辨）。"""
    return str(_get(edge, "from_port") or "") == f"out:{LINEAGE_EDGE_PORT}"


def artifact_role_of(spec: Mapping[str, Any] | None) -> str:
    """第二层门的角色谓词：读 stamped ``artifact_role``；无 key 节点 =
    ``unknown``（legacy 读面直通，永不猜）。"""
    spec = spec or {}
    role = str(spec.get("artifact_role") or "")
    return role if role in ARTIFACT_ROLES else "unknown"


def assign_artifact_groups(
    head_kinds: Mapping[str, str],
    parents: Mapping[str, Iterable[str]],
    order_keys: Mapping[str, tuple],
) -> dict[str, tuple[int, str]]:
    """编译期 artifact 分组内核（ADR-097 §1）—— 一次 run stamp 内，每个节
    点家族分到 (slot, role)。

    输入（调用方 graph_fill 从持久化的 step inputs 推导，verify 的输入边已
    排除——verify 折叠进 executor 家族, 它的 inputs 只是质量门接线）：

    - ``head_kinds``: family fill_key → 族头 step kind（角色判定的工具身份）；
    - ``parents``: family fill_key → 上游 family fill_keys（家族 DAG）；
    - ``order_keys``: family fill_key → 确定性排序键（stamp 侧 = 家族最小
      step seq + fill_key——slot 枚举的确定性来源）。

    律：

    - **terminal** = 无非隐藏后代（传递闭包）的非隐藏家族——每个 terminal
      锚一个 group，role = deliverable（组装站/写手/producer 尾站）。
    - 其余非隐藏家族 F 看下游可达 terminal 集 D(F)：恰好 1 个 → 加入为
      facet；多于 1 个 → F 是共享 producer，自锚一个 singleton group 为
      deliverable（fork 兄弟各自独立，互不吞并）。
    - 隐藏 modifier：下游 terminal 唯一则随链加入为 facet；否则归**最近
      非隐藏祖先**的组（它原地改写的就是那位 producer 的产物）——modifier
      永是 facet，即使它握着 render-spec 的最后一笔；无祖先的孤儿自锚成
      无 deliverable 的兜底组（病态, 投影层容忍）。病态多候选一律取
      ``order_keys`` 最小——编译期分配任意确定性选择都诚实，结果随出生凝固。
    """
    keys = sorted(head_kinds)
    hidden = {k for k in keys if head_kinds[k] in LEVER_TOOLS}
    children: dict[str, list[str]] = {k: [] for k in keys}
    for child, ups in parents.items():
        if child not in children:
            continue
        for up in ups:
            if up in children and up != child:
                children[up].append(child)

    def _non_hidden_descendants(start: str) -> set[str]:
        seen: set[str] = set()
        frontier = list(children.get(start, []))
        found: set[str] = set()
        while frontier:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if cur not in hidden:
                found.add(cur)
            frontier.extend(children.get(cur, []))
        return found

    terminals = {
        k for k in keys if k not in hidden and not _non_hidden_descendants(k)
    }

    def _reachable_terminals(start: str) -> set[str]:
        seen: set[str] = set()
        frontier = list(children.get(start, []))
        found: set[str] = set()
        while frontier:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            if cur in terminals:
                found.add(cur)
            frontier.extend(children.get(cur, []))
        return found

    anchor_of: dict[str, str] = {}  # family key → 所属 group 的锚 family key
    # 第一遍：非隐藏家族。terminal 自锚；下游 terminal 唯一则加入；共享
    # producer（下游 terminal > 1）自锚——fork 兄弟各自独立，互不吞并。
    for k in keys:
        if k in hidden:
            continue
        if k in terminals:
            anchor_of[k] = k
            continue
        down = _reachable_terminals(k)
        if len(down) == 1:
            anchor_of[k] = next(iter(down))
        elif len(down) > 1:
            anchor_of[k] = k
        else:  # 不可达（DAG 上不会发生——非隐藏无后代即 terminal），兜底自锚
            anchor_of[k] = k
    # 第二遍：隐藏 modifier。下游 terminal 唯一则随链加入；否则归最近的非
    # 隐藏祖先的组（它原地改写的就是那位 producer 的产物——BFS 层序, 同层
    # 多候选取 ``order_keys`` 最小的确定性兜底）；无祖先 = 孤儿自锚（永是
    # facet，永不是 deliverable）。
    parent_map: dict[str, list[str]] = {k: [u for u in parents.get(k, []) if u in head_kinds] for k in keys}
    for k in keys:
        if k not in hidden:
            continue
        down = _reachable_terminals(k)
        if len(down) == 1:
            anchor_of[k] = next(iter(down))
            continue
        seen: set[str] = {k}
        frontier = list(parent_map.get(k, []))
        home: str | None = None
        while frontier and home is None:
            level, frontier = frontier, []
            non_hidden = [u for u in level if u not in hidden and u not in seen]
            seen.update(level)
            if non_hidden:
                home = min(non_hidden, key=lambda u: order_keys.get(u, (0, u)))
                break
            for u in level:
                frontier.extend(parent_map.get(u, []))
        anchor_of[k] = anchor_of.get(home, k) if home is not None else k
    anchors = sorted(
        set(anchor_of.values()), key=lambda a: order_keys.get(a, (0, a))
    )
    slot_of = {a: i + 1 for i, a in enumerate(anchors)}
    # deliverable = 自锚的非隐藏家族（terminal 站 / 共享 producer）；孤儿
    # modifier 的自锚只是归组兜底, 永不是 deliverable。
    return {
        k: (
            slot_of[anchor_of[k]],
            "deliverable" if anchor_of[k] == k and k not in hidden else "facet",
        )
        for k in keys
    }


def artifact_fields_for_birth(
    spec: Mapping[str, Any] | None,
    *,
    draft: bool,
    artifact_key: str | None,
    work_key: str | None,
    role: str | None,
    name: str | None,
) -> dict[str, str]:
    """stamp 甄别真值表（ADR-097 §1 降生四字段的唯一写口律）：

    - ``draft``（K5 预览）→ ``{}``——草图永不盖章；Start 的活填在原地补写
      （same compile → same fill_key → same node，draft-born 无 run_id）。
    - spec 已携 ``artifact_key`` → ``{}``（key 随出生凝固，re-fill 永不改派）。
    - spec 无 key 但携 ``run_id`` → ``{}``（legacy run-born 行永不补猜——
      读面 unknown 直通）。
    - 其余（newborn / draft-born 首次活填）→ 写入四字段；``name`` 空则省略
      （null 读容忍的诚实标签回退，ADR-058 二源律）。
    """
    if draft or not artifact_key or not work_key or role not in ARTIFACT_ROLES:
        return {}
    spec = spec or {}
    if spec.get("artifact_key") or spec.get("run_id"):
        return {}
    fields = {
        "work_key": work_key,
        "artifact_key": artifact_key,
        "artifact_role": role,
    }
    if name:
        fields["artifact_name"] = name
    return fields


def aggregate_artifact_activity(states: Iterable[str]) -> str:
    """artifact 的单一 activity owner 的聚合律（ADR-097 §4——成员节点状态的
    确定性 rollup；失败恒可见，然后活跃，然后终态诚实）。"""
    states = [str(s) for s in states]
    if not states:
        return "queued"
    if any(s == "failed" for s in states):
        return "failed"
    if any(s == "running" for s in states):
        return "running"
    if any(s == "stale" for s in states):
        return "stale"
    if any(s == "queued" for s in states):
        return "queued"
    if all(s == "skipped" for s in states):
        return "skipped"
    return "done"


def project_artifacts(
    nodes: Iterable[Any],
    outputs_by_id: Mapping[str, Any],
    *,
    visible_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """读面投影（ADR-097 §3——/graph 的 artifacts 块装配内核，纯函数）。

    - 成员**只认** stamped ``artifact_key`` / ``artifact_role``；无 key 节点
      永不进任何块（unknown/legacy 直通）——rank / 边序 / created_at /
      共享 output / fill_key 相似性的任何扰动都不改变成员（ADR-097 §10）。
    - live output 唯一归属（一 live output 至多一张交付物卡）：output 的
      物化写者 ``workflow_step_id`` 落在哪个 keyed 节点的 ``step_ids`` 里就
      归哪个 artifact；写者未知（legacy / step_ids 已被 re-fill 刷新）则归
      deliverable 站（兜底诚实——output_ids 本来就是该节点的版本血缘）。
    - archived version 留历史归属（ADR-091 语义不动）。
    """
    node_list = list(nodes)
    keyed = [
        n
        for n in node_list
        if str(_spec_of(n).get("artifact_key") or "")
        and artifact_role_of(_spec_of(n)) != "unknown"
    ]
    # 写者 step → artifact_key 的全图索引（跨组归属判定的唯一事实源）。
    step_owner: dict[str, str] = {}
    for n in keyed:
        spec = _spec_of(n)
        for sid in spec.get("step_ids") or []:
            step_owner[str(sid)] = str(spec["artifact_key"])
    groups: dict[str, list[Any]] = {}
    for n in keyed:
        groups.setdefault(str(_spec_of(n)["artifact_key"]), []).append(n)
    visible = {str(v) for v in visible_ids}

    blocks: list[dict[str, Any]] = []
    for key, members in groups.items():
        by_role: dict[str, list[Any]] = {"deliverable": [], "facet": [], "companion": []}
        for m in members:
            role = artifact_role_of(_spec_of(m))
            if role in by_role:
                by_role[role].append(m)
        deliverable = (
            sorted(by_role["deliverable"], key=lambda n: str(_get(n, "id"))) or [None]
        )[0]
        lineage_ids = (
            list(_spec_of(deliverable).get("output_ids") or [])
            if deliverable is not None
            else [
                oid
                for m in members
                for oid in (_spec_of(m).get("output_ids") or [])
            ]
        )
        owned_visible: list[str] = []
        archived: list[str] = []
        for oid in lineage_ids:
            output = outputs_by_id.get(str(oid))
            if output is None:
                continue  # deleted rows have their own lifecycle
            writer = str(_get(output, "workflow_step_id") or "")
            owner = step_owner.get(writer)
            if owner is not None and owner != key:
                continue  # 另一 artifact 的写者最后一笔——per-output 不吞并
            if str(oid) in visible:
                owned_visible.append(str(oid))
            else:
                archived.append(str(oid))
        states = [str(_get(m, "state") or "") for m in members]
        failed_ids = [
            str(_get(m, "id")) for m in members if str(_get(m, "state") or "") == "failed"
        ]
        name = next(
            (
                str(_spec_of(m)["artifact_name"])
                for m in members
                if _spec_of(m).get("artifact_name")
            ),
            None,
        )
        facets = [
            {
                "node_id": str(_get(f, "id")),
                "tool": str(_spec_of(f).get("tool") or "") or None,
                "label": str(_spec_of(f).get("summary") or "") or None,
                "state": str(_get(f, "state") or ""),
                "surface": (
                    HIDDEN_MODIFIER_SURFACE
                    if str(_spec_of(f).get("tool") or "") in LEVER_TOOLS
                    else None
                ),
            }
            for f in sorted(by_role["facet"], key=lambda n: str(_get(n, "id")))
        ]
        blocks.append(
            {
                "artifact_key": key,
                "work_key": str(_spec_of(members[0]).get("work_key") or ""),
                "name": name,
                "deliverable_node_id": (
                    str(_get(deliverable, "id")) if deliverable is not None else None
                ),
                "facet_node_ids": [f["node_id"] for f in facets],
                "facets": facets,
                "companion_node_ids": [
                    str(_get(c, "id"))
                    for c in sorted(by_role["companion"], key=lambda n: str(_get(n, "id")))
                ],
                "current_output_id": owned_visible[-1] if owned_visible else None,
                "archived_output_ids": archived,
                "activity": {
                    "state": aggregate_artifact_activity(states),
                    "failed_node_ids": failed_ids,
                },
            }
        )

    def _slot(block: dict[str, Any]) -> tuple[int, str]:
        try:
            return (int(str(block["artifact_key"]).rsplit(":", 1)[1]), block["artifact_key"])
        except ValueError:
            return (1 << 30, block["artifact_key"])

    return sorted(blocks, key=_slot)


__all__ = [
    "ARTIFACT_KEY_PREFIX",
    "ARTIFACT_ROLES",
    "HIDDEN_MODIFIER_SURFACE",
    "HIDDEN_ROLES",
    "LEGACY_VISIBLE_TYPES",
    "LEVER_TOOLS",
    "LINEAGE_EDGE_PORT",
    "MEDIA_TYPES",
    "PITCH",
    "RANK_EDGE_TYPES",
    "TRANSITIONAL_TYPES",
    "WORK_KEY_PREFIX",
    "aggregate_artifact_activity",
    "artifact_fields_for_birth",
    "artifact_role_of",
    "assign_artifact_groups",
    "display_ranks",
    "is_lineage_edge",
    "is_product_node",
    "is_rank_edge",
    "product_ranks",
    "project_artifacts",
    "project_x",
    "sibling_order",
    "topological_order",
    "validate_product_graph",
]
