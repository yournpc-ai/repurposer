// One authorized normal Chat -> render journey with real viewport geometry.
// usage: node chat_turn_live_scroll.mjs <project-url> <jwt> <user-json> <out-prefix>
import { spawn } from "node:child_process"
import { writeFileSync } from "node:fs"
import http from "node:http"

const [PAGE_URL, TOKEN, USER_JSON, OUT] = process.argv.slice(2)
if (!PAGE_URL || !TOKEN || !USER_JSON || !OUT) {
  throw new Error("usage: chat_turn_live_scroll.mjs <project-url> <jwt> <user-json> <out-prefix>")
}
const PROMPT = "请把当前保存并已完整展示的 version 21 直接再制作一次，仅复用现有版本，不修改内容、不新建版本、不重新设计、不生成图片或旁白。本轮已获一次真实渲染授权，预算上限 ¥10。"
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9247
const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=/tmp/chat-turn-live-scroll-${process.pid}`,
  "--window-size=1440,900",
  "--force-device-scale-factor=1",
  "--no-first-run",
  "--no-proxy-server",
  "--mute-audio",
  "about:blank",
], { stdio: "ignore" })
process.on("exit", () => chrome.kill())

const report = {
  prompt: PROMPT,
  sendAttempts: 0,
  chatResponses: [],
  presentationAcks: [],
  runEventUrls: [],
  consoleErrors: [],
  phaseA: null,
  phaseB: null,
  final: null,
  error: null,
}
const pending = new Map()
let nextId = 0
let ws
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const getJson = (path) => new Promise((resolve, reject) => {
  http.get({ host: "127.0.0.1", port: PORT, path }, (res) => {
    let body = ""
    res.on("data", (chunk) => { body += chunk })
    res.on("end", () => resolve(JSON.parse(body)))
  }).on("error", reject)
})
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId
  pending.set(id, { resolve, reject })
  ws.send(JSON.stringify({ id, method, params }))
})
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const until = async (expression, timeout = 30000) => {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return
    await wait(400)
  }
  throw new Error(`Timed out: ${expression}`)
}
const clickPoint = async (point) => {
  await send("Input.dispatchMouseEvent", { type: "mousePressed", ...point, button: "left", clickCount: 1 })
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", ...point, button: "left", clickCount: 1 })
}
const wheelUp = async (delta = -1400) => {
  const point = await evaluate(`(() => {
    const v = document.querySelector('[data-slot="message-scroller-viewport"]')
    if (!v) return null
    const r = v.getBoundingClientRect()
    return { x: r.left + r.width / 2, y: r.top + Math.min(r.height / 2, 300) }
  })()`)
  if (!point) throw new Error("Message viewport missing")
  await send("Input.dispatchMouseEvent", { type: "mouseWheel", ...point, deltaX: 0, deltaY: delta })
  await wait(500)
}
const sample = async (label) => evaluate(`(() => {
  const v = document.querySelector('[data-slot="message-scroller-viewport"]')
  const c = document.querySelector('[data-slot="message-scroller-content"]')
  const anchor = window.__liveScrollAnchor
  const ar = anchor?.isConnected ? anchor.getBoundingClientRect() : null
  const vr = v?.getBoundingClientRect()
  return {
    label: ${JSON.stringify(label)},
    at: new Date().toISOString(),
    scrollTop: v?.scrollTop ?? null,
    scrollHeight: v?.scrollHeight ?? null,
    clientHeight: v?.clientHeight ?? null,
    remaining: v ? v.scrollHeight - v.scrollTop - v.clientHeight : null,
    anchor: anchor ? {
      connected: anchor.isConnected,
      messageId: anchor.closest('[data-message-id]')?.getAttribute('data-message-id') ?? null,
      text: (anchor.innerText || '').trim().slice(0, 100),
      top: ar?.top ?? null,
      viewportTop: vr?.top ?? null,
    } : null,
    contentHeight: c?.getBoundingClientRect().height ?? null,
    runText: [...document.querySelectorAll('[data-slot="message-scroller-item"]')]
      .map((el) => (el.innerText || '').trim())
      .filter((text) => /渲染排队请求|交付准入|保存版与执行输入校验|正在整理制作结果|Render queue request|Delivery admission|Saved version and input validation|Gathering the results/.test(text))
      .at(-1)?.slice(0, 1600) ?? '',
    outputs: [...document.querySelectorAll('[data-slot="message-scroller-content"] [data-output-id]')].map((el) => el.getAttribute('data-output-id')),
    tail: (document.body.innerText || '').slice(-1800),
  }
})()`)
const chooseAnchor = async () => evaluate(`(() => {
  const v = document.querySelector('[data-slot="message-scroller-viewport"]')
  if (!v) return false
  const vr = v.getBoundingClientRect()
  const edges = [...v.querySelectorAll('[data-message-scroller-reading-edge]')]
  const edge = edges.find((el) => {
    const r = el.getBoundingClientRect()
    return r.height > 0 && r.top >= vr.top + 4 && r.bottom <= vr.bottom - 4 && (el.innerText || '').trim().length > 20
  })
  if (!edge) return false
  window.__liveScrollAnchor = edge
  return true
})()`)
const captureSamples = async (target, label, durationMs) => {
  const start = Date.now()
  while (Date.now() - start < durationMs) {
    target.push(await sample(label))
    await wait(700)
  }
}

try {
  let targets
  for (let i = 0; i < 60; i++) {
    try { targets = await getJson("/json/list"); break } catch { await wait(250) }
  }
  if (!targets) throw new Error("Chrome did not start")
  ws = new WebSocket(targets.find((target) => target.type === "page").webSocketDebuggerUrl)
  await new Promise((resolve) => { ws.onopen = resolve })
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    if (message.id && pending.has(message.id)) {
      const item = pending.get(message.id)
      pending.delete(message.id)
      if (message.error) item.reject(new Error(JSON.stringify(message.error)))
      else item.resolve(message.result)
      return
    }
    if (message.method === "Network.responseReceived") {
      const { url, status } = message.params.response
      if (/\/api\/v1\/chat$/.test(url)) report.chatResponses.push({ url, status })
      if (url.includes("/video-presentation")) report.presentationAcks.push({ url, status })
      if (url.includes("/api/v1/runs/") && url.includes("/events")) report.runEventUrls.push(url)
    }
    if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
      report.consoleErrors.push(message.params.args.map((arg) => arg.value || arg.description || "").join(" ").slice(0, 500))
    }
    if (message.method === "Runtime.exceptionThrown") {
      report.consoleErrors.push(JSON.stringify(message.params.exceptionDetails).slice(0, 500))
    }
  }

  await send("Runtime.enable")
  await send("Page.enable")
  await send("Network.enable")
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});
             localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});
             localStorage.setItem("repurposer-theme", "dark");`,
  })
  await send("Page.navigate", { url: PAGE_URL })
  await wait(8000)
  await evaluate(`[...document.querySelectorAll('button')].find((b) => /^(Skip|跳过)$/.test((b.textContent || '').trim()))?.click()`)
  await until(`document.querySelectorAll('[data-slot="message-scroller-viewport"]').length === 1`)
  report.before = await sample("before-send")
  const baselineRunEventUrls = new Set(report.runEventUrls)
  const editorCount = await evaluate(`document.querySelectorAll('[role="textbox"][data-slot="input-group-control"]').length`)
  if (editorCount !== 1) throw new Error(`Expected one composer, found ${editorCount}; nothing sent`)
  await evaluate(`document.querySelector('[role="textbox"][data-slot="input-group-control"]').focus()`)
  await send("Input.insertText", { text: PROMPT })
  await wait(200)
  const ready = await evaluate(`(() => {
    const editor = document.querySelector('[role="textbox"][data-slot="input-group-control"]')
    const button = [...document.querySelectorAll('button[aria-label]')].find((b) => /^(Send|发送)$/.test(b.getAttribute('aria-label') || ''))
    return !!editor?.innerText.includes('version 21') && !!button && !button.disabled
  })()`)
  if (!ready) throw new Error("Composer did not become send-ready; nothing sent")
  report.sendAttempts += 1
  await evaluate(`[...document.querySelectorAll('button[aria-label]')].find((b) => /^(Send|发送)$/.test(b.getAttribute('aria-label') || '')).click()`)
  await until(`document.body.innerText.includes(${JSON.stringify(PROMPT.slice(0, 30))})`, 15000)
  const runWaitStart = Date.now()
  const hasNewRun = () => report.runEventUrls.some((url) => !baselineRunEventUrls.has(url))
  while (!hasNewRun() && Date.now() - runWaitStart < 120000) {
    await wait(400)
  }
  if (!hasNewRun()) {
    throw new Error("The single Chat attempt did not start a Run; no retry sent")
  }
  await wait(500)

  // Phase A: leave the bottom during real production, keep reading through
  // updates, exercise a real disclosure, then explicitly restore following.
  const phaseA = { initial: null, afterWheel: null, beforeReturn: [], toggle: null, returned: null, following: [] }
  report.phaseA = phaseA
  phaseA.initial = await sample("phase-a-live-initial")
  await wheelUp()
  if (!await chooseAnchor()) {
    await wheelUp(-1800)
    if (!await chooseAnchor()) throw new Error("No real reading anchor after wheel-up")
  }
  phaseA.afterWheel = await sample("phase-a-after-wheel")
  await captureSamples(phaseA.beforeReturn, "phase-a-reading", 7000)

  const disclosure = await evaluate(`(() => {
    const v = document.querySelector('[data-slot="message-scroller-viewport"]')
    const vr = v.getBoundingClientRect()
    const el = [...v.querySelectorAll('div[role="button"][aria-expanded]')].find((candidate) => {
      const r = candidate.getBoundingClientRect()
      return r.height > 0 && r.top >= vr.top && r.bottom <= vr.bottom && /工作了|项操作|Worked/.test(candidate.innerText || '')
    })
    if (!el) return null
    window.__liveDisclosure = el
    const r = el.getBoundingClientRect()
    return { x: r.left + Math.min(r.width / 2, 100), y: r.top + r.height / 2, top: r.top, expanded: el.getAttribute('aria-expanded') }
  })()`)
  if (disclosure) {
    const before = await sample("disclosure-before")
    await clickPoint({ x: disclosure.x, y: disclosure.y })
    await wait(450)
    const afterOpen = await sample("disclosure-after-open")
    const openTop = await evaluate(`window.__liveDisclosure?.getBoundingClientRect().top ?? null`)
    await clickPoint({ x: disclosure.x, y: openTop ?? disclosure.y })
    await wait(450)
    const afterClose = await sample("disclosure-after-close")
    phaseA.toggle = { disclosure, before, afterOpen, afterClose }
  }

  await evaluate(`document.querySelector('[data-slot="message-scroller-button"][data-direction="end"]')?.click()`)
  await wait(1400)
  phaseA.returned = await sample("phase-a-explicit-return")
  await captureSamples(phaseA.following, "phase-a-following", 3000)

  // Phase B: leave again before terminal and remain anchored through Run
  // terminal, delivery prose, Output admission and live -> Worked.
  const phaseB = { afterWheel: null, samples: [], terminalObserved: false }
  report.phaseB = phaseB
  await wheelUp(-1500)
  if (!await chooseAnchor()) {
    await wheelUp(-1800)
    if (!await chooseAnchor()) throw new Error("No phase-B reading anchor")
  }
  phaseB.afterWheel = await sample("phase-b-after-wheel")
  const start = Date.now()
  const baselineOutputs = new Set(report.before.outputs)
  while (Date.now() - start < 180000) {
    const current = await sample("phase-b-reading")
    phaseB.samples.push(current)
    const newOutput = current.outputs.some((id) => id && !baselineOutputs.has(id))
    const deliveryVisible = /成片.*(完成|交付)|渲染完成并交付/.test(current.tail)
    if (newOutput && deliveryVisible) {
      phaseB.terminalObserved = true
      break
    }
    if (/本次.*失败|运行失败|没能把成片/.test(current.tail) && current.runText.includes('工作了')) break
    await wait(800)
  }
  phaseB.finalReading = await sample("phase-b-final-reading")
  await evaluate(`document.querySelector('[data-slot="message-scroller-button"][data-direction="end"]')?.click()`)
  await wait(1400)
  report.final = await sample("final-explicit-return")
  const shot = await send("Page.captureScreenshot", { format: "png" })
  writeFileSync(`${OUT}.png`, Buffer.from(shot.data, "base64"))
} catch (error) {
  report.error = error instanceof Error ? error.stack : String(error)
  try { report.failureState = await sample("failure-state") } catch {}
} finally {
  writeFileSync(`${OUT}.json`, JSON.stringify(report, null, 2))
  try { ws?.close() } catch {}
  chrome.kill()
}

if (report.error) {
  console.error(report.error)
  process.exitCode = 1
} else {
  console.log(JSON.stringify({
    sendAttempts: report.sendAttempts,
    runEventUrls: report.runEventUrls,
    phaseA: report.phaseA,
    phaseBTerminalObserved: report.phaseB.terminalObserved,
    final: report.final,
    consoleErrors: report.consoleErrors,
  }, null, 2))
}
