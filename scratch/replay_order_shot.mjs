// Read-only replay verifier (F2/F4, incident 7886d879): opens the incident
// project with a dev JWT, waits for history replay to settle, then dumps the
// chat transcript's DOM order + the canvas card inventory and screenshots.
// Never clicks, types, or mutates — pure observation. Reuses cdp_watch.mjs's
// zero-dep CDP plumbing.
import { spawn } from "node:child_process"
import { writeFileSync, readFileSync } from "node:fs"
import http from "node:http"

const PAGE_URL = process.argv[2]
const TOKEN = readFileSync(process.argv[3], "utf8").trim()
const USER_JSON = '{"id":"52037604-9321-4b70-9212-445ccf5ade60","email":"xymzhs@gmail.com"}'
const SHOT = process.argv[4] ?? "/tmp/replay_order.png"

if (!PAGE_URL || !TOKEN) {
  console.error("usage: node replay_order_shot.mjs <page-url> <jwt-file> [shot]")
  process.exit(1)
}

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9224
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-replay-profile",
  "--window-size=1440,900",
  "--no-first-run",
  "--mute-audio",
  // The local stack must never ride the system proxy (Surge swallows
  // localhost/::1 — the known 拦截坑).
  "--proxy-server=direct://",
  "--proxy-bypass-list=*",
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
  if (m.id && pending.has(m.id)) { pending.get(m.id).resolve(m.result ?? m.error); pending.delete(m.id) }
}

await send("Runtime.enable")
await send("Page.enable")
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});
           localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});`,
})
await send("Page.navigate", { url: PAGE_URL })

// Wait for replay to settle: poll until the transcript contains the reply's
// signature text (or 25s elapse).
const SETTLED = `(() => {
  const t = document.body.innerText || ""
  return t.includes("分镜排好了") && t.includes("技术评估")
})()`
let settled = false
for (let i = 0; i < 50; i++) {
  const res = await send("Runtime.evaluate", { expression: SETTLED, returnByValue: true })
  if (res?.result?.value === true) { settled = true; break }
  await new Promise((r) => setTimeout(r, 500))
}
await new Promise((r) => setTimeout(r, 2000)) // let the typewriter finish

// Dump the dock's message-flow row order: every assistant/user block in DOM
// order with a short signature, plus the canvas card inventory.
const DUMP = `(() => {
  const out = { settledHint: ${settled}, rows: [], canvas: [] }
  // The dock scrollport: find the scrollable message column.
  const scrollers = [...document.querySelectorAll("div")].filter((el) =>
    el.scrollHeight > el.clientHeight + 40 && (el.innerText || "").includes("分镜排好了"))
  const root = scrollers.sort((a, b) => a.scrollHeight - b.scrollHeight)[0] || document.body
  const blocks = [...root.querySelectorAll("*")].filter((el) =>
    el.children.length === 0 && (el.innerText || "").trim().length > 4)
  const seen = []
  for (const el of blocks) {
    const txt = (el.innerText || "").trim().replace(/\\n/g, " ").slice(0, 42)
    if (txt && txt !== seen[seen.length - 1]) seen.push(txt)
  }
  out.rows = seen
  out.canvas = [...document.querySelectorAll(".react-flow__node")].map((n) =>
    (n.dataset.id || "?").slice(0, 8) + ":" + ((n.innerText || "").trim().replace(/\\n/g, " ").slice(0, 30) || "(media)"))
  return JSON.stringify(out)
})()`
const res = await send("Runtime.evaluate", { expression: DUMP, returnByValue: true })
console.log(res?.result?.value ?? JSON.stringify(res))

const shot = await send("Page.captureScreenshot", { format: "png" })
if (shot?.data) writeFileSync(SHOT, Buffer.from(shot.data, "base64"))
console.log("shot ->", SHOT)
chrome.kill()
process.exit(0)
