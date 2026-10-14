// Spike: web reader — fetch a landing page, extract its copy inventory and a
// screenshot. This is the capture half of the "URL → MG film" recipe.
// Usage: node capture.mjs [url] [outdir]
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const url = process.argv[2] || 'http://localhost:3000/';
const out = path.resolve(process.argv[3] || new URL('.', import.meta.url).pathname);
fs.mkdirSync(out, { recursive: true });

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

// --- 1. fetch + copy inventory (zero-dep lite extraction) -------------------
const html = await (await fetch(url)).text();
const strip = (s) => s
  .replace(/<script[\s\S]*?<\/script>/gi, ' ')
  .replace(/<style[\s\S]*?<\/style>/gi, ' ')
  .replace(/<[^>]+>/g, ' ')
  .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
  .replace(/&quot;/g, '"').replace(/&#x27;|&#39;/g, "'").replace(/&mdash;/g, '—')
  .replace(/\s+/g, ' ').trim();

const pick = (re) => {
  const seen = new Set(); const outArr = [];
  for (const m of html.matchAll(re)) {
    const t = strip(m[1] ?? '');
    if (t && t.length >= 2 && t.length <= 90 && !seen.has(t)) { seen.add(t); outArr.push(t); }
  }
  return outArr.slice(0, 24);
};

const title = strip(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1] ?? '');
const description = strip(html.match(/<meta\s+name="description"\s+content="([^"]*)"/i)?.[1] ?? '');
const research = {
  url,
  title,
  description,
  h1: pick(/<h1[^>]*>([\s\S]*?)<\/h1>/gi),
  h2: pick(/<h2[^>]*>([\s\S]*?)<\/h2>/gi),
  h3: pick(/<h3[^>]*>([\s\S]*?)<\/h3>/gi),
  buttons: pick(/<button[^>]*>([\s\S]*?)<\/button>/gi),
  links: pick(/<a\s[^>]*>([\s\S]*?)<\/a>/gi),
};

// --- 2. screenshot via system Chrome headless --------------------------------
const shot = path.join(out, 'landing.png');
execFileSync(CHROME, [
  // Dev-server HMR sockets never reach virtual-time quiescence — cap hard
  // with --timeout instead of --virtual-time-budget.
  '--headless=new', '--disable-gpu', '--hide-scrollbars',
  '--window-size=1440,900', '--timeout=9000',
  `--screenshot=${shot}`, url,
], { stdio: 'pipe' });
research.screenshot = 'landing.png';

fs.writeFileSync(path.join(out, 'research.json'), JSON.stringify(research, null, 1));
console.log(JSON.stringify(research, null, 1));
