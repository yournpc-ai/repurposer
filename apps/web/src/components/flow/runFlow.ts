import type { TFunction } from "i18next"

import { toAbsoluteUrl } from "@/lib/api"
import type { Output, PlaceholderRow, WorkflowStep } from "@/lib/types"

import { ASSET_TOOLBAR_PX, PLACEHOLDER_TEXT_LINES, productNodeSize, textProductNodeSize, VIDEO_ASSET_NODE_SIZE } from "./layout"
import type { FlowEdge, FlowNode, FlowNodeStatus } from "./types"

/** RunFlowGraph adapter (ADR-036/041, 全栈同名 with the server graph): a
 * run's real topology → the FlowView contract, consumed by the results
 * canvas. Composition: assets left, the 任务书 glass text node + 过程脊
 * middle, product outputs right.
 *
 * 渲染单元 (D6 修订 2026-08-12; 名词节点收窄 2026-08-19): the canvas renders
 * NOUN nodes only — 素材 / 文本 (任务书, the "plan" canvas_key) / 产物.
 * Process verbs (select_clips / translate / dub / add_music) never get a
 * card: each is an ATTRIBUTE of its product, so their steps fold into the
 * 过程脊 (intervention = click the product, or the expanded spine's step
 * pill via @workflow_step — the translate_clip 2026-08-15 precedent
 * generalized). Steps sharing a class-declared `canvas_key` still merge
 * into ONE node (the mechanism is untouched — the grants narrowed).
 * `canvas_hidden` covers TWO invisible classes: render steps (their state
 * projects onto the product card in place) and the prelude (preprocess /
 * persona_bootstrap — 二轮 R1: plan's upstream must not share the spine
 * with plan's downstream, or the folded pair forms a 2-cycle that sinks
 * the 任务书 into the product column; the 素材 feed walks DOWNSTREAM to
 * the first rendered descendant instead). All of it is VIEW behavior over
 * the full step rows.
 *
 * Edge discipline (prohibitions #9 / #11): dependency edges come from the
 * server's edge table (step `inputs`) plus the structural fact every recipe
 * adapter already relies on — source assets feed the root steps; lineage
 * edges come from server-resolved fields only (output.workflow_step_id).
 * Endpoint rewiring (step → its artifact card / the spine; hidden step →
 * its first rendered ancestor via `inputs`) is mechanical projection over
 * that same real data — the frontend never invents derivation. */
export interface RunFlowAsset {
  id: string
  type: string
  title: string | null
  file_url: string | null
  /** Browser-playable URL resolved through the storage seam (AssetResponse's
   * computed field) — the media src for image thumbs and inline video. */
  stream_url?: string | null
  /** Lightbox meta (AssetResponse passthrough): media duration + upload
   * time ride the info column and the chip grid. */
  duration_seconds?: number | null
  created_at?: string
}

/** User-facing product types (the /results payload is already filtered
 * server-side; internal artifact types like material_understanding never
 * become canvas nodes). */
const PRODUCT_TYPE_LABEL_KEY: Record<string, string> = {
  clip: "results.tabs.clips",
  post: "results.tabs.post",
  quotes: "results.tabs.quotes",
  quote_frame: "results.tabs.quoteFrame",
  carousel: "results.tabs.carousel",
  article: "results.tabs.article",
}

/** Step status → FlowView status. A parked interrupt (`waiting`) reads as
 * not-yet-done on the canvas — the ask lives in the chat dock, not the
 * graph (D2: progress never enters the graph). */
function stepNodeStatus(status: string): FlowNodeStatus {
  switch (status) {
    case "running":
      return "running"
    case "done":
      return "done"
    case "failed":
      return "failed"
    case "skipped":
      return "skipped"
    default:
      return "pending"
  }
}

/** Aggregate status over a canvas node's member steps: failure is always
 * visible (in place — the card itself turns red), then liveness. */
function aggregateStatus(members: WorkflowStep[]): FlowNodeStatus {
  const statuses = members.map((s) => stepNodeStatus(s.status))
  if (statuses.some((s) => s === "failed")) return "failed"
  if (statuses.some((s) => s === "running")) return "running"
  if (statuses.every((s) => s === "done" || s === "skipped")) return "done"
  return "pending"
}

/** The 过程脊 group node's reserved id (D6) — every folded step's edges
 * rewire to it; the surface toggles expansion off this id. */
export const SPINE_NODE_ID = "spine"

export function runFlowGraph(
  input: {
    assets: RunFlowAsset[]
    steps: WorkflowStep[]
    outputs: Output[]
    /** The run's prompt — displayed in every product card's interaction
     * area (spec on the body; changes happen in chat). */
    prompt?: string | null
    /** The live run's placeholder roster (ADR-051 B — server-projected from
     * the compiled steps; empty for terminal/absent runs): each row's slots
     * render as quiet placeholder cards born at their final size/position;
     * a landed output from the same step fills its slot in place. */
    placeholders?: PlaceholderRow[]
    /** The node carrying the results tour's data-tour anchors (first ready
     * product, chosen by the surface). */
    tourOutputId?: string | null
    /** 过程脊 state (D6): collapsed (default) folds the keyless plumbing
     * steps into one group node; expanded renders them as step pills.
     * Artifact cards stay cards either way — they are render units, not
     * steps. */
    spineExpanded?: boolean
  },
  t: TFunction
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const nodes: FlowNode[] = []
  const rawEdges: FlowEdge[] = []
  const { assets, steps, outputs, prompt, placeholders, tourOutputId, spineExpanded = false } = input

  const stepIds = new Set(steps.map((s) => s.id))
  const byId = new Map(steps.map((s) => [s.id, s]))

  assets.forEach((asset, i) => {
    const typeLabel = t(`generationOverlay.assetTypes.${asset.type}`, {
      defaultValue: asset.type,
    })
    // file_url is a bare storage key on new rows — the browser-playable URL
    // is the computed stream_url (legacy rows carry a path/URL in file_url,
    // which toAbsoluteUrl passes through).
    const mediaUrl = toAbsoluteUrl(asset.stream_url ?? asset.file_url)
    nodes.push({
      id: `asset:${asset.id}`,
      kind: "asset",
      // Caption = type icon + type name, right slot empty (2026-08-17 走查
      // 拍板): the filename moves to the toolbar's info slot — carried as
      // `detail` (data only; the caption never renders it, the lightbox's
      // info chips do).
      label: typeLabel,
      detail: asset.title ?? undefined,
      asset: {
        id: asset.id,
        type: asset.type,
        title: asset.title,
        file_url: asset.file_url,
        stream_url: asset.stream_url,
        duration_seconds: asset.duration_seconds,
      },
      thumbUrl: asset.type === "image" ? mediaUrl : null,
      // The source video IS a video node — it plays inline (muted loop),
      // sized landscape so the frame is watchable.
      videoUrl: asset.type === "video" ? mediaUrl : null,
      // Every asset node carries its toolbar on this surface — the reserved
      // band is part of the size budget.
      size:
        asset.type === "video"
          ? VIDEO_ASSET_NODE_SIZE
          : { width: 128, height: 216 + ASSET_TOOLBAR_PX },
      order: i,
    })
  })

  // ── 渲染单元分组 (D6 修订) ────────────────────────────────────────────
  // canvas_hidden → never a node; canvas_key → merge into one artifact card
  // per key; the rest → the 过程脊.
  const artifactGroups = new Map<string, WorkflowStep[]>()
  const spineSteps: WorkflowStep[] = []
  for (const step of steps) {
    if (step.canvas_hidden) continue
    if (step.canvas_key) {
      const group = artifactGroups.get(step.canvas_key) ?? []
      artifactGroups.set(step.canvas_key, [...group, step])
    } else {
      spineSteps.push(step)
    }
  }

  // 脊收编 (ADR-051 G — a fold of ≤1 step is noise, not a group): the lone
  // folded step renders NO node; its edges resolve through the same ancestor
  // projection as a canvas_hidden step (zero new rules), and the asset feed
  // bridges DOWNSTREAM to its products (the R1 rule's natural conclusion —
  // the absorbed step's products ARE the roots' first rendered descendants).
  const spineAbsorbed = !spineExpanded && spineSteps.length <= 1

  // step id → rendered node id. A hidden step (render) resolves through its
  // own inputs to the first rendered ancestor — projection over the real
  // edge table, never invented lineage.
  const resolvedNode = new Map<string, string | null>()
  const resolveStepNode = (
    stepId: string,
    trail: Set<string> = new Set()
  ): string | null => {
    if (resolvedNode.has(stepId)) return resolvedNode.get(stepId)!
    if (trail.has(stepId)) return null // cycle guard — input is a DAG, never trust it
    trail.add(stepId)
    const step = byId.get(stepId)
    let id: string | null = null
    if (step) {
      if (step.canvas_key) {
        id = `artifact:${step.canvas_key}`
      } else if (!step.canvas_hidden && !spineAbsorbed) {
        id = spineExpanded ? `step:${step.id}` : SPINE_NODE_ID
      } else {
        for (const upstream of step.inputs ?? []) {
          id = resolveStepNode(upstream, trail)
          if (id) break
        }
      }
    }
    resolvedNode.set(stepId, id)
    return id
  }

  // Children index for the asset-feed fallback below.
  const childrenOf = new Map<string, string[]>()
  for (const step of steps) {
    for (const upstream of step.inputs ?? []) {
      childrenOf.set(upstream, [...(childrenOf.get(upstream) ?? []), step.id])
    }
  }
  /** Asset-feed target resolution (2026-08-19 二轮评审 R1): a canvas_hidden
   * ROOT (the prelude — preprocess/persona_bootstrap) has no inputs to walk
   * up, so a naive resolve drops the 素材 feed and parks the 任务书 in the
   * assets' own column. The feed instead walks DOWNSTREAM (seq order, cycle
   * guard) to the first rendered descendant — the edge lands on the 任务书
   * and the visible graph stays a DAG (素材→任务书→脊→产物). 脊收编 (G)
   * bridge: an absorbed step renders no node, so its PRODUCTS are the first
   * rendered descendants — the feed lands 素材 → 产物 directly. */
  const resolveAssetFeedTargets = (
    stepId: string,
    trail: Set<string> = new Set()
  ): string[] => {
    const direct = resolveStepNode(stepId)
    if (direct) return [direct]
    if (trail.has(stepId)) return []
    trail.add(stepId)
    const step = byId.get(stepId)
    if (step && !step.canvas_hidden && !step.canvas_key) {
      const produced = producedNodeIdsByStep.get(stepId)
      if (produced && produced.length > 0) return produced
    }
    const kids = [...(childrenOf.get(stepId) ?? [])].sort(
      (a, b) => (byId.get(a)?.seq ?? 0) - (byId.get(b)?.seq ?? 0)
    )
    return kids.flatMap((kid) => resolveAssetFeedTargets(kid, trail))
  }

  // Artifact cards (D6 修订; 2026-08-19 名词节点收窄后只有 "plan"): body =
  // the group's own copy (the plan card shows the picked direction in full
  // via canvas_text); the mention anchors to the group's last step.
  // canvas_key is derived live from the node class at serialization
  // (outputs.py, "never the row") — old runs re-render with the same
  // narrowed canvas, there are no persisted keys to migrate.
  for (const [key, members] of artifactGroups) {
    const sorted = [...members].sort((a, b) => a.seq - b.seq)
    const anchor = sorted[sorted.length - 1]
    const bodyMember = sorted.find((s) => s.canvas_text) ?? anchor
    const type = key.split(":", 1)[0]
    nodes.push({
      id: `artifact:${key}`,
      kind: "artifact",
      artifact: key,
      label: t(`results.canvas.artifact.${type}`, { defaultValue: type }),
      body: bodyMember.canvas_text ?? bodyMember.summary ?? undefined,
      // Plan 卡只展示任务书摘要 (body)，不展示内部工序 summary。
      detail: undefined,
      status: aggregateStatus(sorted),
      anchorStepId: anchor.id,
      order: sorted[0].seq,
    })
  }

  // The 过程脊: keyless plumbing folds into one expandable group node;
  // expanding reveals the step pills (artifact cards are unaffected). A
  // failed plumbing step no longer breaks out — the group node itself
  // carries the failed aggregate (the run's failure is narrated in chat).
  if (spineExpanded) {
    for (const step of spineSteps) {
      nodes.push({
        id: `step:${step.id}`,
        kind: "step",
        // The same friendly-name chain the chat step flow uses (prohibition
        // #10 — never a model name on the canvas).
        label:
          step.summary ||
          (step.stage
            ? t(`results.stepper.${step.stage}`, { defaultValue: "" })
            : "") ||
          t(`chat.stepKinds.${step.kind}`, { defaultValue: step.kind }),
        status: stepNodeStatus(step.status),
        order: step.seq,
      })
    }
  } else if (!spineAbsorbed) {
    nodes.push({
      id: SPINE_NODE_ID,
      kind: "spine",
      label: t("results.canvas.spine"),
      detail: t("results.canvas.spineSteps", { count: spineSteps.length }),
      status: aggregateStatus(spineSteps),
      expanded: false,
      order: Math.min(...spineSteps.map((s) => s.seq)),
    })
  }

  // Step-level dependency edges (the raw table; endpoints resolve to canvas
  // nodes in the final pass).
  for (const step of steps) {
    for (const upstream of step.inputs ?? []) {
      // Guard: edges only between steps present in this run's payload.
      if (stepIds.has(upstream)) {
        rawEdges.push({
          from: `step:${upstream}`,
          to: `step:${step.id}`,
          semantic: "dependency",
        })
      }
    }
  }

  // The asset feed runs AFTER the roster below (the 脊收编 bridge lands on
  // the absorbed step's product/placeholder nodes, which must exist first).

  const TEXT_PRODUCT_TYPES = new Set(["post", "article"])

  // (2026-08-17 走查拍板): the run's only excerpt vocabulary belongs to
  // real excerpts — materialize_source stamps segment.id="full" and the
  // fork family (translate / dub) carries the same source_ref downstream.
  const isWholeSourceClip = (o: Output) =>
    o.type === "clip" &&
    (o.source_ref?.segment as { id?: string } | undefined)?.id === "full"

  // Products: newest-first payload → stable ascending order within a layer.
  const products = [...outputs]
    .filter((o) => o.type in PRODUCT_TYPE_LABEL_KEY)
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
  const productIds = new Set(products.map((o) => o.id))
  // Top pick: the batch's highest-scored clip gets the accent badge — the
  // same triage rule the old results grid used (score → what to post first).
  const topClipScore = Math.max(
    0,
    ...products
      .filter((o) => o.type === "clip")
      .map((o) => (typeof o.score?.value === "number" ? o.score.value : 0)),
  )

  // ── Placeholder roster merge (ADR-051 B — 占位物化) ────────────────────
  // Products of THIS run's producing steps fill placeholder slots IN PLACE
  // (the slot and its filler share the roster index, so the card never
  // moves); everything else (earlier runs' rows, step-less rows) is carried
  // and keeps plain created_at order ahead of the roster. A slot block's
  // leftover products (runtime-decided families — the quote chain's frame
  // cards and motion clip) append right behind their step's slots.
  type RosterEntry =
    | { kind: "output"; output: Output }
    | { kind: "placeholder"; row: PlaceholderRow; ordinal: number }
  const roster: RosterEntry[] = []
  const rosterStepIds = new Set((placeholders ?? []).map((r) => r.step_id))
  const productsByStep = new Map<string, Output[]>()
  for (const output of products) {
    if (output.workflow_step_id && rosterStepIds.has(output.workflow_step_id)) {
      const group = productsByStep.get(output.workflow_step_id) ?? []
      group.push(output)
      productsByStep.set(output.workflow_step_id, group)
    } else {
      roster.push({ kind: "output", output })
    }
  }
  for (const row of placeholders ?? []) {
    const pool = productsByStep.get(row.step_id) ?? []
    // Type-preferred fill: a slot consumes the pool's first output matching
    // its vocabulary (clip slots respect the whole/excerpt split), falling
    // back to plain ordinal when the family is runtime-decided (the quote
    // chain materializes quote_frame rows under a "quotes" slot).
    const take = (): Output | undefined => {
      const matchIdx = pool.findIndex((o) =>
        row.type === "clip"
          ? o.type === "clip" && isWholeSourceClip(o) === row.whole
          : o.type === row.type,
      )
      if (matchIdx >= 0) return pool.splice(matchIdx, 1)[0]
      return pool.shift()
    }
    for (let ordinal = 0; ordinal < row.count; ordinal++) {
      const filled = take()
      roster.push(
        filled
          ? { kind: "output", output: filled }
          : { kind: "placeholder", row, ordinal },
      )
    }
    for (const sibling of pool) roster.push({ kind: "output", output: sibling })
  }

  // ── Fork family map (ADR-051 F2 — 变体分页) ────────────────────────────
  // One family = every visible row connected through derived_from chains
  // (translate/dub "再来一版" forks) — each member a REAL row with its own
  // media. source_ref.parents (the quote chain's frames ↔ composite) is
  // sub-artifact lineage, never a version family. Members are already in
  // created_at order (products was sorted above).
  const productById = new Map(products.map((o) => [o.id, o]))
  const rootOf = (o: Output): string => {
    const seen = new Set<string>([o.id])
    let cur = o
    while (cur.source_ref?.derived_from_output_id) {
      const parentId = cur.source_ref.derived_from_output_id
      if (seen.has(parentId)) break // cycle guard — never trust input
      seen.add(parentId)
      const parent = productById.get(parentId)
      if (!parent) break // unknown parents (outside the payload) drop
      cur = parent
    }
    return cur.id
  }
  const familyOf = new Map<string, Output[]>()
  const familyGroups = new Map<string, Output[]>()
  for (const o of products) {
    const root = rootOf(o)
    familyGroups.set(root, [...(familyGroups.get(root) ?? []), o])
  }
  for (const members of familyGroups.values()) {
    if (members.length < 2) continue
    for (const m of members) familyOf.set(m.id, members)
  }

  // step → its rendered product/placeholder node ids (the 脊收编 feed bridge
  // — populated as the roster materializes the nodes).
  const producedNodeIdsByStep = new Map<string, string[]>()
  const markProduced = (stepId: string, nodeId: string) => {
    producedNodeIdsByStep.set(stepId, [
      ...(producedNodeIdsByStep.get(stepId) ?? []),
      nodeId,
    ])
  }

  roster.forEach((entry, i) => {
    if (entry.kind === "placeholder") {
      const { row, ordinal } = entry
      const id = `placeholder:${row.step_id}:${ordinal}`
      markProduced(row.step_id, id)
      nodes.push({
        id,
        kind: "output",
        label: row.whole
          ? t("generationOverlay.assetTypes.video", { defaultValue: "Video" })
          : t(PRODUCT_TYPE_LABEL_KEY[row.type], { defaultValue: row.type }),
        detail: row.language
          ? t(`languages.${row.language}`, { defaultValue: row.language })
          : undefined,
        // The producing step's own status — a running step gives the
        // placeholder its FLORA wipe (the card's run 期 projection).
        status: stepNodeStatus(byId.get(row.step_id)?.status ?? "pending"),
        placeholder: {
          stepId: row.step_id,
          type: row.type,
          whole: row.whole,
          language: row.language,
          variant: row.variant,
          aspect: row.aspect,
        },
        size: TEXT_PRODUCT_TYPES.has(row.type)
          ? textProductNodeSize(PLACEHOLDER_TEXT_LINES)
          : productNodeSize(row.aspect),
        order: i,
      })
      // Same lineage rule as a landed product — the edge's from-endpoint is
      // identical across the fill swap (only the to-id re-keys).
      if (stepIds.has(row.step_id)) {
        rawEdges.push({
          from: `step:${row.step_id}`,
          to: id,
          semantic: "lineage",
        })
      }
      return
    }
    const output = entry.output
    const id = `output:${output.id}`
    if (output.workflow_step_id) markProduced(output.workflow_step_id, id)
    const thumbUrl = toAbsoluteUrl(
      output.files.image ?? output.publishing.cover_image_url ?? null,
    )
    // Multi-item outputs (quotes = N cards, carousel = N slides): the node
    // carries one display variant per item — the hover switcher flips the
    // main display (the first quote's baked image is the only media; the
    // rest render as text tiles).
    const quotes = output.type === "quotes" ? (output.payload.quotes ?? []) : []
    const slides = output.type === "carousel" ? (output.payload.slides ?? []) : []
    const variants =
      quotes.length > 1
        ? quotes.map((q, qi) => ({
            label: q.quote,
            sub: q.attribution,
            thumbUrl: qi === 0 ? thumbUrl : null,
          }))
        : slides.length > 1
          ? slides.map((s) => ({
              label: s.title,
              sub: s.body ?? undefined,
              thumbUrl: null,
            }))
          : undefined
function textContentFromOutput(output: Output): FlowNode["textContent"] | undefined {
  if (!TEXT_PRODUCT_TYPES.has(output.type)) return undefined
  const title = output.publishing.title ?? output.payload.title ?? null
  const body = output.payload.content ?? ""
  const hashtags = output.publishing.hashtags ?? output.payload.hashtags ?? []
  if (!title && !body && hashtags.length === 0) return undefined
  return { title, body, hashtags }
}

function textProductLineCount(output: Output): number {
  const tc = textContentFromOutput(output)
  if (!tc) return 0
  // Estimate visible lines from the body at the card's text width (~248px,
  // text-xs). A rough heuristic: ~55 chars per line for Latin, ~35 for CJK.
  const cjk = /[一-龥぀-ゟ゠-ヿ]/.test(tc.body)
  const charsPerLine = cjk ? 35 : 55
  const bodyLines = Math.max(1, Math.ceil(tc.body.length / charsPerLine))
  const titleLines = tc.title ? 1 : 0
  // We count title + body, then clamp to the 2–8 preview range.
  return Math.min(8, Math.max(2, titleLines + bodyLines))
}
    const textContent = textContentFromOutput(output)
    const textLines = textContent ? textProductLineCount(output) : 0
    const wholeSource = isWholeSourceClip(output)
    nodes.push({
      id,
      kind: "output",
      label: wholeSource
        ? t("generationOverlay.assetTypes.video", { defaultValue: "Video" })
        : t(PRODUCT_TYPE_LABEL_KEY[output.type], { defaultValue: output.type }),
      detail: output.language
        ? t(`languages.${output.language}`, { defaultValue: output.language })
        : undefined,
      thumbUrl,
      // The product card skin (D5): the node carries the row, sized as the
      // canvas's 大卡; the tour anchors ride the surface's chosen node. The
      // node keeps the clip's own frame (2026-08-14 三档画幅 on the canvas —
      // 9:16/1:1/16:9 node sizes, never a forced crop; "original" whole-
      // source rows take the landscape strip until the media element
      // reports its real pixels to the toolbar).
      output,
      prompt: prompt ?? null,
      specPrompt: output.spec_prompt ?? null,
      familyOutputs: familyOf.get(output.id),
      variants,
      textContent,
      topPick:
        output.type === "clip" &&
        topClipScore > 0 &&
        output.score?.value === topClipScore,
      // Node frame = the server-derived display aspect (产物展示统一:
      // render_spec.aspect → payload.aspect → null). quote_frame payload
      // pins "9:16"; "original" whole-source rows normalize to null and
      // take the default tier until media reports real pixels. Text products
      // (post / article) have no aspect — the card is sized by preview line
      // count instead.
      size:
        textContent && textLines > 0
          ? textProductNodeSize(textLines)
          : productNodeSize(output.aspect ?? null),
      tourTargets: output.id === tourOutputId,
      order: i,
    })
    // Lineage = the server-resolved producing step (prohibition #11). Rows
    // carried over from an earlier run point at steps outside this payload —
    // the node still renders, edgeless, rather than inventing a parent.
    if (output.workflow_step_id && stepIds.has(output.workflow_step_id)) {
      rawEdges.push({
        from: `step:${output.workflow_step_id}`,
        to: id,
        semantic: "lineage",
      })
    }
    // Derivation lineage (quote-cards §2.2, 2026-08-28): source_ref.parents
    // names the outputs THIS one derives from — the chain composite's frame
    // cards (N→1) and the motion clip's composite. Server-resolved like
    // workflow_step_id; unknown parents (outside this payload) drop.
    for (const parentId of output.source_ref?.parents ?? []) {
      if (productIds.has(parentId)) {
        rawEdges.push({
          from: `output:${parentId}`,
          to: id,
          semantic: "lineage",
        })
      }
    }
  })

  // Source assets feed the root steps (the run's entry points) — process
  // order, so the dependency semantic (recipe adapter precedent). A hidden
  // root (the prelude) resolves DOWNSTREAM to its first rendered descendant
  // (R1) — resolved here because the final pass only walks up. Runs after
  // the roster so the 脊收编 bridge can land on the absorbed step's
  // product/placeholder nodes.
  const roots = steps.filter((s) => (s.inputs ?? []).length === 0)
  for (const asset of assets) {
    for (const root of roots) {
      for (const target of resolveAssetFeedTargets(root.id)) {
        rawEdges.push({
          from: `asset:${asset.id}`,
          to: target,
          semantic: "dependency",
        })
      }
    }
  }

  // Final pass: step endpoints resolve to their canvas node (artifact card /
  // spine / step pill when the spine is expanded; hidden steps walk to their
  // first rendered ancestor). Self-loops and duplicates collapse — the
  // visible graph stays 真边, never invented.
  const seen = new Set<string>()
  const edges: FlowEdge[] = []
  for (const e of rawEdges) {
    const from = e.from.startsWith("step:")
      ? resolveStepNode(e.from.slice(5))
      : e.from
    const to = e.to.startsWith("step:")
      ? resolveStepNode(e.to.slice(5))
      : e.to
    if (!from || !to || from === to) continue
    const key = `${from}|${to}|${e.semantic}`
    if (seen.has(key)) continue
    seen.add(key)
    edges.push({ from, to, semantic: e.semantic })
  }

  return { nodes, edges }
}
