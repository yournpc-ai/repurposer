// Read-only hydrated-history evidence for the authorized live-scroll Run.
// usage: node chat_turn_history_read.mjs <project-url> <jwt> <user-json> <out-prefix> <output-id>
import { spawn } from "node:child_process"
import { writeFileSync } from "node:fs"
import http from "node:http"

const [PAGE_URL, TOKEN, USER_JSON, OUT, OUTPUT_ID] = process.argv.slice(2)
if (!PAGE_URL || !TOKEN || !USER_JSON || !OUT || !OUTPUT_ID) throw new Error("missing arguments")
const PORT = 9248
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=/tmp/chat-turn-history-${process.pid}`,
  "--window-size=1440,900", "--force-device-scale-factor=1",
  "--no-first-run", "--no-proxy-server", "--mute-audio", "about:blank",
], { stdio: "ignore" })
process.on("exit", () => chrome.kill())
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const getJson = (path) => new Promise((resolve, reject) => {
  http.get({ host: "127.0.0.1", port: PORT, path }, (res) => {
    let body = ""; res.on("data", (chunk) => { body += chunk }); res.on("end", () => resolve(JSON.parse(body)))
  }).on("error", reject)
})
let targets
for (let i = 0; i < 60; i++) {
  try { targets = await getJson("/json/list"); break } catch { await wait(250) }
}
if (!targets) throw new Error("Chrome did not start")
const ws = new WebSocket(targets.find((target) => target.type === "page").webSocketDebuggerUrl)
await new Promise((resolve) => { ws.onopen = resolve })
let nextId = 0
const pending = new Map()
const report = { chatPosts: 0, presentationAcks: [], consoleErrors: [] }
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params }))
})
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const item = pending.get(message.id); pending.delete(message.id)
    if (message.error) item.reject(new Error(JSON.stringify(message.error))); else item.resolve(message.result)
    return
  }
  if (message.method === "Network.requestWillBeSent" && message.params.request.method === "POST" && /\/api\/v1\/chat$/.test(message.params.request.url)) report.chatPosts += 1
  if (message.method === "Network.responseReceived" && message.params.response.url.includes("/video-presentation")) {
    report.presentationAcks.push({ url: message.params.response.url, status: message.params.response.status })
  }
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    report.consoleErrors.push(message.params.args.map((arg) => arg.value || arg.description || "").join(" ").slice(0, 500))
  }
}
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
try {
  await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable")
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});
             localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});
             localStorage.setItem("repurposer-theme", "dark");`,
  })
  await send("Page.navigate", { url: PAGE_URL })
  await wait(9000)
  await evaluate(`[...document.querySelectorAll('button')].find((b) => /^(Skip|跳过)$/.test((b.textContent || '').trim()))?.click()`)
  await wait(1500)
  report.hydrated = await evaluate(`(() => {
    const viewport = document.querySelector('[data-slot="message-scroller-viewport"]')
    const content = document.querySelector('[data-slot="message-scroller-content"]')
    const spacer = document.querySelector('[data-message-scroller-spacer]')
    const chatOutputs = [...content.querySelectorAll('[data-output-id]')].map((el) => el.getAttribute('data-output-id'))
    const items = [...content.querySelectorAll('[data-slot="message-scroller-item"]')]
    const last = items.at(-1)
    const cr = content.getBoundingClientRect()
    const lr = last?.getBoundingClientRect()
    return {
      outputId: ${JSON.stringify(OUTPUT_ID)},
      chatOutputCount: chatOutputs.filter((id) => id === ${JSON.stringify(OUTPUT_ID)}).length,
      chatOutputs,
      deliveryCount: items.filter((el) => (el.innerText || '').includes('成片已经渲染完成并交付到你手上') && (el.innerText || '').includes('version 21')).length,
      entranceNodes: content.querySelectorAll('[class*="animate-in"], [class*="slide-in-from-bottom"]').length,
      streamingTextNodes: content.querySelectorAll('[data-streaming="true"]').length,
      spacer: spacer ? { hidden: spacer.hidden, height: spacer.getBoundingClientRect().height, style: spacer.getAttribute('style') } : null,
      scroll: viewport ? { top: viewport.scrollTop, height: viewport.scrollHeight, clientHeight: viewport.clientHeight, remaining: viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight } : null,
      lastItemGap: last && lr ? cr.bottom - lr.bottom : null,
      tail: (document.body.innerText || '').slice(-2200),
    }
  })()`)
  const shot = await send("Page.captureScreenshot", { format: "png" })
  writeFileSync(`${OUT}.png`, Buffer.from(shot.data, "base64"))
} catch (error) {
  report.error = error instanceof Error ? error.stack : String(error)
} finally {
  writeFileSync(`${OUT}.json`, JSON.stringify(report, null, 2))
  try { ws.close() } catch {}
  chrome.kill()
}
console.log(JSON.stringify(report, null, 2))
if (report.error) process.exitCode = 1
