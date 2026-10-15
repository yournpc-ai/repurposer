// One-shot theme screenshot: seeds auth + theme, opens a page, screenshots.
// Read-only. usage: node shot_theme.mjs <page-url> <jwt> <dark|light> <out.png>
import { spawn } from "node:child_process"
import { writeFileSync } from "node:fs"
import http from "node:http"

const [PAGE_URL, TOKEN, THEME, OUT] = process.argv.slice(2)
const USER_JSON = '{"id":"52037604-9321-4b70-9212-445ccf5ade60","email":"dev@local"}'
if (!PAGE_URL || !TOKEN || !THEME || !OUT) {
  console.error("usage: node shot_theme.mjs <page-url> <jwt> <dark|light> <out.png>")
  process.exit(1)
}

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9226
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=/tmp/cdp-shot-${THEME}`,
  "--window-size=1600,1000",
  "--force-device-scale-factor=2",
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
  new Promise((resolve) => {
    const id = ++msgId
    pending.set(id, { resolve })
    ws.send(JSON.stringify({ id, method, params }))
  })
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data)
  if (m.id && pending.has(m.id)) { pending.get(m.id).resolve(m.result ?? m.error); pending.delete(m.id) }
}

await send("Runtime.enable")
await send("Page.enable")
// Seed auth + theme BEFORE the app bundle runs (localStorage on about:blank
// hits the wrong origin — must ride addScriptToEvaluateOnNewDocument).
await send("Page.addScriptToEvaluateOnNewDocument", {
  source:
    `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});` +
    `localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});` +
    `localStorage.setItem("repurposer-theme", ${JSON.stringify(THEME)});`,
})
await send("Page.navigate", { url: PAGE_URL })
await new Promise((r) => setTimeout(r, 4500))
// Dismiss the composer tour if it rides (its seen-key is version-hashed —
// clicking Skip is the honest path).
await send("Runtime.evaluate", {
  expression: `[...document.querySelectorAll("button")].find((b) => /^(Skip|跳过)$/.test((b.textContent || "").trim()))?.click()`,
})
await new Promise((r) => setTimeout(r, 2500))

const shot = await send("Page.captureScreenshot", { format: "png" })
if (shot?.data) writeFileSync(OUT, Buffer.from(shot.data, "base64"))
console.log("screenshot →", OUT)
chrome.kill()
process.exit(0)
