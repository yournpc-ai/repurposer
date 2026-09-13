// One-shot canvas geometry probe: opens a project page headless at the
// user's window size, waits for settle, then dumps the xyflow viewport
// transform + every node's world position/measured size + a screenshot.
// Read-only. usage: node viewport_probe.mjs <page-url> <jwt> [userJson]
import { spawn } from "node:child_process"
import { writeFileSync } from "node:fs"
import http from "node:http"

const PAGE_URL = process.argv[2]
const TOKEN = process.argv[3]
const USER_JSON = process.argv[4] ?? '{"id":"52037604-9321-4b70-9212-445ccf5ade60","email":"dev@local"}'
if (!PAGE_URL || !TOKEN) {
  console.error("usage: node viewport_probe.mjs <page-url> <jwt> [userJson]")
  process.exit(1)
}

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9224
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-viewport-profile",
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
  else if (m.method === "Runtime.exceptionThrown") {
    console.log("PAGE-EXCEPTION:", JSON.stringify(m.params.exceptionDetails).slice(0, 400))
  }
}

await send("Runtime.enable")
await send("Page.enable")
// Seed auth BEFORE the app bundle runs (cdp_watch.mjs pattern — setting
// localStorage on about:blank hits the wrong origin).
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)}); localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});`,
})
await send("Page.navigate", { url: PAGE_URL })
await new Promise((r) => setTimeout(r, 6000))

const evalJs = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true })
  return r?.result?.value
}

const out = await evalJs(`(() => {
  const vp = document.querySelector(".react-flow__viewport")
  const nodes = [...document.querySelectorAll(".react-flow__node")].map((el) => ({
    id: el.getAttribute("data-id"),
    transform: el.style.transform,
    w: el.offsetWidth,
    h: el.offsetHeight,
    rect: (() => { const r = el.getBoundingClientRect(); return [Math.round(r.x), Math.round(r.y)] })(),
  }))
  const pane = document.querySelector(".react-flow")
  const pill = [...document.querySelectorAll("button")].find((b) => /%$/.test(b.textContent || ""))
  return {
    viewport: vp ? vp.style.transform : null,
    paneSize: pane ? [pane.clientWidth, pane.clientHeight] : null,
    zoomPill: pill ? pill.textContent : null,
    nodes,
  }
})()`)
console.log(JSON.stringify(out, null, 1))

const shot = await send("Page.captureScreenshot", { format: "png" })
if (shot?.data) writeFileSync("/tmp/viewport_probe.png", Buffer.from(shot.data, "base64"))
console.log("screenshot → /tmp/viewport_probe.png")
chrome.kill()
process.exit(0)
