// Two authorized real deliveries; assert each Output stays on its own message.
// usage: node chat_turn_per_delivery.mjs <project-url> <auth-json> <out-prefix>
import { spawn } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import http from "node:http"

const [PAGE_URL, AUTH_FILE, OUT] = process.argv.slice(2)
if (!PAGE_URL || !AUTH_FILE || !OUT) throw new Error("missing arguments")
const { token: TOKEN, user: USER } = JSON.parse(readFileSync(AUTH_FILE, "utf8"))
const PROMPT = "请把当前保存并已完整展示的 version 21 直接再制作一次，仅复用现有版本，不修改内容、不新建版本、不重新设计、不生成图片或旁白。本轮已获一次真实渲染授权，预算上限 ¥10。"
const PORT = 9250
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=/tmp/chat-per-delivery-${process.pid}`,
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
const report = { prompt: PROMPT, sendAttempts: 0, chatResponses: [], runEventUrls: [], deliveries: [], consoleErrors: [], viewer: null, error: null }
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
  if (message.method === "Network.responseReceived") {
    const { url, status } = message.params.response
    if (/\/api\/v1\/chat$/.test(url)) report.chatResponses.push({ url, status })
    if (url.includes("/api/v1/runs/") && url.includes("/events")) report.runEventUrls.push(url)
  }
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    report.consoleErrors.push(message.params.args.map((arg) => arg.value || arg.description || "").join(" ").slice(0, 500))
  }
  if (message.method === "Runtime.exceptionThrown") report.consoleErrors.push(JSON.stringify(message.params.exceptionDetails).slice(0, 500))
}
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const chatState = () => evaluate(`(() => {
  const content = document.querySelector('[data-slot="message-scroller-content"]')
  const outputs = [...(content?.querySelectorAll('[data-output-id]') ?? [])].map((el) => {
    const item = el.closest('[data-message-id]')
    return { id: el.getAttribute('data-output-id'), messageId: item?.getAttribute('data-message-id') ?? null, text: (item?.innerText || '').trim().slice(0, 500) }
  })
  const viewport = document.querySelector('[data-slot="message-scroller-viewport"]')
  return { outputs, tail: (document.body.innerText || '').slice(-1600), scroll: viewport ? { top: viewport.scrollTop, remaining: viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight } : null }
})()`)
const until = async (expression, timeout = 30000) => {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return
    await wait(400)
  }
  throw new Error(`Timed out: ${expression}`)
}
const sendPrompt = async () => {
  await until(`document.querySelectorAll('[role="textbox"][data-slot="input-group-control"]').length === 1`)
  const baselineRuns = new Set(report.runEventUrls)
  const before = await chatState()
  const baselineOutputs = new Set(before.outputs.map((output) => output.id))
  await evaluate(`document.querySelector('[role="textbox"][data-slot="input-group-control"]').focus()`)
  await send("Input.insertText", { text: PROMPT })
  await wait(200)
  const ready = await evaluate(`(() => { const e = document.querySelector('[role="textbox"][data-slot="input-group-control"]'); const b = [...document.querySelectorAll('button[aria-label]')].find((b) => /^(Send|发送)$/.test(b.getAttribute('aria-label') || '')); return !!e?.innerText.includes('version 21') && !!b && !b.disabled })()`)
  if (!ready) throw new Error("Composer not ready; prompt not sent")
  report.sendAttempts += 1
  await evaluate(`[...document.querySelectorAll('button[aria-label]')].find((b) => /^(Send|发送)$/.test(b.getAttribute('aria-label') || '')).click()`)
  const start = Date.now()
  let runUrl = null
  while (!runUrl && Date.now() - start < 120000) {
    runUrl = report.runEventUrls.find((url) => !baselineRuns.has(url)) ?? null
    if (!runUrl) await wait(400)
  }
  if (!runUrl) throw new Error("Single Chat attempt did not start a new Run; no retry")
  let delivery = null
  while (!delivery && Date.now() - start < 240000) {
    const current = await chatState()
    const fresh = current.outputs.find((output) => output.id && !baselineOutputs.has(output.id))
    if (fresh?.messageId) delivery = { ...fresh, runUrl, state: current }
    else await wait(800)
  }
  if (!delivery) throw new Error(`New Run ${runUrl} did not reveal a chat Output`)
  await wait(2500)
  const settled = await chatState()
  const current = settled.outputs.find((output) => output.id === delivery.id)
  report.deliveries.push({ ...delivery, settledMessageId: current?.messageId ?? null, settledText: current?.text ?? null, settledTail: settled.tail })
  return delivery
}
try {
  await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable")
  await send("Page.addScriptToEvaluateOnNewDocument", { source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)}); localStorage.setItem("repurposer-user", ${JSON.stringify(JSON.stringify(USER))}); localStorage.setItem("repurposer-theme", "dark");` })
  await send("Page.navigate", { url: PAGE_URL })
  await wait(8000)
  await evaluate(`[...document.querySelectorAll('button')].find((b) => /^(Skip|跳过)$/.test((b.textContent || '').trim()))?.click()`)
  await until(`document.querySelectorAll('[data-slot="message-scroller-viewport"]').length === 1`)
  report.before = await chatState()
  const first = await sendPrompt()
  const second = await sendPrompt()
  if (first.id === second.id) throw new Error("Two Runs revealed the same Output id")
  if (first.messageId === second.messageId) throw new Error("Two deliveries share one message id")
  const finalState = await chatState()
  const oldCard = finalState.outputs.find((output) => output.id === first.id)
  const newCard = finalState.outputs.find((output) => output.id === second.id)
  if (oldCard?.messageId !== first.messageId || newCard?.messageId !== second.messageId) {
    throw new Error("An Output moved away from its original delivery message")
  }
  report.final = finalState
  const chatShot = await send("Page.captureScreenshot", { format: "png" })
  writeFileSync(`${OUT}-chat.png`, Buffer.from(chatShot.data, "base64"))
  await evaluate(`[...document.querySelectorAll('[data-slot="message-scroller-content"] [data-output-id]')].find((el) => el.getAttribute('data-output-id') === ${JSON.stringify(second.id)})?.click()`)
  await until(`document.querySelectorAll('[role="group"][aria-label]').length > 0 && !!document.querySelector('[role="dialog"]')`)
  const viewerState = () => evaluate(`(() => { const group = [...document.querySelectorAll('[role="group"]')].find((el) => el.querySelector('[data-active]')); const active = group?.querySelector('[data-active]'); const previous = [...document.querySelectorAll('button[aria-label]')].find((b) => /^(Previous output|上一个产物)$/.test(b.getAttribute('aria-label') || '')); return { total: group?.querySelectorAll('[data-index]').length ?? 0, activeIndex: active ? Number(active.getAttribute('data-index')) : null, previousDisabled: previous?.disabled ?? null } })()`)
  const opened = await viewerState()
  await evaluate(`[...document.querySelectorAll('button[aria-label]')].find((b) => /^(Previous output|上一个产物)$/.test(b.getAttribute('aria-label') || ''))?.click()`)
  await wait(700)
  const previous = await viewerState()
  report.viewer = { opened, previous }
  if (opened.total < 2 || previous.activeIndex !== opened.activeIndex - 1) throw new Error("Shared viewer did not navigate to the preceding Output")
  const viewerShot = await send("Page.captureScreenshot", { format: "png" })
  writeFileSync(`${OUT}-viewer.png`, Buffer.from(viewerShot.data, "base64"))
} catch (error) {
  report.error = error instanceof Error ? error.stack : String(error)
  try { report.failureState = await chatState() } catch {}
} finally {
  writeFileSync(`${OUT}.json`, JSON.stringify(report, null, 2))
  try { ws.close() } catch {}
  chrome.kill()
}
console.log(JSON.stringify({ sendAttempts: report.sendAttempts, deliveries: report.deliveries.map((d) => ({ id: d.id, messageId: d.messageId, runUrl: d.runUrl })), viewer: report.viewer, consoleErrors: report.consoleErrors, error: report.error }, null, 2))
if (report.error) process.exitCode = 1
