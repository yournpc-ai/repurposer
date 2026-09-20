/** Chat wire protocol (Phase 3 Batch C test seam): the normalize family +
 * the plan/brief row vocabulary, extracted from ChatDock as PURE functions
 * (行为零变化 — the same branches, the same read tolerance). Wire types
 * live here too (TaskItem / InferredIntent / BriefSlot / Brief): they are
 * the payload vocabulary these normalizers speak, and ChatDock imports
 * them back — one source, no parallel copies. */

import type { IntentSlot } from "@/lib/types"

/** One task in the plan chain (ADR-043 — the request layer's only grammar:
 * a registry tool + its params, the same shape the intent router proposes and
 * the chat loop adjudicates). Outputs are a derived projection of the
 * compiled chain, never a panel declaration. */
export interface TaskItem {
  tool: string
  params: Record<string, unknown>
}

export interface InferredIntent {
  /** The intent router's four-action payload (ADR-052 B2 — `generate`
   * renamed to `draft`: it never generates, it drafts the task plan). The
   * panel round-trips the value; only `draft` plans are ever editable. */
  action: "draft" | "ask" | "answer" | "start"
  answer: string | null
  tasks: TaskItem[]
  specific_instruction: string | null
  /** Caption-language policy for captioned chains (write_quotes / clips),
   * answered via the dock's caption question. The panel never edits it —
   * it only round-trips so Start doesn't drop the user's choice (the
   * server treats a missing mode as "not mentioned", never "retracted"). */
  caption_mode?: "bilingual" | "source_only" | "target_only" | null
  /** The proposer's fresh naming of the run/plan (ADR-058 — LLM 建图时命名):
   * a compact noun phrase in the interface language; "" = unnamed (readers
   * fall back to the chain-derived label). */
  name?: string
}

const LEGACY_SLOT_TO_TOOL: Record<string, string> = {
  clips: "select_clips",
  post: "write_post",
  quotes: "write_quotes",
  carousel: "write_carousel",
  article: "write_article",
}

function normalizeTasks(raw: unknown): TaskItem[] {
  if (!Array.isArray(raw)) return []
  const tasks: TaskItem[] = []
  for (const item of raw) {
    if (
      item &&
      typeof item === "object" &&
      typeof (item as { tool?: unknown }).tool === "string"
    ) {
      const params = (item as { params?: unknown }).params
      tasks.push({
        tool: (item as { tool: string }).tool,
        params:
          params && typeof params === "object" && !Array.isArray(params)
            ? (params as Record<string, unknown>)
            : {},
      })
    }
  }
  return tasks
}

/** outputs-grammar → task list (client-side read tolerance for legacy
 * run.context rows; the same conversion the server applies to stored
 * pending_brief plans). */
function legacyOutputsToTasks(data: Record<string, unknown>): TaskItem[] {
  const tasks: TaskItem[] = []
  const aspect = typeof data.aspect === "string" ? data.aspect : null
  for (const slot of normalizeSlots(data.outputs, data.clip_count as number | null)) {
    const tool = LEGACY_SLOT_TO_TOOL[slot.type]
    if (!tool) continue
    const params: Record<string, unknown> = {}
    if (slot.count != null) params.count = slot.count
    if (slot.focus) params.focus = slot.focus
    if (slot.language) params.language = slot.language
    if (slot.tone_override) params.tone_override = slot.tone_override
    if (tool === "select_clips" && aspect) params.aspect = aspect
    tasks.push({ tool, params })
  }
  for (const lang of Array.isArray(data.dub_languages) ? data.dub_languages : []) {
    if (typeof lang === "string" && lang) {
      // fork: pre-ADR-043 compiles produced dub/translate as fork nodes
      // (derived rows, source untouched) — the upgrade keeps that shape so a
      // panel re-submit / tab retry doesn't morph the originals in place.
      tasks.push({ tool: "dub_clip", params: { target_language: lang, fork: true } })
    }
  }
  const bilingual = data.caption_bilingual === true
  for (const lang of Array.isArray(data.caption_languages) ? data.caption_languages : []) {
    if (typeof lang === "string" && lang) {
      tasks.push({
        tool: "translate_clip",
        params: { target_language: lang, bilingual, fork: true },
      })
    }
  }
  return tasks
}

/** Normalize an intent payload into the task-chain InferredIntent the panel
 * edits. Tasks pass through verbatim; a legacy outputs-grammar payload
 * (stored run contexts, old plans) upgrades on read. */
export function normalizeIntent(raw: unknown): InferredIntent {
  const data = (raw ?? {}) as Record<string, unknown>
  const tasks = Array.isArray(data.tasks)
    ? normalizeTasks(data.tasks)
    : legacyOutputsToTasks(data)
  const action = data.action
  return {
    action:
      action === "answer" || action === "ask" || action === "start"
        ? action
        : "draft",
    answer: (data.answer as string | null) ?? null,
    tasks,
    specific_instruction: (data.specific_instruction as string | null) ?? null,
    caption_mode:
      (data.caption_mode as InferredIntent["caption_mode"]) ?? null,
    // The proposer's fresh naming (ADR-058): "" = unnamed → readers fall
    // back to the chain-derived label.
    name: typeof data.name === "string" ? data.name : "",
  }
}

/** A run's chain (ADR-043): context.tasks verbatim; legacy outputs-grammar
 * contexts upgrade on read (the same conversion as normalizeIntent's). */
export function tasksFromRunContext(ctx: unknown): TaskItem[] {
  const data = (ctx ?? {}) as Record<string, unknown>
  return Array.isArray(data.tasks)
    ? normalizeTasks(data.tasks)
    : legacyOutputsToTasks(data)
}

// ---------------------------------------------------------------------------
// brief (ADR-052 B2/B3): the dialog engine's structured state, mirrored
// from the API. The plan card renders the brief's valued slots (the agent's
// own understanding) instead of blank form fields; an inferred slot value is
// clickable and its edit rides the normal chat send channel (chat is the one
// and only revision channel — the click-to-edit is its shorthand).
// ---------------------------------------------------------------------------

type BriefSlotSource = "user-stated" | "inferred" | "default"

export interface BriefSlot<T> {
  value: T | null
  source: BriefSlotSource
}

/** The slots the plan card renders. `material_state` is code-stamped
 * server-side (none/pasted/attached); the card shows it only when material
 * exists. `constraints` and the code-owned `asked` roll stay off the card. */
export interface Brief {
  topic: BriefSlot<string>
  audience: BriefSlot<string>
  tone: BriefSlot<string>
  material_state: BriefSlot<"none" | "pasted" | "attached">
}

function normalizeBriefSlot<T>(raw: unknown): BriefSlot<T> {
  const data = (raw ?? {}) as Record<string, unknown>
  const source = data.source
  return {
    value: (data.value as T | null) ?? null,
    source:
      source === "user-stated" || source === "inferred" ? source : "default",
  }
}

/** Tolerate a missing/partial brief payload (old question rows pre-B3 carry
 * no `brief` key — read tolerance only, never written back). */
export function normalizeBrief(raw: unknown): Brief | null {
  if (!raw || typeof raw !== "object") return null
  const data = raw as Record<string, unknown>
  return {
    topic: normalizeBriefSlot<string>(data.topic),
    audience: normalizeBriefSlot<string>(data.audience),
    tone: normalizeBriefSlot<string>(data.tone),
    material_state: normalizeBriefSlot<"none" | "pasted" | "attached">(
      data.material_state
    ),
  }
}

/** Tolerate both run.context slot shapes (outputs = derive, ADR-043): slot
 * objects pass through; legacy flat rows (string outputs + flat counts)
 * upgrade to bare slots. Internal to the legacy→tasks upgrader — read
 * tolerance only, never written back. */
function normalizeSlots(
  raw: unknown,
  legacyClipCount?: number | null
): IntentSlot[] {
  if (!Array.isArray(raw)) return []
  const bare = (type: string, count: number | null = null): IntentSlot => ({
    type: type as IntentSlot["type"],
    count,
    focus: null,
    language: null,
    tone_override: null,
    explicit: false,
  })
  const slots: IntentSlot[] = []
  for (const item of raw) {
    if (typeof item === "string") {
      if (item in LEGACY_SLOT_TO_TOOL) {
        slots.push(bare(item, item === "clips" ? (legacyClipCount ?? null) : null))
      }
    } else if (item && typeof item === "object" && typeof item.type === "string") {
      if (item.type in LEGACY_SLOT_TO_TOOL) {
        slots.push({
          ...bare(item.type),
          count: item.count ?? null,
          focus: item.focus ?? null,
          language: item.language ?? null,
          tone_override: item.tone_override ?? null,
          explicit: item.explicit ?? false,
        })
      }
    }
  }
  return slots
}
