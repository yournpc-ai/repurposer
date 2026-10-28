// Real B-VI browser playback + hard-refresh evidence; raw CDP, no dependencies.
import { spawn } from "node:child_process"
import { writeFileSync } from "node:fs"
import http from "node:http"

const [PAGE_URL, TOKEN, USER_JSON, OUT_PREFIX] = process.argv.slice(2)
if (!PAGE_URL || !TOKEN || !USER_JSON || !OUT_PREFIX) {
  console.error("usage: node bvi_browser_refresh.mjs <url> <jwt> <user-json> <out-prefix>")
  process.exit(1)
}
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9231
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--user-data-dir=/tmp/cdp-bvi-narration",
  "--window-size=1600,1000",
  "--force-device-scale-factor=1",
  "--no-first-run",
  "--mute-audio",
  "about:blank",
], { stdio: "ignore" })
process.on("exit", () => chrome.kill())
const getJson = (path) => new Promise((resolve, reject) => {
  http.get({ host: "127.0.0.1", port: PORT, path }, (res) => {
    let buf = ""
    res.on("data", (c) => { buf += c })
    res.on("end", () => resolve(JSON.parse(buf)))
  }).on("error", reject)
})
let targets
for (let i = 0; i < 60; i++) {
  try { targets = await getJson("/json/list"); break } catch { await new Promise((r) => setTimeout(r, 250)) }
}
if (!targets) throw new Error("Chrome did not start")
const page = targets.find((t) => t.type === "page")
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((r) => { ws.onopen = r })
let nextId = 0
const pending = new Map()
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId
  pending.set(id, { resolve, reject })
  ws.send(JSON.stringify({ id, method, params }))
})
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const item = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) item.reject(new Error(JSON.stringify(message.error)))
    else item.resolve(message.result)
  }
}
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms))
await send("Runtime.enable")
await send("Page.enable")
await send("Page.addScriptToEvaluateOnNewDocument", {
  source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});` +
    `localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});` +
    `localStorage.setItem("repurposer-theme", "dark");`,
})
await send("Page.navigate", { url: PAGE_URL })
await wait(7000)
await evaluate(`[...document.querySelectorAll("button")].find((b) => /^(Skip|跳过)$/.test((b.textContent || "").trim()))?.click()`)
await wait(3000)
const sample = `(() => {
  const videos = [...document.querySelectorAll("video")].map((v) => ({
    src: v.currentSrc || v.src, readyState: v.readyState, duration: v.duration,
    currentTime: v.currentTime, paused: v.paused, error: v.error?.message || null,
  }))
  const text = document.body.innerText
  return {
    videos,
    storyboardVersions: [...text.matchAll(/Storyboard\\s+V(\\d+)/gi)].map((m) => Number(m[1])),
    hasManualCaption: text.includes("先看挑战。"),
    hasRevisedNarration: text.includes("答案在这里。"),
    hasOverlongNarration: text.includes("这句旁白现在被刻意写得非常长"),
    hasConflict: text.includes("旁白超过了已确认的镜头长度"),
  }
})()`
const before = await evaluate(sample)
await evaluate(`[...document.querySelectorAll("video")].at(-1)?.scrollIntoView({block:"center"})`)
await wait(1500)
const played = await evaluate(`(async () => {
  const v = [...document.querySelectorAll("video")].at(-1)
  if (!v) return { played: false, reason: "no video element" }
  try {
    await v.play()
    await new Promise((r) => setTimeout(r, 1800))
    const result = { played: v.currentTime > 0, currentTime: v.currentTime, readyState: v.readyState, duration: v.duration, src: v.currentSrc || v.src }
    v.pause()
    return result
  } catch (error) { return { played: false, reason: String(error), readyState: v.readyState, src: v.currentSrc || v.src } }
})()`)
const shotBefore = await send("Page.captureScreenshot", { format: "png" })
writeFileSync(`${OUT_PREFIX}-before-refresh.png`, Buffer.from(shotBefore.data, "base64"))
await send("Page.reload", { ignoreCache: true })
await wait(9000)
const after = await evaluate(sample)
const shotAfter = await send("Page.captureScreenshot", { format: "png" })
writeFileSync(`${OUT_PREFIX}-after-refresh.png`, Buffer.from(shotAfter.data, "base64"))
const report = { before, played, after }
writeFileSync(`${OUT_PREFIX}.json`, JSON.stringify(report, null, 2))
console.log(JSON.stringify(report, null, 2))
chrome.kill()
process.exit(0)
