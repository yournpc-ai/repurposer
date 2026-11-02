// One authorized real render; verify delivery ownership, playback and hydration.
// usage: node chat_turn_real_render.mjs <project-url> <auth-json> <out-prefix>
import { spawn } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import http from "node:http"

const [PAGE_URL, AUTH_FILE, OUT] = process.argv.slice(2)
if (!PAGE_URL || !AUTH_FILE || !OUT) throw new Error("missing arguments")
const { token: TOKEN, user: USER } = JSON.parse(readFileSync(AUTH_FILE, "utf8"))
const RETRY_RUN_ID = process.env.RETRY_RUN_ID ?? null
const RETRY_OUTPUT_ID = process.env.RETRY_OUTPUT_ID ?? null
const PROMPT = RETRY_RUN_ID
  ? "请对刚才上传失败的 version 21 直接重试上传，不重新渲染、不修改内容、不新建版本、不生成图片或旁白。"
  : "请把当前保存并已完整展示的 version 21 直接再制作一次，仅复用现有版本，不修改内容、不新建版本、不重新设计、不生成图片或旁白。本轮已获一次真实渲染授权，预算上限 ¥10。"
const PORT = RETRY_RUN_ID ? 9252 : 9251
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", `--remote-debugging-port=${PORT}`,
  `--user-data-dir=/tmp/chat-real-render-${process.pid}`,
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
const report = {
  prompt: PROMPT, sendAttempts: 0, chatResponses: [], runEventUrls: [],
  delivery: null, viewer: null, refresh: null, consoleErrors: [], error: null,
}
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
  return {
    outputs,
    promptRows: [...(content?.querySelectorAll('[data-message-id]') ?? [])].filter((el) => (el.innerText || '').includes(${JSON.stringify(PROMPT)})).length,
    tail: (document.body.innerText || '').slice(-1800),
    scroll: viewport ? { top: viewport.scrollTop, remaining: viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight } : null,
  }
})()`)
const until = async (expression, timeout = 30000) => {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return
    await wait(400)
  }
  throw new Error(`Timed out: ${expression}`)
}
const screenshot = async (suffix) => {
  const shot = await send("Page.captureScreenshot", { format: "png" })
  writeFileSync(`${OUT}-${suffix}.png`, Buffer.from(shot.data, "base64"))
}
try {
  await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable")
  await send("Page.addScriptToEvaluateOnNewDocument", { source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)}); localStorage.setItem("repurposer-user", ${JSON.stringify(JSON.stringify(USER))}); localStorage.setItem("repurposer-theme", "dark");` })
  await send("Page.navigate", { url: PAGE_URL })
  await wait(8000)
  await evaluate(`[...document.querySelectorAll('button')].find((b) => /^(Skip|跳过)$/.test((b.textContent || '').trim()))?.click()`)
  await until(`document.querySelectorAll('[data-slot="message-scroller-viewport"]').length === 1`)
  report.before = await chatState()
  const baselineRuns = new Set(report.runEventUrls)
  const baselineRetryEvents = RETRY_RUN_ID
    ? report.runEventUrls.filter((url) => url.includes(`/runs/${RETRY_RUN_ID}/`)).length
    : 0
  const baselineOutputs = new Set(report.before.outputs.map((output) => output.id))
  await until(`document.querySelectorAll('[role="textbox"][data-slot="input-group-control"]').length === 1`)
  await evaluate(`document.querySelector('[role="textbox"][data-slot="input-group-control"]').focus()`)
  await send("Input.insertText", { text: PROMPT })
  await wait(200)
  const ready = await evaluate(`(() => { const e = document.querySelector('[role="textbox"][data-slot="input-group-control"]'); const b = [...document.querySelectorAll('button[aria-label]')].find((b) => /^(Send|发送)$/.test(b.getAttribute('aria-label') || '')); return !!(e?.innerText || e?.textContent || '').includes('version 21') && !!b && !b.disabled })()`)
  if (!ready) {
    const debug = await evaluate(`(() => { const e = document.querySelector('[role="textbox"][data-slot="input-group-control"]'); return { innerText: e?.innerText ?? null, textContent: e?.textContent ?? null, buttons: [...document.querySelectorAll('button[aria-label]')].map((b) => ({ label: b.getAttribute('aria-label'), disabled: b.disabled })).filter((b) => /Send|发送|Stop|停止/.test(b.label || '')) } })()`)
    throw new Error(`Composer not ready; prompt not sent: ${JSON.stringify(debug)}`)
  }
  report.sendAttempts += 1
  await evaluate(`[...document.querySelectorAll('button[aria-label]')].find((b) => /^(Send|发送)$/.test(b.getAttribute('aria-label') || '')).click()`)
  const start = Date.now()
  let runUrl = null
  while (!runUrl && Date.now() - start < 120000) {
    if (RETRY_RUN_ID) {
      const matches = report.runEventUrls.filter((url) => url.includes(`/runs/${RETRY_RUN_ID}/`))
      if (matches.length > baselineRetryEvents) runUrl = matches.at(-1)
    } else {
      runUrl = report.runEventUrls.find((url) => !baselineRuns.has(url)) ?? null
    }
    if (!runUrl) await wait(400)
  }
  if (!runUrl) throw new Error(RETRY_RUN_ID ? "Same-Run recovery did not resubscribe; no retry" : "Single Chat attempt did not start a new Run; no retry")
  report.recoveryActive = RETRY_RUN_ID ? await evaluate(`(() => ({
    stopVisible: [...document.querySelectorAll('button[aria-label]')].some((b) => /^(Stop|停止)$/.test(b.getAttribute('aria-label') || '') && !b.disabled),
    tail: (document.body.innerText || '').slice(-500),
  }))()`) : null
  if (RETRY_RUN_ID && !report.recoveryActive.stopVisible) throw new Error("Same-Run recovery did not restore Send=Stop")
  let delivery = null
  while (!delivery && Date.now() - start < 300000) {
    const current = await chatState()
    const fresh = RETRY_OUTPUT_ID
      ? current.outputs.find((output) => output.id === RETRY_OUTPUT_ID)
      : current.outputs.find((output) => output.id && !baselineOutputs.has(output.id))
    if (fresh?.messageId) delivery = { ...fresh, runUrl, state: current }
    else await wait(800)
  }
  if (!delivery) throw new Error(`Run ${runUrl} did not reveal a chat Output`)
  await wait(3000)
  const settled = await chatState()
  const current = settled.outputs.find((output) => output.id === delivery.id)
  report.delivery = {
    ...delivery, settledMessageId: current?.messageId ?? null,
    settledCardCount: settled.outputs.filter((output) => output.id === delivery.id).length,
    settledPromptRows: settled.promptRows, settledTail: settled.tail,
  }
  if (report.delivery.settledCardCount !== 1 || settled.promptRows !== 1) throw new Error("Live delivery or prompt duplicated")
  await screenshot("live-chat")
  await evaluate(`[...document.querySelectorAll('[data-slot="message-scroller-content"] [data-output-id]')].find((el) => el.getAttribute('data-output-id') === ${JSON.stringify(delivery.id)})?.click()`)
  await until(`!!document.querySelector('[role="dialog"]') && !!document.querySelector('[role="dialog"] video')`)
  await until(`(() => { const v = document.querySelector('[role="dialog"] video'); return !!v && v.readyState >= 2 && v.duration > 0 })()`, 60000)
  await evaluate(`(() => { const v = document.querySelector('[role="dialog"] video'); v.muted = true; return v.play() })()`)
  await wait(1800)
  report.viewer = await evaluate(`(() => { const v = document.querySelector('[role="dialog"] video'); return { src: v?.currentSrc ?? null, duration: v?.duration ?? null, currentTime: v?.currentTime ?? null, paused: v?.paused ?? null, readyState: v?.readyState ?? null, videoWidth: v?.videoWidth ?? null, videoHeight: v?.videoHeight ?? null } })()`)
  if (!(report.viewer.currentTime > 0) || report.viewer.paused) throw new Error("Delivered video did not actually play")
  await screenshot("viewer")
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 })
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 })
  await wait(500)
  await send("Page.reload", { ignoreCache: true })
  await wait(8000)
  await evaluate(`[...document.querySelectorAll('button')].find((b) => /^(Skip|跳过)$/.test((b.textContent || '').trim()))?.click()`)
  await until(`document.querySelectorAll('[data-slot="message-scroller-viewport"]').length === 1`)
  await until(`[...document.querySelectorAll('[data-output-id]')].some((el) => el.getAttribute('data-output-id') === ${JSON.stringify(delivery.id)})`)
  await wait(2500)
  const hydrated = await chatState()
  const hydratedCard = hydrated.outputs.find((output) => output.id === delivery.id)
  report.refresh = {
    cardCount: hydrated.outputs.filter((output) => output.id === delivery.id).length,
    messageId: hydratedCard?.messageId ?? null,
    promptRows: hydrated.promptRows,
    tail: hydrated.tail,
  }
  if (report.refresh.cardCount !== 1 || hydrated.promptRows !== 1) throw new Error("Hydrated delivery or prompt duplicated")
  await screenshot("hydrated-chat")
} catch (error) {
  report.error = error instanceof Error ? error.stack : String(error)
  try { report.failureState = await chatState() } catch {}
} finally {
  writeFileSync(`${OUT}.json`, JSON.stringify(report, null, 2))
  try { ws.close() } catch {}
  chrome.kill()
}
console.log(JSON.stringify({ sendAttempts: report.sendAttempts, delivery: report.delivery && { id: report.delivery.id, messageId: report.delivery.messageId, runUrl: report.delivery.runUrl }, viewer: report.viewer, refresh: report.refresh, consoleErrors: report.consoleErrors, error: report.error }, null, 2))
if (report.error) process.exitCode = 1
