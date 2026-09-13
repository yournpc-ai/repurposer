// Deep canvas forensics watcher (vanish-bug round 2): raw-CDP headless Chrome,
// samples the React Flow DOM every 150ms — per-node visibility + rects +
// viewport transform — and classifies the failure family live:
//   COUNT-DROP  : fewer .react-flow__node wrappers than expected (store layer)
//   HIDDEN      : wrappers present but computed visibility!=visible (measure gate)
//   OFFSCREEN   : wrappers visible but all rects outside the window (viewport aim)
// Never clicks/types — the run is started via repro_vanish_start.py.
import { spawn } from "node:child_process"
import { writeFileSync, appendFileSync } from "node:fs"
import http from "node:http"

const PAGE_URL = process.argv[2]
const TOKEN = process.argv[3]
const USER_JSON = process.argv[4] ?? '{"id":"52037604-9321-4b70-9212-445ccf5ade60","email":"dev@local"}'
const DURATION_S = Number(process.argv[5] ?? 300)
const LOG = process.argv[6] ?? "/tmp/canvas_watch2.log"
// When "click", the watcher clicks the task-book Start control in-page once it
// appears — the dock then drives the run exactly as a user's click would
// (its SSE + the page's per-step refetches all fire from the real surface).
const CLICK_START = process.argv[7] === "click"

if (!PAGE_URL || !TOKEN) {
  console.error("usage: node cdp_watch2.mjs <page-url> <jwt> [userJson] [durationS] [log]")
  process.exit(1)
}

const log = (msg) => {
  const line = `[${new Date().toISOString().slice(11, 19)}.${String(Date.now() % 1000).padStart(3, "0")}] ${msg}\n`
  appendFileSync(LOG, line)
  process.stdout.write(line)
}
writeFileSync(LOG, "")

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9224
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-watch2-profile",
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
  } else if (m.method === "Runtime.consoleAPICalled") {
    const text = (m.params.args ?? []).map((a) => a.value ?? a.description ?? "").join(" ")
    if (["error", "warning"].includes(m.params.type)) log(`CONSOLE.${m.params.type}: ${text.slice(0, 300)}`)
  } else if (m.method === "Runtime.exceptionThrown") {
    log(`PAGE-EXCEPTION: ${JSON.stringify(m.params.exceptionDetails).slice(0, 600)}`)
  }
}

await send("Runtime.enable")
await send("Page.enable")
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});
           localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});`,
})
await send("Page.navigate", { url: PAGE_URL })
log(`navigated ${PAGE_URL}`)

const SAMPLE = `(() => {
  const W = window.innerWidth, H = window.innerHeight
  const nodes = [...document.querySelectorAll(".react-flow__node")].map(n => {
    const cs = getComputedStyle(n)
    const r = n.getBoundingClientRect()
    return {
      i: (n.dataset.id || "?").slice(0, 4),
      v: cs.visibility === "visible" ? 1 : 0,
      d: cs.display === "none" ? 0 : 1,
      r: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      sw: n.style.width || "", sh: n.style.height || "",
    }
  })
  const edges = document.querySelectorAll(".react-flow__edge").length
  const edgeIds = [...document.querySelectorAll(".react-flow__edge")].map(e => (e.dataset.id || e.getAttribute("data-testid") || "?").slice(0, 22)).join(",")
  const vpEl = document.querySelector(".react-flow__viewport")
  const vp = vpEl ? (vpEl.style.transform || getComputedStyle(vpEl).transform) : "?"
  const pane = document.querySelector(".react-flow__nodes")
  const paneVis = pane ? getComputedStyle(pane).visibility + "/" + getComputedStyle(pane).display : "-"
  const onScreen = nodes.filter(n => n.v && n.d && n.r[2] > 0 && n.r[0] < W && n.r[0] + n.r[2] > 0 && n.r[1] < H && n.r[1] + n.r[3] > 0).length
  const bodyText = document.body.innerText || ""
  const phase = (bodyText.match(/(Translating|Preparing|Rendering|Understanding|Transcribing)[^\\n]{0,30}/) || [""])[0].slice(0, 44)
  return JSON.stringify({ n: nodes.length, edges, edgeIds, onScreen, vp: String(vp).slice(0, 60), paneVis, phase, nodes: nodes.slice(0, 10) })
})()`

const start = Date.now()
let lastSig = null
let lastBeat = 0
let clicked = false
const CLICK_EXPR = `(() => {
  const btns = [...document.querySelectorAll("button")].filter(b => b.offsetParent !== null)
  const b = btns.find(b => /^(Start generation|开始生成|开始|Start)$/i.test((b.textContent || "").trim()))
  if (!b) return "not-found"
  b.click()
  return "clicked: " + (b.textContent || "").trim().slice(0, 30)
})()`
while ((Date.now() - start) / 1000 < DURATION_S) {
  if (CLICK_START && !clicked) {
    try {
      const res = await send("Runtime.evaluate", { expression: CLICK_EXPR, returnByValue: true })
      const v = res?.result?.value
      if (v && v !== "not-found") {
        clicked = true
        log(`START-CLICK: ${v}`)
      }
    } catch (e) {
      log(`click-error: ${String(e).slice(0, 160)}`)
    }
  }
  try {
    const res = await send("Runtime.evaluate", { expression: SAMPLE, returnByValue: true })
    const v = res?.result?.value
    if (v) {
      const d = JSON.parse(v)
      const hidden = d.nodes.filter((x) => !x.v || !x.d).length
      const zeroSize = d.nodes.filter((x) => x.r[2] === 0 || x.r[3] === 0).length
      const sig = `${d.n}|${d.edges}|${d.onScreen}|${hidden}|${zeroSize}|${d.vp}|${d.phase}|${d.edgeIds}`
      const alarm =
        d.n > 0 && d.onScreen === 0 ? " *** ALL-OFFSCREEN-OR-HIDDEN ***" :
        hidden > 0 ? ` *** HIDDEN=${hidden} ***` :
        zeroSize > 0 ? ` *** ZERO-SIZE=${zeroSize} ***` : ""
      if (sig !== lastSig) {
        const detail = d.nodes.map((x) => `${x.i}:${x.v ? "V" : "H"}${x.d ? "" : ":nodisp"}@${x.r.join(",")}${x.sw ? ` ${x.sw}x${x.sh}` : ""}`).join(" | ")
        log(`n=${d.n} edges=${d.edges} onScreen=${d.onScreen} pane=${d.paneVis} vp=${d.vp} phase="${d.phase}"${alarm}`)
        log(`   edges: ${d.edgeIds || "-"}`)
        if (alarm || sig.split("|").slice(0, 2).join() !== (lastSig || "").split("|").slice(0, 2).join()) log(`   ${detail}`)
        lastSig = sig
      } else if (Date.now() - lastBeat > 3000) {
        log(`… n=${d.n} edges=${d.edges} onScreen=${d.onScreen} phase="${d.phase}"${alarm}`)
        lastBeat = Date.now()
      }
    }
  } catch (e) {
    log(`sample-error: ${String(e).slice(0, 200)}`)
  }
  await new Promise((r) => setTimeout(r, 150))
}
log("watch done")
chrome.kill()
process.exit(0)
