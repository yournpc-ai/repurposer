// Read-only canvas watcher: drives headless Chrome via raw CDP (no deps).
// Opens the project page with a dev JWT, samples the React Flow DOM every
// 400ms, and logs every node-count/edge-count/zoom transition + console errors.
// Never clicks, types, or mutates — pure observation.
import { spawn } from "node:child_process"
import { writeFileSync, appendFileSync } from "node:fs"
import http from "node:http"

const PAGE_URL = process.argv[2]
const TOKEN = process.argv[3]
const USER_JSON = process.argv[4] ?? '{"id":"52037604-9321-4b70-9212-445ccf5ade60","email":"dev@local"}'
const DURATION_S = Number(process.argv[5] ?? 900)
const LOG = process.argv[6] ?? "/tmp/canvas_watch.log"

if (!PAGE_URL || !TOKEN) {
  console.error("usage: node cdp_watch.mjs <page-url> <jwt> [userJson] [durationS] [log]")
  process.exit(1)
}

const log = (msg) => {
  const line = `[${new Date().toISOString().slice(11, 19)}] ${msg}\n`
  appendFileSync(LOG, line)
  process.stdout.write(line)
}
writeFileSync(LOG, "")

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9223
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-watch-profile",
  "--window-size=1440,900",
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

// wait for chrome
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
    if (["error", "warning"].includes(m.params.type)) {
      log(`CONSOLE.${m.params.type}: ${text.slice(0, 400)}`)
    } else if (/vite|hmr|hot updat/i.test(text)) {
      log(`CONSOLE.${m.params.type}: ${text.slice(0, 300)}`)
    }
  } else if (m.method === "Runtime.exceptionThrown") {
    log(`PAGE-EXCEPTION: ${JSON.stringify(m.params.exceptionDetails).slice(0, 500)}`)
  }
}

await send("Runtime.enable")
await send("Page.enable")
// Seed auth BEFORE the app bundle runs.
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});
           localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});`,
})
await send("Page.navigate", { url: PAGE_URL })
log(`navigated ${PAGE_URL}`)

const SAMPLE = `(() => {
  const nodes = document.querySelectorAll(".react-flow__node").length
  const edges = document.querySelectorAll(".react-flow__edge").length
  const zoomEl = document.querySelector(".react-flow__panel button")
  const zoom = zoomEl ? zoomEl.textContent : "?"
  const rf = !!document.querySelector(".react-flow")
  const dots = !!document.querySelector(".react-flow__background")
  const rfNodes = document.querySelector(".react-flow__nodes")
  const nodesBox = rfNodes ? (getComputedStyle(rfNodes).opacity + "/" + getComputedStyle(rfNodes).visibility + "/" + (rfNodes.style.cssText||"").slice(0,60)) : "-"
  const canvasWrap = document.querySelector(".react-flow")?.closest("div.min-h-0")
  const wrapOp = canvasWrap ? getComputedStyle(canvasWrap).opacity : "?"
  const bodyText = document.body.innerText || ""
  const statusLine = (bodyText.match(/正在[^\\n]{0,24}/) || [""])[0].slice(0, 40)
  const loading = /loading|加载/i.test(bodyText.slice(0, 200))
  const sample = [...document.querySelectorAll(".react-flow__node")].slice(0, 8).map(n => {
    const el = n
    return (el.dataset.id || "?").slice(0, 8) + ":" + (el.style.transform || "").slice(0, 40) + ":" + (el.style.width || "")
  }).join(" | ")
  return JSON.stringify({ nodes, edges, zoom, rf, dots, wrapOp, nodesBox, loading, statusLine, sample })
})()`

const start = Date.now()
let last = null
while ((Date.now() - start) / 1000 < DURATION_S) {
  try {
    const res = await send("Runtime.evaluate", { expression: SAMPLE, returnByValue: true })
    const v = res?.result?.value
    if (v && v !== last) {
      const d = JSON.parse(v)
      log(`nodes=${d.nodes} edges=${d.edges} zoom=${d.zoom} rf=${d.rf} dots=${d.dots} :: ${d.sample}`)
      last = v
    }
  } catch (e) {
    log(`sample-error: ${String(e).slice(0, 200)}`)
  }
  await new Promise((r) => setTimeout(r, 400))
}
log("watch done")
chrome.kill()
process.exit(0)
