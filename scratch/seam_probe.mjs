// Computed-style probe: why the sidebar seam doesn't render.
// usage: node seam_probe.mjs <page-url> <jwt>
import { spawn } from "node:child_process"
import http from "node:http"

const [PAGE_URL, TOKEN] = process.argv.slice(2)
const USER_JSON = '{"id":"52037604-9321-4b70-9212-445ccf5ade60","email":"dev@local"}'
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9227
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-seam-profile",
  "--window-size=1600,1000", "--no-first-run", "--mute-audio", "about:blank",
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
const send = (m, p = {}) => new Promise((res) => { const id = ++msgId; pending.set(id, { res }); ws.send(JSON.stringify({ id, method: m, params: p })) })
ws.onmessage = (ev) => { const m = JSON.parse(ev.data); if (m.id && pending.has(m.id)) { pending.get(m.id).res(m.result ?? m.error); pending.delete(m.id) } }

await send("Runtime.enable")
await send("Page.enable")
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)}); localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)}); localStorage.setItem("repurposer-theme", "dark");`,
})
await send("Page.navigate", { url: PAGE_URL })
await new Promise((r) => setTimeout(r, 6000))

const r = await send("Runtime.evaluate", { expression: `(() => {
  const el = document.querySelector('[data-slot="sidebar-container"]')
  if (!el) return "no container"
  const cs = getComputedStyle(el)
  return JSON.stringify({
    cls: el.className.slice(0, 200),
    brw: cs.borderRightWidth,
    brc: cs.borderRightColor,
    brs: cs.borderRightStyle,
    w: cs.width,
  }, null, 1)
})()`, returnByValue: true })
console.log(r?.result?.value ?? JSON.stringify(r))
chrome.kill()
process.exit(0)
