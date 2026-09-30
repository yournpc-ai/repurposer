"""Pure tests for the Product Artifact Ontology (ADR-097 Phase 1, batch C-1).

No DB / no LLM / no HTTP: the three kernels are pure —

- ``assign_artifact_groups`` — the compile-time grouping law (stamp core's
  seat): terminal deliverables / facets / shared-producer forks / hidden
  modifiers, deterministic slot enumeration.
- ``artifact_fields_for_birth`` — the stamp discrimination truth table:
  birth write / key frozen / legacy never backfilled / draft never stamped.
- ``project_artifacts`` — the read-face projection: membership reads ONLY
  the stamped keys (ADR-097 §2 first load-bearing clause); live-output
  unique ownership reads the materialized writer FK.

Plus the ADR-097 §10 mandatory negatives: rank/edge-order/created_at/
shared-output/fill_key-similarity perturbations never change membership;
unkeyed nodes are never guessed in; lineage/display-only edges never feed
rank nor the run closure (edit transcript text → downstream captions stay
intact); one live output lands on at most one deliverable card (fork
siblings never merge).
"""

from types import SimpleNamespace
from uuid import uuid4

from app.pipeline.graph_store import executable_children_of
from app.pipeline.product_graph import (
    HIDDEN_MODIFIER_SURFACE,
    aggregate_artifact_activity,
    artifact_fields_for_birth,
    artifact_role_of,
    assign_artifact_groups,
    is_lineage_edge,
    product_ranks,
    project_artifacts,
    validate_product_graph,
)


# ---- fixtures ------------------------------------------------------------


def _node(node_id, *, spec=None, state="done", type_="video"):
    return SimpleNamespace(
        id=node_id, spec=spec or {}, state=state, type=type_, layout={}
    )


def _output(oid, *, workflow_step_id=None):
    return SimpleNamespace(id=oid, workflow_step_id=workflow_step_id)


def _edge(from_node, to_node, edge_type="text", from_port=None):
    return SimpleNamespace(
        from_node=from_node,
        to_node=to_node,
        edge_type=edge_type,
        from_port=from_port or f"out:{edge_type}",
    )


# ---- the compile-time grouping kernel -------------------------------------


class TestAssignArtifactGroups:
    def test_single_translate_chain(self) -> None:
        """cut → translate → reframe: the asm is the deliverable; producer
        and hidden modifier are facets of the SAME group."""
        heads = {
            "select_clips#clip#0": "select_clips",
            "translate_clip#fr#False#False": "translate_clip",
            "reframe_clip": "reframe_clip",
        }
        parents = {
            "select_clips#clip#0": [],
            "translate_clip#fr#False#False": ["select_clips#clip#0"],
            "reframe_clip": ["translate_clip#fr#False#False"],
        }
        order = {k: (i, k) for i, k in enumerate(heads)}
        out = assign_artifact_groups(heads, parents, order)
        assert out["translate_clip#fr#False#False"] == (1, "deliverable")
        assert out["select_clips#clip#0"] == (1, "facet")
        assert out["reframe_clip"] == (1, "facet")

    def test_producer_only_chain_is_its_own_deliverable(self) -> None:
        heads = {"select_clips#clip#0": "select_clips"}
        out = assign_artifact_groups(heads, {"select_clips#clip#0": []}, {"select_clips#clip#0": (0, "select_clips#clip#0")})
        assert out == {"select_clips#clip#0": (1, "deliverable")}

    def test_terminal_modifier_joins_its_producer(self) -> None:
        """cut → reframe (chain ends in a hidden modifier): the producer is
        the last NON-HIDDEN render-spec writer → deliverable; the modifier
        rides it as facet."""
        heads = {"select_clips#clip#0": "select_clips", "reframe_clip": "reframe_clip"}
        parents = {"select_clips#clip#0": [], "reframe_clip": ["select_clips#clip#0"]}
        order = {k: (i, k) for i, k in enumerate(heads)}
        out = assign_artifact_groups(heads, parents, order)
        assert out["select_clips#clip#0"] == (1, "deliverable")
        assert out["reframe_clip"] == (1, "facet")

    def test_fork_siblings_never_merge(self) -> None:
        """cut → {translate-fr, translate-de}: three groups — each sibling
        its own deliverable, the shared producer self-anchored (ADR-097 §10
        ④: fork 兄弟各自独立, 互不吞并)."""
        heads = {
            "select_clips#clip#0": "select_clips",
            "translate_clip#fr#False#True": "translate_clip",
            "translate_clip#de#False#True": "translate_clip",
        }
        parents = {
            "select_clips#clip#0": [],
            "translate_clip#fr#False#True": ["select_clips#clip#0"],
            "translate_clip#de#False#True": ["select_clips#clip#0"],
        }
        order = {k: (i, k) for i, k in enumerate(heads)}
        out = assign_artifact_groups(heads, parents, order)
        assert out["select_clips#clip#0"] == (1, "deliverable")
        assert out["translate_clip#fr#False#True"] == (2, "deliverable")
        assert out["translate_clip#de#False#True"] == (3, "deliverable")

    def test_mid_chain_modifier_joins_the_shared_producer(self) -> None:
        """cut → reframe → {fr, de}: the mid-chain modifier's nearest
        non-hidden ancestor is the shared producer — it rides THAT group,
        never one of the fork siblings'."""
        heads = {
            "select_clips#clip#0": "select_clips",
            "reframe_clip": "reframe_clip",
            "translate_clip#fr#False#True": "translate_clip",
            "translate_clip#de#False#True": "translate_clip",
        }
        parents = {
            "select_clips#clip#0": [],
            "reframe_clip": ["select_clips#clip#0"],
            "translate_clip#fr#False#True": ["reframe_clip"],
            "translate_clip#de#False#True": ["reframe_clip"],
        }
        order = {k: (i, k) for i, k in enumerate(heads)}
        out = assign_artifact_groups(heads, parents, order)
        assert out["reframe_clip"] == (1, "facet")
        assert out["select_clips#clip#0"] == (1, "deliverable")
        assert out["translate_clip#fr#False#True"] == (2, "deliverable")
        assert out["translate_clip#de#False#True"] == (3, "deliverable")

    def test_dub_tail_is_the_deliverable(self) -> None:
        """cut → translate → dub: the LAST non-hidden render-spec writer
        owns the card; every upstream station is a facet."""
        heads = {
            "select_clips#clip#0": "select_clips",
            "translate_clip#fr#False#False": "translate_clip",
            "dub_clip#fr#False#False": "dub_clip",
        }
        parents = {
            "select_clips#clip#0": [],
            "translate_clip#fr#False#False": ["select_clips#clip#0"],
            "dub_clip#fr#False#False": ["translate_clip#fr#False#False"],
        }
        order = {k: (i, k) for i, k in enumerate(heads)}
        out = assign_artifact_groups(heads, parents, order)
        assert out["dub_clip#fr#False#False"] == (1, "deliverable")
        assert out["translate_clip#fr#False#False"] == (1, "facet")
        assert out["select_clips#clip#0"] == (1, "facet")

    def test_writer_singleton_and_independent_chains(self) -> None:
        """A clip chain and a writer family share no edge: two groups,
        slots follow the deterministic order keys."""
        heads = {
            "select_clips#clip#0": "select_clips",
            "write_post#post#0": "write_post",
        }
        parents = {"select_clips#clip#0": [], "write_post#post#0": []}
        order = {"select_clips#clip#0": (3, "select_clips#clip#0"), "write_post#post#0": (1, "write_post#post#0")}
        out = assign_artifact_groups(heads, parents, order)
        assert out["write_post#post#0"] == (1, "deliverable")
        assert out["select_clips#clip#0"] == (2, "deliverable")

    def test_input_permutation_never_changes_the_assignment(self) -> None:
        """Determinism (ADR-097 §10 ①): dict/order perturbation of the
        INPUTS leaves the assignment byte-identical."""
        heads = {
            "select_clips#clip#0": "select_clips",
            "translate_clip#fr#False#False": "translate_clip",
            "reframe_clip": "reframe_clip",
        }
        parents = {
            "translate_clip#fr#False#False": ["select_clips#clip#0"],
            "reframe_clip": ["translate_clip#fr#False#False"],
            "select_clips#clip#0": [],
        }
        order = {k: (i, k) for i, k in enumerate(heads)}
        baseline = assign_artifact_groups(heads, parents, order)
        for _ in range(5):
            permuted_heads = dict(reversed(list(heads.items())))
            permuted_parents = {k: list(reversed(v)) for k, v in reversed(list(parents.items()))}
            assert assign_artifact_groups(permuted_heads, permuted_parents, order) == baseline


# ---- the stamp discrimination truth table ----------------------------------


class TestArtifactFieldsForBirth:
    KEY = "artifact:00000000-0000-0000-0000-0000000000aa:1"
    WORK = "work:00000000-0000-0000-0000-0000000000aa"

    def _fields(self, spec, **kw):
        args = {
            "draft": False,
            "artifact_key": self.KEY,
            "work_key": self.WORK,
            "role": "deliverable",
            "name": "My clip",
        }
        args.update(kw)
        return artifact_fields_for_birth(spec, **args)

    def test_newborn_gets_the_four_fields(self) -> None:
        out = self._fields({})
        assert out == {
            "work_key": self.WORK,
            "artifact_key": self.KEY,
            "artifact_role": "deliverable",
            "artifact_name": "My clip",
        }

    def test_draft_never_stamps(self) -> None:
        assert self._fields({}, draft=True) == {}

    def test_frozen_key_never_reassigned(self) -> None:
        """key 随出生凝固 — a re-fill keeps the birth key even when the new
        stamp computes one."""
        assert self._fields({"artifact_key": "artifact:other:9", "run_id": "r"}) == {}
        # 冻结只看已有 key, 与 run_id 无关
        assert self._fields({"artifact_key": "artifact:other:9"}) == {}

    def test_legacy_run_born_never_backfilled(self) -> None:
        """无 key + 有 run_id = legacy run-born 行 — 永不补猜 (unknown 直通)."""
        assert self._fields({"run_id": "old-run", "tool": "select_clips"}) == {}

    def test_draft_born_first_live_fill_assigns(self) -> None:
        """无 key + 无 run_id = draft-born (K5 预览) — Start 的活填在原地
        补写 (same fill_key → same node)."""
        out = self._fields({"fill_key": "select_clips#clip#0", "state": "draft"})
        assert out["artifact_key"] == self.KEY

    def test_empty_name_is_omitted(self) -> None:
        """ADR-058 二源律: name 缺省则省略键 (null 读容忍的诚实标签回退),
        永不写空串占位."""
        out = self._fields({}, name=None)
        assert "artifact_name" not in out
        out = self._fields({}, name="")
        assert "artifact_name" not in out

    def test_invalid_role_refuses_the_write(self) -> None:
        assert self._fields({}, role="cluster") == {}
        assert self._fields({}, role=None) == {}

    def test_missing_identity_refuses_the_write(self) -> None:
        assert self._fields({}, artifact_key=None) == {}
        assert self._fields({}, work_key=None) == {}


class TestArtifactRoleOf:
    def test_canonical_roles_pass_through(self) -> None:
        for role in ("deliverable", "facet", "companion", "reference"):
            assert artifact_role_of({"artifact_role": role}) == role

    def test_keyless_is_unknown_never_guessed(self) -> None:
        assert artifact_role_of({}) == "unknown"
        assert artifact_role_of(None) == "unknown"
        assert artifact_role_of({"artifact_role": "producer"}) == "unknown"


# ---- lineage edges: rank exclusion + run-closure exclusion -----------------


class TestLineageEdgeExclusion:
    def test_port_marker_is_the_only_discriminator(self) -> None:
        assert is_lineage_edge(_edge("a", "b", from_port="out:lineage")) is True
        assert is_lineage_edge(_edge("a", "b", from_port="out:text")) is False
        assert is_lineage_edge(_edge("a", "b", "video")) is False
        # edge_type 沿用 text — 类型层不可辨, 只有端口词说话
        assert is_lineage_edge(_edge("a", "b", "text", from_port="out:lineage")) is True

    def test_lineage_never_feeds_rank(self) -> None:
        """ADR-086 的预授权激活: lineage 边不入 rank——同一图加/减一条
        lineage 真边, rank 帧逐字节不变 (画布零变化)."""
        asset, transcript, deliverable = uuid4(), uuid4(), uuid4()
        nodes = [
            _node(asset, type_="asset"),
            _node(transcript, type_="document"),
            _node(deliverable, type_="video"),
        ]
        flow = [_edge(asset, deliverable, "video")]
        without = product_ranks(nodes, flow, gated=False)
        with_lineage = product_ranks(
            nodes,
            [*flow, _edge(transcript, deliverable, "text", from_port="out:lineage")],
            gated=False,
        )
        assert without == with_lineage

    def test_run_closure_never_walks_lineage(self) -> None:
        """ADR-097 §10 ③ 的纯函数闸: 对转写稿的 run 闭包沿血缘边永远不
        到达下游字幕节点 (改 edited_text → 下游产物不失效); 普通物料流边
        照常走."""
        transcript, deliverable = uuid4(), uuid4()
        edges = [
            _edge(transcript, deliverable, "text", from_port="out:lineage"),
        ]
        assert executable_children_of(edges, transcript) == []
        flow_edges = [
            _edge(transcript, deliverable, "text", from_port="out:lineage"),
            _edge(transcript, deliverable, "text"),
        ]
        assert executable_children_of(flow_edges, transcript) == [deliverable]

    def test_direction_invariant_exempts_lineage(self) -> None:
        """producer-deliverable 链 (无 translate): 对照——物料流直边喂 rank
        (deliverable 被推到 T 之后一列); 血缘边永不喂 rank (两者并列 asset
        下游), 横跨同列也不是 violation (display-only, 永不是 product
        edge——方向不变量豁免, layout.ts 同律两镜像)."""
        asset, transcript, cut = uuid4(), uuid4(), uuid4()
        nodes = [
            _node(asset, type_="asset"),
            _node(transcript, type_="document"),
            _node(cut, type_="video"),
        ]
        flow = [_edge(asset, transcript, "text"), _edge(asset, cut, "video")]
        with_flow = product_ranks(nodes, [*flow, _edge(transcript, cut, "text")])
        assert with_flow[str(cut)] == with_flow[str(transcript)] + 1
        lineage_edges = [
            *flow,
            _edge(transcript, cut, "text", from_port="out:lineage"),
        ]
        with_lineage = product_ranks(nodes, lineage_edges)
        assert with_lineage == product_ranks(nodes, flow)
        assert with_lineage[str(cut)] == with_lineage[str(transcript)]
        assert validate_product_graph(nodes, lineage_edges) == []


# ---- the activity rollup ----------------------------------------------------


class TestAggregateArtifactActivity:
    def test_failure_always_visible(self) -> None:
        assert aggregate_artifact_activity(["done", "failed", "running"]) == "failed"

    def test_running_beats_queued_and_done(self) -> None:
        assert aggregate_artifact_activity(["done", "running", "queued"]) == "running"

    def test_stale_between_running_and_queued(self) -> None:
        assert aggregate_artifact_activity(["done", "stale", "queued"]) == "stale"

    def test_terminal_honesty(self) -> None:
        assert aggregate_artifact_activity(["done", "skipped"]) == "done"
        assert aggregate_artifact_activity(["skipped", "skipped"]) == "skipped"

    def test_empty_is_queued(self) -> None:
        assert aggregate_artifact_activity([]) == "queued"


# ---- the read-face projection -----------------------------------------------


def _keyed(node_id, key, role, *, step_ids=(), output_ids=(), state="done", tool=None, name=None, type_="video"):
    spec = {
        "artifact_key": key,
        "artifact_role": role,
        "work_key": "work:w1",
        "step_ids": [str(s) for s in step_ids],
        "output_ids": [str(o) for o in output_ids],
    }
    if tool:
        spec["tool"] = tool
    if name:
        spec["artifact_name"] = name
    return _node(node_id, spec=spec, state=state, type_=type_)


class TestProjectArtifacts:
    def test_one_deliverable_one_card(self) -> None:
        key = "artifact:w1:1"
        d, f, c = uuid4(), uuid4(), uuid4()
        o1 = uuid4()
        nodes = [
            _keyed(d, key, "deliverable", step_ids=("s1",), output_ids=(o1,), name="金句短片"),
            _keyed(f, key, "facet", state="running", tool="reframe_clip"),
            _keyed(c, key, "companion", type_="table"),
        ]
        blocks = project_artifacts(nodes, {str(o1): _output(o1, workflow_step_id="s1")}, visible_ids={str(o1)})
        assert len(blocks) == 1
        block = blocks[0]
        assert block["artifact_key"] == key
        assert block["work_key"] == "work:w1"
        assert block["name"] == "金句短片"
        assert block["deliverable_node_id"] == str(d)
        assert block["facet_node_ids"] == [str(f)]
        assert block["companion_node_ids"] == [str(c)]
        assert block["current_output_id"] == str(o1)
        assert block["archived_output_ids"] == []
        # facet 摘要: 程序/状态可查 + hidden_modifier 表面标记
        assert block["facets"] == [
            {
                "node_id": str(f),
                "tool": "reframe_clip",
                "label": None,
                "state": "running",
                "surface": HIDDEN_MODIFIER_SURFACE,
            }
        ]
        assert block["activity"]["state"] == "running"

    def test_membership_perturbation_invariance(self) -> None:
        """ADR-097 §10 ①: 改节点序 / 输出序 / created_at / rank 无关属性
        → 成员与归属逐字节不变 (成员只认 stamped key)."""
        key = "artifact:w1:1"
        d, f = uuid4(), uuid4()
        o1, o2 = uuid4(), uuid4()
        nodes = [
            _keyed(d, key, "deliverable", step_ids=("s1",), output_ids=(o1, o2)),
            _keyed(f, key, "facet", tool="add_music"),
        ]
        outputs = {str(o1): _output(o1, workflow_step_id="s1"), str(o2): _output(o2, workflow_step_id="s1")}
        baseline = project_artifacts(nodes, outputs, visible_ids={str(o1), str(o2)})
        perturbed_nodes = [
            _keyed(f, key, "facet", tool="add_music"),
            _keyed(d, key, "deliverable", step_ids=("s1",), output_ids=(o2, o1)),
        ]
        perturbed = project_artifacts(perturbed_nodes, dict(reversed(list(outputs.items()))), visible_ids={str(o2), str(o1)})
        assert [b["artifact_key"] for b in perturbed] == [b["artifact_key"] for b in baseline]
        assert perturbed[0]["deliverable_node_id"] == baseline[0]["deliverable_node_id"]
        assert perturbed[0]["facet_node_ids"] == baseline[0]["facet_node_ids"]
        # current = output_ids 顺序里最后一张 live (append = 落地序, 写事实)
        assert perturbed[0]["current_output_id"] == str(o1)

    def test_unkeyed_nodes_never_guessed_in(self) -> None:
        """ADR-097 §10 ②: 共享 output_ids + fill_key 相似 + 同 created_at
        的 legacy 节点永不进块 (unknown/legacy 直通)."""
        key = "artifact:w1:1"
        d, legacy = uuid4(), uuid4()
        o1 = uuid4()
        legacy_spec = {
            "fill_key": "select_clips#clip#0",  # 与 keyed 成员形似
            "output_ids": [str(o1)],  # 共享同一 output
            "tool": "select_clips",
            "run_id": "old-run",
        }
        nodes = [
            _keyed(d, key, "deliverable", step_ids=("s1",), output_ids=(o1,)),
            _node(legacy, spec=legacy_spec, type_="video"),
        ]
        blocks = project_artifacts(nodes, {str(o1): _output(o1, workflow_step_id="s1")}, visible_ids={str(o1)})
        assert len(blocks) == 1
        assert str(legacy) not in blocks[0]["facet_node_ids"]
        assert str(legacy) != blocks[0]["deliverable_node_id"]

    def test_live_output_unique_ownership_across_groups(self) -> None:
        """ADR-097 §10 ④: 改写同一行的两个组 — 物化写者
        (workflow_step_id) 落在 B 的 step_ids → 只 B 认领, A 不吞并."""
        key_a, key_b = "artifact:w1:1", "artifact:w2:1"
        da, db_ = uuid4(), uuid4()
        shared = uuid4()
        nodes = [
            _keyed(da, key_a, "deliverable", step_ids=("s-cut",), output_ids=(shared,)),
            _keyed(db_, key_b, "deliverable", step_ids=("s-translate",), output_ids=(shared,)),
        ]
        outputs = {str(shared): _output(shared, workflow_step_id="s-translate")}
        blocks = project_artifacts(nodes, outputs, visible_ids={str(shared)})
        by_key = {b["artifact_key"]: b for b in blocks}
        assert by_key["artifact:w2:1"]["current_output_id"] == str(shared)
        assert by_key["artifact:w1:1"]["current_output_id"] is None

    def test_unknown_writer_falls_back_to_the_deliverable(self) -> None:
        """写者不可考 (legacy / step_ids 已被 re-fill 刷新) → deliverable
        站兜底认领 (output_ids 本来就是它的版本血缘)."""
        key = "artifact:w1:1"
        d = uuid4()
        o1 = uuid4()
        nodes = [_keyed(d, key, "deliverable", step_ids=("s-new",), output_ids=(o1,))]
        blocks = project_artifacts(nodes, {str(o1): _output(o1, workflow_step_id="s-old-gone")}, visible_ids={str(o1)})
        assert blocks[0]["current_output_id"] == str(o1)

    def test_archived_versions_keep_historical_ownership(self) -> None:
        """ADR-091: archived 行不进 visible → archived_output_ids 留历史
        归属; 删除行 (outputs_by_id 缺席) 静默跳过."""
        key = "artifact:w1:1"
        d = uuid4()
        live, archived, deleted = uuid4(), uuid4(), uuid4()
        nodes = [
            _keyed(d, key, "deliverable", step_ids=("s1",), output_ids=(live, archived, deleted)),
        ]
        outputs = {
            str(live): _output(live, workflow_step_id="s1"),
            str(archived): _output(archived, workflow_step_id="s1"),
        }
        blocks = project_artifacts(nodes, outputs, visible_ids={str(live)})
        assert blocks[0]["current_output_id"] == str(live)
        assert blocks[0]["archived_output_ids"] == [str(archived)]

    def test_activity_failure_carries_member_location(self) -> None:
        key = "artifact:w1:1"
        d, f = uuid4(), uuid4()
        nodes = [
            _keyed(d, key, "deliverable", state="done"),
            _keyed(f, key, "facet", state="failed", tool="add_music"),
        ]
        blocks = project_artifacts(nodes, {}, visible_ids=set())
        assert blocks[0]["activity"] == {"state": "failed", "failed_node_ids": [str(f)]}

    def test_missing_name_reads_none(self) -> None:
        key = "artifact:w1:1"
        d = uuid4()
        blocks = project_artifacts([_keyed(d, key, "deliverable")], {}, visible_ids=set())
        assert blocks[0]["name"] is None

    def test_blocks_sort_by_slot(self) -> None:
        d2, d1 = uuid4(), uuid4()
        nodes = [
            _keyed(d2, "artifact:w1:2", "deliverable"),
            _keyed(d1, "artifact:w1:1", "deliverable"),
        ]
        blocks = project_artifacts(nodes, {}, visible_ids=set())
        assert [b["artifact_key"] for b in blocks] == ["artifact:w1:1", "artifact:w1:2"]
