#!/usr/bin/env node
// 下批 B 收尾④: 浏览器免费检查（既有产物回放/卡片/Tasks 名称/页面可用性）。
// 零依赖 CDP 驱动系统 Chrome headless；登录态 = 铸 JWT 注 localStorage。
// 用法: node mg_b_cdp_check.mjs <jwt> <outdir>
import { spawn } from 'node:child_process'
import { writeFileSync, readFileSync } from 'node:fs'

const [jwt, outdir] = process.argv.slice(2)
const USER = { id: '1ed68148-1038-4bb4-a060-7f4d2367b6ca', email: 'scenario-5f321158@test.local', name: 'scenario-bot' }
const PID = 'd85eacce-d5c1-4bc7-b2bf-0cfea2ec8290'
const PORT = 9333

const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, '--no-first-run',
  '--user-data-dir=/tmp/mg-b-chrome-profile', '--window-size=1400,900',
  `--auth-server-allowlist=*`,
], { stdio: 'ignore' })

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

async function ws_connect() {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json()
      const page = list.find(t => t.type === 'page')
      if (page) return page.webSocketDebuggerUrl
    } catch {}
    await sleep(250)
  }
  throw new Error('chrome did not come up')
}

let msgId = 0
const pending = new Map()
let ws
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++msgId
    pending.set(id, { resolve, reject })
    ws.send(JSON.stringify({ id, method, params }))
  })
}

async function evaluate(expr) {
  const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })
  return r.result?.value
}

const consoleErrors = []
async function main() {
  const url = await ws_connect()
  ws = new WebSocket(url)
  await new Promise(r => (ws.onopen = r))
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data)
    if (m.id && pending.has(m.id)) { pending.get(m.id).resolve(m.result || {}); pending.delete(m.id) }
    if (m.method === 'Runtime.exceptionThrown') consoleErrors.push(m.params.exceptionDetails?.exception?.description?.slice(0, 300))
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') consoleErrors.push(m.params.args?.map(a => a.value || a.description || '').join(' ').slice(0, 300))
  }
  await send('Runtime.enable')
  await send('Page.enable')
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `
    localStorage.setItem('repurposer-token', ${JSON.stringify(jwt)});
    localStorage.setItem('repurposer-user', ${JSON.stringify(JSON.stringify(USER))});
    localStorage.setItem('repurposer-tour-seen', 'true');
  `})
  await send('Page.navigate', { url: `http://localhost:3000/projects/${PID}` })
  await sleep(9000)  // SSR + hydration + data fetch + media probe

  const report = await evaluate(`(() => {
    const q = (s) => Array.from(document.querySelectorAll(s))
    const vids = q('video').map(v => ({
      src: (v.currentSrc || v.src || '').slice(0, 120),
      readyState: v.readyState, duration: v.duration,
      error: v.error ? v.error.code : null,
      w: v.videoWidth, h: v.videoHeight,
    }))
    const text = document.body.innerText
    return {
      title: document.title,
      url: location.href,
      videos: vids,
      hasLoginWall: /验证码|登录|sign in/i.test(text) && !text.includes('scenario'),
      bodyLen: text.length,
      bodySample: text.replace(/\\s+/g, ' ').slice(0, 800),
      imgs: q('img').length,
      canvasNodes: q('[data-id], .react-flow__node').length || undefined,
    }
  })()`)
  console.log(JSON.stringify({ report, consoleErrors }, null, 1))
  const shot = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(`${outdir}/browser_project_page.png`, Buffer.from(shot.data, 'base64'))

  // 第二屏: 消息流底部（交付行/Tasks 名称所在）
  await evaluate(`window.scrollTo(0, document.body.scrollHeight)`)
  await sleep(1200)
  const shot2 = await send('Page.captureScreenshot', { format: 'png' })
  writeFileSync(`${outdir}/browser_project_bottom.png`, Buffer.from(shot2.data, 'base64'))

  // 第三段: 折叠行展开/收起行为（role=button + aria-expanded 的 FoldedActivityRow）
  const errsBefore = consoleErrors.length
  const foldProbe = await evaluate(`(() => {
    const folds = Array.from(document.querySelectorAll('[role="button"][aria-expanded]'))
      .filter((el) => /Worked for|工作了/.test(el.innerText || ''))
    if (!folds.length) return { folds: 0 }
    const f = folds[0]
    f.click()
    return new Promise((res) => setTimeout(() => {
      const expanded = f.getAttribute('aria-expanded') === 'true'
      const catRows = f.parentElement ? f.parentElement.children.length - 1 : -1
      const catText = (f.parentElement?.innerText || '').replace(/\\s+/g, ' ').slice(0, 200)
      f.click()  // collapse back
      setTimeout(() => res({
        folds: folds.length, label: (f.innerText || '').trim(), expanded, catRows, catText,
        collapsedBack: f.getAttribute('aria-expanded') === 'false',
      }), 300)
    }, 400))
  })()`)
  console.log(JSON.stringify({ foldProbe, newConsoleErrors: consoleErrors.slice(errsBefore) }, null, 1))
}

main().catch(e => { console.error('FAIL', e); process.exitCode = 1 }).finally(async () => {
  await sleep(300); chrome.kill()
})
