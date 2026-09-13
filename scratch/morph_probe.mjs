// Morph-path driver (2026-09-13 centering walkthrough): open a fresh
// project (full-form chat world), type the caption prompt in the dock,
// send it, then sample the canvas through the full→panel morph beat —
// zoom / node count / canvas opacity transitions — and end with a
// geometry dump + screenshot. Read-only after the send.
// usage: node morph_probe.mjs <page-url> <jwt>
import { spawn } from "node:child_process"
import { writeFileSync, appendFileSync } from "node:fs"
import http from "node:http"

const PAGE_URL = process.argv[2]
const TOKEN = process.argv[3]
const USER_JSON = '{"id":"52037604-9321-4b70-9212-445ccf5ade60","email":"dev@local"}'
const PROMPT = "Caption my video in Chinese and French — Chinese as bilingual subtitles."
const LOG = "/tmp/morph_probe.log"
if (!PAGE_URL || !TOKEN) {
  console.error("usage: node morph_probe.mjs <page-url> <jwt>")
  process.exit(1)
}

const log = (m) => {
  const line = `[${new Date().toISOString().slice(11, 19)}] ${m}\n`
  appendFileSync(LOG, line)
  process.stdout.write(line)
}
writeFileSync(LOG, "")

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9225
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-morph-profile",
  "--window-size=1993,1255",
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
  try { targets = await getJson("/json/list"); break } catch { await new Promise((r) => setTimeout(r, 200)) }
}
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
  if (m.id && pending.has(m.id)) { pending.get(m.id).resolve(m.result ?? m.error); pending.delete(m.id) }
  else if (m.method === "Runtime.exceptionThrown") log(`PAGE-EXCEPTION: ${JSON.stringify(m.params.exceptionDetails).slice(0, 400)}`)
}

const evalJs = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true }))?.result?.value

await send("Runtime.enable")
await send("Page.enable")
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)}); localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});`,
})
await send("Page.navigate", { url: PAGE_URL })
log(`navigated ${PAGE_URL}`)

// Wait for the composer editor.
let ready = false
for (let i = 0; i < 40; i++) {
  await new Promise((r) => setTimeout(r, 500))
  ready = await evalJs(`!!document.querySelector('[contenteditable="true"]')`)
  if (ready) break
}
if (!ready) { log("composer never appeared"); process.exit(1) }
log("composer ready")

await evalJs(`(() => { const el = document.querySelector('[contenteditable="true"]'); el.focus(); return true })()`)
await send("Input.insertText", { text: PROMPT })
await new Promise((r) => setTimeout(r, 400))
const clicked = await evalJs(`(() => {
  const btns = [...document.querySelectorAll("button")]
  const send = btns.find((b) => /^(send|发送)$/i.test((b.getAttribute("aria-label") || "").trim()))
  if (!send) return "no-send-button"
  send.click()
  return "clicked"
})()`)
log(`send: ${clicked}`)

const SAMPLE = `(() => {
  const nodes = document.querySelectorAll(".react-flow__node").length
  const zoomEl = document.querySelector(".react-flow__panel button")
  const zoom = zoomEl ? zoomEl.textContent : "?"
  const vp = document.querySelector(".react-flow__viewport")
  const wrap = document.querySelector(".react-flow")?.closest("div.min-h-0")
  const op = wrap ? getComputedStyle(wrap).opacity : "?"
  return JSON.stringify({ nodes, zoom, vp: vp ? vp.style.transform : null, op })
})()`

const start = Date.now()
let last = null
while ((Date.now() - start) / 1000 < 150) {
  const v = await evalJs(SAMPLE)
  if (v && v !== last) { log(v); last = v }
  await new Promise((r) => setTimeout(r, 500))
  const d = v ? JSON.parse(v) : null
  // Settled: graph visible (op 1), ≥4 nodes, then give 6s and stop.
  if (d && d.op === "1" && d.nodes >= 4 && (Date.now() - start) / 1000 > 20) {
    await new Promise((r) => setTimeout(r, 6000))
    break
  }
}

const geo = await evalJs(`(() => {
  const vp = document.querySelector(".react-flow__viewport")
  return JSON.stringify({
    viewport: vp ? vp.style.transform : null,
    nodes: [...document.querySelectorAll(".react-flow__node")].map((el) => ({
      id: (el.getAttribute("data-id") || "").slice(0, 8),
      transform: el.style.transform,
      w: el.offsetWidth, h: el.offsetHeight,
      rect: (() => { const r = el.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y)] })(),
    })),
  })
})()`)
log(`GEO ${geo}`)
const shot = await send("Page.captureScreenshot", { format: "png" })
if (shot?.data) writeFileSync("/tmp/morph_probe.png", Buffer.from(shot.data, "base64"))
log("screenshot → /tmp/morph_probe.png")
process.exit(0)
