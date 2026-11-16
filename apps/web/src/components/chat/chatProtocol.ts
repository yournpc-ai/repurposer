/** Chat wire protocol (Phase 3 Batch C test seam): the normalize family +
 * the plan/brief row vocabulary, extracted from ChatDock as PURE functions
 * (行为零变化 — the same branches, the same read tolerance). Wire types
 * live here too (TaskItem / InferredIntent / BriefSlot / Brief): they are
 * the payload vocabulary these normalizers speak, and ChatDock imports
 * them back — one source, no parallel copies. */

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
  /** The proposer's fresh naming of the run/plan (ADR-058 — LLM 建图时命名):
   * a compact noun phrase in the interface language; "" = unnamed (readers
   * fall back to the chain-derived label). */
  name?: string
}

function normalizeTasks(raw: unknown): TaskItem[] {
  if (!Array.isArray(raw)) return []
  const tasks: TaskItem[] = []
  for (const item of raw) {
    if (item && typeof item === "object" && typeof (item as { tool?: unknown }).tool === "string") {
      const params = (item as { params?: unknown }).params
      tasks.push({
        tool: (item as { tool: string }).tool,
        params: params && typeof params === "object" && !Array.isArray(params)
          ? (params as Record<string, unknown>)
          : {},
      })
    }
  }
  return tasks
}

/** Normalize the current task-list intent. */
export function normalizeIntent(raw: unknown): InferredIntent {
  const data = (raw ?? {}) as Record<string, unknown>
  const tasks = normalizeTasks(data.tasks)
  const action = data.action
  return {
    action:
      action === "answer" || action === "ask" || action === "start"
        ? action
        : "draft",
    answer: (data.answer as string | null) ?? null,
    tasks,
    specific_instruction: (data.specific_instruction as string | null) ?? null,
    // The proposer's fresh naming (ADR-058): "" = unnamed → readers fall
    // back to the chain-derived label.
    name: typeof data.name === "string" ? data.name : "",
  }
}

/** Read the current Run's authorized task list. */
export function tasksFromRunContext(ctx: unknown): TaskItem[] {
  const data = (ctx ?? {}) as Record<string, unknown>
  return normalizeTasks(data.tasks)
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
