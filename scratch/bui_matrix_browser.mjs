// B-UI remaining real-delivery matrix; raw CDP, no dependencies or production.
import { spawn } from "node:child_process"
import { mkdirSync, writeFileSync } from "node:fs"
import http from "node:http"
import assert from "node:assert/strict"

const [TOKENS_JSON, OUT] = process.argv.slice(2)
if (!TOKENS_JSON || !OUT) throw new Error("usage: bui_matrix_browser.mjs <tokens-json> <out-dir>")
const TOKENS = JSON.parse(TOKENS_JSON)
mkdirSync(OUT, { recursive: true })
const PORT = 9234
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=/tmp/cdp-b-ui-matrix-${process.pid}`,
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
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++nextId; pending.set(id, { resolve, reject }); ws.send(JSON.stringify({ id, method, params }))
})
ws.onmessage = (event) => {
  const message = JSON.parse(event.data)
  if (message.id && pending.has(message.id)) {
    const item = pending.get(message.id); pending.delete(message.id)
    if (message.error) item.reject(new Error(JSON.stringify(message.error))); else item.resolve(message.result)
  }
}
const evaluate = async (expression) => {
  const result = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const until = async (expression, timeout = 30000) => {
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
const openOutput = async (id) => {
  const point = await evaluate(`(() => { const el = document.querySelector('[data-output-id="${id}"]'); if (!el) return null; el.scrollIntoView({block:'center'}); const r=el.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2} })()`)
  if (!point) throw new Error(`Missing Output ${id}`)
  await send("Input.dispatchMouseEvent", { type: "mousePressed", ...point, button: "left", clickCount: 1 })
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", ...point, button: "left", clickCount: 1 })
  await until(`document.querySelector('[role="dialog"]') !== null`)
}
const scenarios = [
  {
    name: "same-version", project: "e6f80236-c5d1-4b5d-94b6-c90a7fb8a7ee", owner: "329ec37c-b4bf-44be-ac1f-2a46cf5ff826",
    ids: ["a6d51bcb-556a-4c93-8f20-5df61e63f0b3", "5204fc7a-0295-491a-b634-f2ea6e3492d2", "dcaa6322-8324-4e9b-b92d-081f186c8461", "3cb5e638-9e99-42e3-bf14-6e4dbc3ca468"],
  },
  { name: "portrait", project: "e0736859-50fe-400d-99f9-11ccb8cd07a8", owner: "0740c945-9cf2-43fb-8786-9d1ca4f7d05a", ids: ["2c45efe4-e2e3-4f10-ad69-13e8dcd00c7a"] },
  { name: "text", project: "5a15e19e-28a2-4dc8-9537-b311fca9cc37", owner: "83ff5191-e75e-4a02-acb3-4342f4179ba4", ids: ["9ad995a2-9ea7-44b0-b31c-6cee9b491f28"] },
  { name: "image", project: "e6dfd73f-597e-4441-b500-c195f7b9f80e", owner: "7fcfd54a-7ac8-46b1-9e8a-939896a75fd7", ids: ["bdf87c61-caee-4453-8fce-944d3a7624c6"] },
]
const report = {}
try {
  await send("Runtime.enable"); await send("Page.enable")
  for (const scenario of scenarios) {
    const token = TOKENS[scenario.owner]
    if (!token) throw new Error(`Missing token for ${scenario.owner}`)
    await send("Page.addScriptToEvaluateOnNewDocument", {
      source: `localStorage.setItem("repurposer-token", ${JSON.stringify(token)}); localStorage.setItem("repurposer-user", ${JSON.stringify(JSON.stringify({ id: scenario.owner, email: "local-matrix@example.com", name: "Local Matrix" }))}); localStorage.setItem("repurposer-theme", "dark");`,
    })
    await send("Page.navigate", { url: `http://localhost:3000/projects/${scenario.project}` })
    await wait(7000)
    await evaluate(`[...document.querySelectorAll('button')].find((b) => /^(Skip|跳过)$/.test((b.textContent || '').trim()))?.click()`)
    await until(`document.querySelectorAll('[data-output-id]').length >= ${scenario.ids.length}`, 60000)
    const cards = await evaluate(`[...document.querySelectorAll('[data-output-id]')].map((el) => ({ id: el.getAttribute('data-output-id'), text: el.parentElement?.textContent || '', width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height }))`)
    assert.deepEqual(cards.map((card) => card.id), scenario.ids)
    report[scenario.name] = { cards }
    if (scenario.name === "same-version") {
      const versions = cards.slice(1).map((card) => card.text.match(/v\d+/)?.[0])
      assert(versions.every(Boolean))
      assert.equal(new Set(versions).size, 1)
      await openOutput(scenario.ids[1])
      await until(`document.querySelectorAll('[data-viewer-output-id]').length === 4`)
      assert(await evaluate(`document.querySelector('[role="dialog"]')?.innerText.includes('2 / 4')`))
      await evaluate(`[...document.querySelectorAll('[role="dialog"] button')].find((b) => b.getAttribute('aria-label') === 'Next output')?.click()`)
      await until(`document.querySelector('[data-viewer-output-id][aria-current="true"]')?.getAttribute('data-viewer-output-id') === '${scenario.ids[2]}'`)
      report[scenario.name].sameVersionIndependentOutputs = true
      await shot("07-same-version-outputs")
    } else if (scenario.name === "portrait") {
      assert(Math.abs(cards[0].height - 288) < 1)
      assert(Math.abs(cards[0].width / cards[0].height - 9 / 16) < 0.02)
      await openOutput(scenario.ids[0])
      await until(`(() => { const v=document.querySelector('[role="dialog"] video'); return v && v.videoWidth > 0 })()`)
      report[scenario.name].video = await evaluate(`(() => { const v=document.querySelector('[role="dialog"] video'); return {width:v.videoWidth,height:v.videoHeight,objectFit:getComputedStyle(v).objectFit} })()`)
      assert(report[scenario.name].video.width < report[scenario.name].video.height)
      assert.equal(report[scenario.name].video.objectFit, "contain")
      await shot("08-portrait-output")
    } else if (scenario.name === "text") {
      await openOutput(scenario.ids[0])
      report[scenario.name].textLength = await evaluate(`document.querySelector('[role="dialog"] p.whitespace-pre-wrap')?.textContent.length || 0`)
      assert(report[scenario.name].textLength > 20)
      assert(await evaluate(`document.querySelector('[role="dialog"]')?.innerText.includes('1 / 1')`))
      await shot("09-text-output")
    } else if (scenario.name === "image") {
      await openOutput(scenario.ids[0])
      await until(`(() => { const img=document.querySelector('[role="dialog"] img:not([alt=""])'); return img && img.complete && img.naturalWidth > 0 })()`)
      report[scenario.name].image = await evaluate(`(() => { const img=document.querySelector('[role="dialog"] img:not([alt=""])'); return {width:img.naturalWidth,height:img.naturalHeight,objectFit:getComputedStyle(img).objectFit} })()`)
      assert.equal(report[scenario.name].image.objectFit, "contain")
      await shot("10-image-output")
    }
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" })
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" })
    await wait(400)
  }
  writeFileSync(`${OUT}/matrix-report.json`, JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
} catch (error) {
  writeFileSync(`${OUT}/matrix-report.json`, JSON.stringify({ ...report, error: String(error) }, null, 2))
  throw error
} finally {
  chrome.kill()
}
