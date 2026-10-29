// B-UI real browser journey; raw CDP, no dependencies.
import { spawn } from "node:child_process"
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs"
import http from "node:http"
import assert from "node:assert/strict"

const [PAGE_URL, TOKEN, USER_JSON, OUT] = process.argv.slice(2)
if (!PAGE_URL || !TOKEN || !USER_JSON || !OUT) throw new Error("usage: bui_browser.mjs <url> <jwt> <user-json> <out-dir>")
mkdirSync(OUT, { recursive: true })
const IDS = {
  v2: "28b03b27-5ecc-4b01-8a58-dbbf0ae70a34",
  v3: "260e3883-9fe0-4f99-b1ce-fd2211126682",
  v4: "d930fbc1-dfc0-4218-a8db-0e917648b30e",
}
const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
const PORT = 9232
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=/tmp/cdp-b-ui-${process.pid}`,
  "--window-size=1600,1000", "--force-device-scale-factor=1", "--no-first-run", "about:blank",
], { stdio: "ignore" })
process.on("exit", () => chrome.kill())
const getJson = (path) => new Promise((resolve, reject) => {
  http.get({ host: "127.0.0.1", port: PORT, path }, (res) => {
    let body = ""; res.on("data", (chunk) => { body += chunk }); res.on("end", () => resolve(JSON.parse(body)))
  }).on("error", reject)
})
let targets
for (let i = 0; i < 60; i++) {
  try { targets = await getJson("/json/list"); break } catch { await new Promise((r) => setTimeout(r, 250)) }
}
if (!targets) throw new Error("Chrome did not start")
const ws = new WebSocket(targets.find((target) => target.type === "page").webSocketDebuggerUrl)
await new Promise((resolve) => { ws.onopen = resolve })
let nextId = 0
const pending = new Map()
const downloadEvents = []
const networkEvents = []
const downloadRequestIds = new Set()
const downloadNetworkBytes = new Map()
const browserConsoleErrors = []
const browserLogEntries = []
let downloadCompleted = false
let suggestedDownloadName = null
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params }))
})
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.method === "Browser.downloadWillBegin") {
    suggestedDownloadName = message.params.suggestedFilename
    downloadEvents.push(message)
  }
  if (message.method === "Browser.downloadProgress") {
    downloadEvents.push(message)
    if (message.params.state === "completed") downloadCompleted = true
  }
  if (message.method === "Log.entryAdded") {
    const entry = message.params.entry
    if (entry.level === "error" || /CORS|fetch|ERR_/i.test(entry.text || "")) browserLogEntries.push(entry)
  }
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    browserConsoleErrors.push(message.params.args.map((arg) => arg.value || arg.description || "").join(" "))
  }
  if (["Network.responseReceived", "Network.loadingFailed"].includes(message.method)) {
    const url = message.params.response?.url || message.params.url || ""
    if (url.includes("/files/") || url.includes("volces.com") || url.startsWith("blob:") || downloadRequestIds.has(message.params.requestId)) {
      networkEvents.push(message)
      if (url.includes("?proxy=1")) downloadRequestIds.add(message.params.requestId)
    }
  }
  if (message.method === "Network.dataReceived" && downloadRequestIds.has(message.params.requestId)) {
    const id = message.params.requestId
    downloadNetworkBytes.set(id, (downloadNetworkBytes.get(id) || 0) + message.params.dataLength)
  }
  if (message.method === "Network.loadingFinished" && downloadRequestIds.has(message.params.requestId)) {
    networkEvents.push(message)
  }
  if (message.id && pending.has(message.id)) {
    const item = pending.get(message.id); pending.delete(message.id)
    if (message.error) item.reject(new Error(JSON.stringify(message.error))); else item.resolve(message.result)
  }
}
const evaluate = async (expression) => {
  let result
  try {
    result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  } catch (error) {
    throw new Error(`CDP evaluate failed for ${expression}: ${error.message}`)
  }
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const until = async (expression, timeout = 15000) => {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return
    await wait(500)
  }
  throw new Error(`Timed out: ${expression}`)
}
const shot = async (name) => {
  const result = await send("Page.captureScreenshot", { format: "png" })
  writeFileSync(`${OUT}/${name}.png`, Buffer.from(result.data, "base64"))
}
const clickOutput = async (id) => {
  const point = await evaluate(`(() => { const el = document.querySelector('[data-output-id="${id}"]'); if (!el) return null; el.scrollIntoView({block:'center'}); const r = el.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2} })()`)
  if (!point) throw new Error(`Missing Output card ${id}`)
  await send("Input.dispatchMouseEvent", { type: "mousePressed", ...point, button: "left", clickCount: 1 })
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", ...point, button: "left", clickCount: 1 })
}
const activeViewer = () => evaluate(`document.querySelector('[data-viewer-output-id][aria-current="true"]')?.getAttribute('data-viewer-output-id') || null`)
const covers = () => evaluate(`[...document.querySelectorAll('[data-output-id]')].map((el) => ({
  id: el.getAttribute('data-output-id'), text: el.parentElement?.innerText,
  width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height,
  image: el.querySelector('img')?.currentSrc || null,
}))`)

const report = { checks: {} }
try {
  await send("Runtime.enable"); await send("Page.enable"); await send("Network.enable"); await send("Log.enable")
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `localStorage.setItem("repurposer-token", ${JSON.stringify(TOKEN)});` +
      `localStorage.setItem("repurposer-user", ${JSON.stringify(USER_JSON)});` +
      `localStorage.setItem("repurposer-theme", "dark");`,
  })
  await send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: OUT, eventsEnabled: true })
  await send("Page.navigate", { url: PAGE_URL }); await wait(9000)
  await evaluate(`[...document.querySelectorAll('button')].find((b) => /^(Skip|跳过)$/.test((b.textContent || '').trim()))?.click()`)
  // A legitimately silent latest delivery uses the existing bounded Worked exit.
  await until(`document.querySelectorAll('[data-output-id]').length >= 3`, 75000)
  await until(`[...document.querySelectorAll('[data-output-id] img')].length >= 3`, 30000)
  report.covers = await covers()
  assert.deepEqual(report.covers.map((cover) => cover.id), [IDS.v2, IDS.v3, IDS.v4])
  assert(report.covers.every((cover) => cover.image))
  assert(report.covers[0].width >= 320 && report.covers[0].width <= 380)
  await shot("01-cover-cards-dark")

  await evaluate(`document.querySelector('[data-output-id="${IDS.v2}"]')?.scrollIntoView({block:'center'})`)
  report.scrollBefore = await evaluate(`(() => { let el = document.querySelector('[data-output-id="${IDS.v2}"]'); let p = el.parentElement; while (p && p.scrollHeight <= p.clientHeight) p = p.parentElement; window.__buiScrollHost = p; return p?.scrollTop ?? 0 })()`)
  await clickOutput(IDS.v2)
  await until(`document.querySelectorAll('[data-viewer-output-id]').length === 3`)
  assert.equal(await activeViewer(), IDS.v2)
  assert.equal(await evaluate(`document.querySelector('[role="dialog"]')?.innerText.includes('1 / 3')`), true)
  await shot("02-shared-viewer-v2-dark")

  await evaluate(`(async () => { const v = document.querySelector('[role="dialog"] video'); window.__buiPreviousVideo = v; await v.play(); return true })()`)
  await wait(1200)
  await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find((b) => b.getAttribute('aria-label') === 'Next output')?.click()`)
  await until(`document.querySelector('[data-viewer-output-id][aria-current="true"]')?.getAttribute('data-viewer-output-id') === '${IDS.v3}'`)
  report.checks.previousVideoStopped = await evaluate(`window.__buiPreviousVideo.paused || !window.__buiPreviousVideo.isConnected`)
  assert.equal(report.checks.previousVideoStopped, true)
  await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find((b) => b.getAttribute('aria-label') === 'Next output')?.click()`)
  await until(`document.querySelector('[data-viewer-output-id][aria-current="true"]')?.getAttribute('data-viewer-output-id') === '${IDS.v4}'`)
  assert.equal(await evaluate(`document.querySelector('[role="dialog"]')?.innerText.includes('3 / 3')`), true)
  await evaluate(`document.querySelector('[data-viewer-output-id="${IDS.v3}"]')?.click()`)
  await until(`document.querySelector('[data-viewer-output-id][aria-current="true"]')?.getAttribute('data-viewer-output-id') === '${IDS.v3}'`)
  report.checks.navigation = true

  const beforeDownloads = new Set(readdirSync(OUT))
  downloadCompleted = false
  suggestedDownloadName = null
  report.downloadButton = await evaluate(`(() => {
    window.__buiDownloadErrors = []
    window.__buiBlobStates = []
    const originalBlob = Response.prototype.blob
    Response.prototype.blob = function (...args) {
      if (!this.url.includes('?proxy=1')) return originalBlob.apply(this, args)
      window.__buiBlobStates.push('start')
      return originalBlob.apply(this, args).then((blob) => {
        window.__buiBlobStates.push('done:' + blob.size + ':' + blob.type)
        return blob
      }, (error) => {
        window.__buiBlobStates.push('error:' + String(error))
        throw error
      })
    }
    const originalCreateObjectURL = URL.createObjectURL
    URL.createObjectURL = function (blob) {
      window.__buiBlobStates.push('object-url:' + blob.size + ':' + blob.type)
      return originalCreateObjectURL.call(this, blob)
    }
    window.addEventListener('unhandledrejection', (event) => window.__buiDownloadErrors.push(String(event.reason)))
    window.addEventListener('error', (event) => window.__buiDownloadErrors.push(String(event.error || event.message)))
    const button = document.querySelector('[role="dialog"] button[title="Download"]')
    if (!button) return null
    const r = button.getBoundingClientRect()
    return { text: button.outerHTML, clicked: true, x: r.left + r.width / 2, y: r.top + r.height / 2 }
  })()`)
  assert(report.downloadButton?.clicked, "download button did not exist")
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: report.downloadButton.x, y: report.downloadButton.y, button: "left", clickCount: 1 })
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: report.downloadButton.x, y: report.downloadButton.y, button: "left", clickCount: 1 })
  let downloadName = null
  let downloadBytes = null
  for (let i = 0; i < 120 && !downloadBytes; i++) {
    await wait(1000)
    const candidate = readdirSync(OUT).find((name) => !beforeDownloads.has(name) && !name.endsWith('.crdownload'))
    if (candidate) {
      const bytes = readFileSync(`${OUT}/${candidate}`)
      if (bytes.length > 1000 && bytes.subarray(4, 8).toString() === 'ftyp') {
        downloadName = candidate
        downloadBytes = bytes
      }
    }
    if (downloadCompleted && suggestedDownloadName && !downloadName) {
      const bytes = readFileSync(`${OUT}/${suggestedDownloadName}`)
      if (bytes.length > 1000 && bytes.subarray(4, 8).toString() === 'ftyp') {
        downloadName = suggestedDownloadName
        downloadBytes = bytes
      }
    }
  }
  report.downloadEvents = downloadEvents
  report.networkEvents = networkEvents
  report.downloadErrors = await evaluate(`window.__buiDownloadErrors || []`)
  report.browserConsoleErrors = browserConsoleErrors
  report.browserLogEntries = browserLogEntries
  report.blobStates = await evaluate(`window.__buiBlobStates || []`)
  report.downloadNetworkBytes = Object.fromEntries(downloadNetworkBytes)
  report.downloaded = downloadName ? [downloadName] : []
  assert(downloadBytes, "download did not produce complete MP4 bytes")
  report.checks.downloadedMp4Bytes = true

  await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find((b) => (b.textContent || '').trim() === 'Reference')?.click()`)
  await wait(500)
  report.checks.exactMention = await evaluate(`document.querySelector('[data-mention-type="output"][data-mention-id="${IDS.v3}"]') !== null`)
  assert.equal(report.checks.exactMention, true)
  assert.equal(await evaluate(`document.querySelector('[role="dialog"]') === null`), true)

  await clickOutput(IDS.v3); await until(`document.querySelector('[role="dialog"] video') !== null`)
  await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find((b) => (b.textContent || '').trim() === 'Continue editing')?.click()`)
  await wait(500)
  report.checks.revisePrefill = await evaluate(`document.querySelector('[data-mention-type="output"][data-mention-id="${IDS.v3}"]') !== null && document.querySelector('[contenteditable="true"]')?.innerText.includes('Continue editing this output')`)
  assert.equal(report.checks.revisePrefill, true)

  await evaluate(`document.querySelector('[data-output-id="${IDS.v2}"]')?.scrollIntoView({block:'center'})`)
  report.scrollBeforeFinalOpen = await evaluate(`window.__buiScrollHost?.scrollTop ?? 0`)
  await clickOutput(IDS.v2); await until(`document.querySelector('[role="dialog"] video') !== null`)
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" })
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" })
  await wait(500)
  report.focusAfterClose = await evaluate(`document.activeElement?.getAttribute('data-output-id')`)
  report.scrollAfter = await evaluate(`window.__buiScrollHost?.scrollTop ?? 0`)
  assert.equal(report.focusAfterClose, IDS.v2)
  assert.equal(report.scrollAfter, report.scrollBeforeFinalOpen)
  report.checks.closeRestoresFocusAndScroll = true

  await send("Page.reload", { ignoreCache: true }); await wait(8000)
  await until(`document.querySelectorAll('[data-output-id]').length >= 3`, 75000)
  report.afterRefresh = await covers()
  assert.deepEqual(report.afterRefresh.map((cover) => cover.id), [IDS.v2, IDS.v3, IDS.v4])
  await clickOutput(IDS.v3); await until(`document.querySelectorAll('[data-viewer-output-id]').length === 3`)
  assert.equal(await activeViewer(), IDS.v3)
  report.checks.refreshStable = true

  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await send("Page.reload", { ignoreCache: true }); await wait(8000)
  await until(`document.querySelectorAll('[data-output-id]').length >= 2`)
  report.mobile = await evaluate(`({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, covers: [...document.querySelectorAll('[data-output-id]')].map((el) => ({ width: el.getBoundingClientRect().width, container: el.parentElement?.getBoundingClientRect().width })) })`)
  assert(report.mobile.scrollWidth <= report.mobile.width)
  assert(report.mobile.covers.every((cover) => cover.width <= 340))
  await shot("03-cover-cards-mobile-dark")
  await clickOutput(IDS.v2); await until(`document.querySelectorAll('[data-viewer-output-id]').length === 3`)
  report.mobileViewer = await evaluate(`({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth })`)
  assert(report.mobileViewer.scrollWidth <= report.mobileViewer.width)
  await shot("04-shared-viewer-mobile-dark")

  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] })
  await evaluate(`localStorage.setItem('repurposer-theme', 'light')`)
  await send("Page.reload", { ignoreCache: true }); await wait(8000)
  await until(`document.querySelectorAll('[data-output-id]').length >= 2`)
  report.checks.lightTheme = await evaluate(`!document.documentElement.classList.contains('dark')`)
  report.checks.reducedMotion = await evaluate(`getComputedStyle(document.querySelector('[data-output-id] span')).transitionDuration === '0s'`)
  assert.equal(report.checks.lightTheme, true)
  assert.equal(report.checks.reducedMotion, true)
  await shot("05-cover-cards-mobile-light-reduced-motion")
  await clickOutput(IDS.v2); await until(`document.querySelectorAll('[data-viewer-output-id]').length === 3`)
  report.lightViewer = await evaluate(`({ width: innerWidth, scrollWidth: document.documentElement.scrollWidth, dark: document.documentElement.classList.contains('dark') })`)
  assert(report.lightViewer.scrollWidth <= report.lightViewer.width)
  assert.equal(report.lightViewer.dark, false)
  await shot("06-shared-viewer-mobile-light-reduced-motion")
  writeFileSync(`${OUT}/browser-report.json`, JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
} catch (error) {
  await shot("failure")
  writeFileSync(`${OUT}/browser-report.json`, JSON.stringify({ ...report, error: String(error) }, null, 2))
  throw error
} finally {
  chrome.kill()
}
