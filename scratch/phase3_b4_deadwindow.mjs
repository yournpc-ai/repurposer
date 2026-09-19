// Phase 3 Batch B ④ — creating_run dead-window forensics (裁决 2: 先证后删).
// Raw-CDP headless Chrome samples the dock DOM every 50ms across the Start
// transition and asserts per sample:
//   (a) ≥1 surface visible: confirm pill (idle or Starting…) / System Status
//       row / active Activity row / run surface (start line or task list)
//   (b) the covering surface is NEVER solely the ThinkingRow carrying the
//       creating_run label ("Creating your workflow…" with no svg = the
//       System Status seat; the same text under svg.animate-spin = Activity).
// Scenario A clicks the pill's Start; scenario B types "start it" (G-1 prose
// path) via trusted CDP input events. Usage:
//   node phase3_b4_deadwindow.mjs <projectId> <jwt> <userJson> A|B [log]
import { spawn } from "node:child_process"
import { writeFileSync, appendFileSync } from "node:fs"
import http from "node:http"

const [PID, TOKEN, USER_JSON, SCENARIO] = process.argv.slice(2)
const LOG = process.argv[6] ?? "/tmp/phase3_b4_deadwindow.log"
if (!PID || !TOKEN || !/^[AB]$/.test(SCENARIO ?? "")) {
  console.error("usage: node phase3_b4_deadwindow.mjs <pid> <jwt> <userJson> A|B [log]")
  process.exit(1)
}
const PAGE_URL = `http://localhost:3000/projects/${PID}`

const log = (msg) => {
  const line = `[${new Date().toISOString().slice(11, 19)}.${String(Date.now() % 1000).padStart(3, "0")}] ${msg}\n`
  appendFileSync(LOG, line)
  process.stdout.write(line)
}
writeFileSync(LOG, "")

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9227
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-b4-profile",
  "--window-size=1680,1000",
  "--no-first-run",
  "--mute-audio",
  "about:blank",
], { stdio: "ignore" })
process.on("exit", () => chrome.kill())

const getJson = (path) =>
  new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port: PORT, path }, (res) => {
      let buf = ""
      res.on("data", (c) => (buf += c))
      res.on("end", () => resolve(JSON.parse(buf)))
    }).on("error", reject)
  })

let targets = null
for (let i = 0; i < 50; i++) {
  try {
    targets = await getJson("/json/list")
    break
  } catch {
    await new Promise((r) => setTimeout(r, 200))
  }
}
if (!targets) throw new Error("chrome did not come up")
const page = targets.find((t) => t.type === "page")
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((r) => (ws.onopen = r))

let msgId = 0
const pending = new Map()
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    const id = ++msgId
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) {
    pending.get(m.id).resolve(m.result ?? m.error)
    pending.delete(m.id)
  } else if (m.method === "Runtime.exceptionThrown") {
    log(`PAGE-EXCEPTION: ${JSON.stringify(m.params.exceptionDetails).slice(0, 400)}`)
  }
}
const evalJs = async (expr) =>
  (await send("Runtime.evaluate", { expression: expr, returnByValue: true }))?.result?.value

await send("Runtime.enable")
await send("Page.enable")
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});
           localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});
           document.cookie = "repurposer-lang=en;path=/";
           localStorage.setItem("repurposer-tour-seen", "seeded");`,
})
await send("Page.navigate", { url: PAGE_URL })
log(`navigated ${PAGE_URL} scenario=${SCENARIO}`)

// ---- surface probe ---------------------------------------------------------
// Surface inventory (ADR-087 三通道分家, client seats):
//   pill      — the confirm pill's Start control ("Start generation" idle /
//               "Starting…" busy) — the confirm beat's affordance
//   status    — the System Status row (ThinkingRow): shimmer label WITHOUT a
//               sibling svg, non-button (thinkingPhases.* / chat.thinking)
//   activity  — an active Activity row: svg.animate-spin inside the flow
//   run       — run surface: the start line prose OR the RunTaskList row
//               (button StatusLine) OR its narrative fallback text
const PROBE = `(() => {
  const vis = (el) => {
    if (!el) return false
    const r = el.getBoundingClientRect()
    const cs = getComputedStyle(el)
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"
  }
  const btns = [...document.querySelectorAll("button")].filter(vis)
  const pill = btns.find(b => /^(Start generation|Starting…)$/.test((b.textContent || "").trim()))
  const shimmers = [...document.querySelectorAll(".shimmer")].filter(vis).map(sp => {
    const row = sp.closest("button") || sp.parentElement
    const isRun = sp.closest("button") != null
    const hasSpinSvg = !!(row && row.querySelector("svg.animate-spin"))
    return { text: (sp.textContent || "").trim(), kind: isRun ? "run" : hasSpinSvg ? "activity" : "status" }
  })
  const bodyText = document.body.innerText || ""
  const startLine = bodyText.includes("I'm starting your generation")
  const queuedNarr = /Queued, starting soon…|Transcribing your media…/.test(bodyText)
  return JSON.stringify({
    pill: pill ? (pill.textContent || "").trim() : null,
    shimmers,
    startLine,
    queuedNarr,
    textLen: bodyText.length,
  })
})()`

// ---- wait for the confirm beat (stamp-driven, post-Batch-B derived) --------
let ready = false
for (let i = 0; i < 240; i++) {
  const v = await evalJs(`(() => {
    const vis = (el) => !!el && el.getBoundingClientRect().width > 0
    const b = [...document.querySelectorAll("button")].filter(vis)
      .find(b => (b.textContent || "").trim() === "Start generation")
    return b ? (b.disabled ? "disabled" : "enabled") : null
  })()`)
  if (v === "enabled") { ready = true; break }
  if (i % 20 === 0) log(`waiting confirm beat… (${v ?? "no pill"})`)
  await new Promise((r) => setTimeout(r, 250))
}
if (!ready) { log("FATAL: confirm pill never enabled — seed/stamp broken"); process.exit(1) }
log("confirm beat live: Start enabled")

// ---- fire the Start gesture ------------------------------------------------
let samples = 0
let deadWindows = 0
let creatingRunOnly = 0
let sawRunSurface = false
let firstRunSurfaceAt = null
const t0 = Date.now()

if (SCENARIO === "A") {
  const clicked = await evalJs(`(() => {
    const b = [...document.querySelectorAll("button")]
      .find(b => (b.textContent || "").trim() === "Start generation" && b.getBoundingClientRect().width > 0)
    if (!b) return false
    b.click()
    return true
  })()`)
  if (!clicked) { log("FATAL: Start button not clickable"); process.exit(1) }
  log("START fired: pill click")
} else {
  // G-1 prose path: focus the dock editor, insert text, press Enter.
  const focused = await evalJs(`(() => {
    const ed = document.querySelector("[contenteditable=true]")
    if (!ed) return false
    ed.focus()
    return true
  })()`)
  if (!focused) { log("FATAL: dock editor not found"); process.exit(1) }
  await send("Input.insertText", { text: "start it" })
  await send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 })
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 })
  log("START fired: G-1 prose 'start it' + Enter")
}

// ---- 50ms sampling across the transition -----------------------------------
let prevTextLen = null
while (Date.now() - t0 < 45000) {
  const v = await evalJs(PROBE)
  samples++
  if (v) {
    const d = JSON.parse(v)
    // Prose in motion IS the turn's activity evidence (打字机律) — the
    // conversation channel's typing counts as a cover, detected as the
    // page text growing between samples.
    const proseMoving = prevTextLen != null && d.textLen > prevTextLen
    prevTextLen = d.textLen
    const pillUp = d.pill != null
    const statusRows = d.shimmers.filter((s) => s.kind === "status")
    const actActive = d.shimmers.some((s) => s.kind === "activity")
    const runUp = d.startLine || d.queuedNarr || d.shimmers.some((s) => s.kind === "run")
    const covered = pillUp || statusRows.length > 0 || actActive || runUp || proseMoving
    const tag = `${samples} pill=${d.pill ?? "-"} rows=[${d.shimmers.map((s) => `${s.kind}:${s.text.slice(0, 30)}`).join("|")}] run=${runUp} prose=${proseMoving ? "+" : "="} len=${d.textLen}`
    log(`S ${tag}`)
    if (!covered) {
      deadWindows++
      log(`DEAD-WINDOW sample=${samples} ${v}`)
    }
    // (b): the ONLY cover = the status row carrying the creating_run label?
    const creatingOnly =
      !pillUp && !actActive && !runUp && !proseMoving &&
      statusRows.length > 0 &&
      statusRows.every((s) => s.text === "Creating your workflow…")
    if (creatingOnly) {
      creatingRunOnly++
      log(`CREATING_RUN-ONLY sample=${samples} ${v}`)
    }
    if (runUp && !sawRunSurface) {
      sawRunSurface = true
      firstRunSurfaceAt = Date.now() - t0
      log(`RUN SURFACE at +${firstRunSurfaceAt}ms: ${v}`)
    }
  }
  if (sawRunSurface && Date.now() - t0 > firstRunSurfaceAt + 1500) break
  await new Promise((r) => setTimeout(r, 50))
}

log(`--- verdict: samples=${samples} dead=${deadWindows} creatingRunOnly=${creatingRunOnly} runSurface=${sawRunSurface} (+${firstRunSurfaceAt}ms)`)
if (!sawRunSurface) { log("FAIL: run surface never arrived (G-1 LLM variance or real break)"); process.exit(1) }
if (deadWindows > 0) { log("FAIL: dead window exists — creating_run must NARROW to System Status, not delete"); process.exit(1) }
if (creatingRunOnly > 0) { log("FAIL: creating_run label was the sole cover — deletion unsafe"); process.exit(1) }
log("PASS: no dead window; creating_run never the sole cover — delete candidate CONFIRMED")
chrome.kill()
process.exit(0)
