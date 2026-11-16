import { execFile, execFileSync, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { ComponentBakeRequest } from "./contract";

const require = createRequire(import.meta.url);
const WORKER = fileURLToPath(new URL("./worker.ts", import.meta.url));
const TSX_CLI = require.resolve("tsx/cli");
const REPO_ROOT = fileURLToPath(new URL("../../../..", import.meta.url));
const SANDBOX_EXEC = "/usr/bin/sandbox-exec";
const RENDER_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const HEADLESS_SHELL = path.join(
  RENDER_ROOT,
  "node_modules",
  ".remotion",
  "chrome-headless-shell",
  `mac-${os.arch() === "arm64" ? "arm64" : "x64"}`,
  `chrome-headless-shell-mac-${os.arch() === "arm64" ? "arm64" : "x64"}`,
  "chrome-headless-shell",
);
const MAX_RESULT_BYTES = 40 * 1024 * 1024;
const BAKE_TIMEOUT_MS = 240_000;
const CPU_SECONDS = 220;
const MEMORY_KB = 8 * 1024 * 1024;
const TEMP_QUOTA_KB = 512 * 1024;
const MAX_ACTIVE_BAKES = 1;
let activeBakes = 0;

export class ComponentBakeError extends Error {
  constructor(message: string, readonly sourceRepairable = true) {
    super(message);
  }
}

function supportedIsolation(): boolean {
  return process.platform === "darwin" &&
    existsSync(SANDBOX_EXEC) &&
    existsSync(process.env.COMPONENT_BROWSER_EXECUTABLE ?? HEADLESS_SHELL);
}

/** The public flag opens only the measured Seatbelt runner below. Other
 * platforms stay fail-closed instead of mistaking process policy for a sandbox. */
export function componentBakeEnabled(): boolean {
  return process.env.COMPONENT_BAKE_ENABLED === "true" && supportedIsolation();
}

export function componentIsolation(): string {
  return componentBakeEnabled() ? "macos-seatbelt-loopback-and-workdir" : "disabled";
}

export function assertComponentBakeEnabled(): void {
  if (!componentBakeEnabled()) {
    throw new ComponentBakeError(
      "remotion-project bake is disabled because this deployment has no verified isolated component runner",
      false,
    );
  }
}

function diagnosticTail(value: string): string {
  return value.trim().slice(-4000);
}

function quoted(value: string): string {
  return JSON.stringify(value);
}

export function sandboxProfile(work: string): string {
  const home = os.homedir();
  const readable = [
    path.join(REPO_ROOT, "node_modules"),
    path.join(REPO_ROOT, "apps", "render"),
    path.join(REPO_ROOT, "packages"),
    work,
  ];
  return [
    "(version 1)",
    "(allow default)",
    "(deny network-outbound)",
    '(allow network-outbound (remote tcp "localhost:*") (local unix))',
    '(deny network-outbound (remote tcp "localhost:5432") (remote tcp "localhost:3306") (remote tcp "localhost:6379"))',
    "(deny file-write*)",
    `(allow file-write* (subpath ${quoted(work)}) (literal "/dev/null") (literal "/dev/urandom"))`,
    `(deny file-read* (subpath ${quoted(home)}))`,
    `(allow file-read-metadata (literal "/Users") (literal ${quoted(home)}) (literal ${quoted(path.resolve(REPO_ROOT))}) (literal ${quoted(path.join(REPO_ROOT, "apps"))}))`,
    `(allow file-read* ${readable.map((root) => `(subpath ${quoted(root)})`).join(" ")})`,
  ].join("\n");
}

/** One bake: one global slot, an unprivileged-by-confinement child process
 * group, loopback-only networking, dependency/workdir-only files, and hard
 * CPU/RSS/temp/file limits. No business environment reaches the child. */
export async function bakeComponent(request: ComponentBakeRequest): Promise<unknown> {
  assertComponentBakeEnabled();
  if (activeBakes >= MAX_ACTIVE_BAKES) {
    throw new ComponentBakeError("component bake capacity is occupied; retry after the active bake settles", false);
  }
  activeBakes += 1;
  const work = await fs.mkdtemp(path.join(os.tmpdir(), "remotion-project-"));
  const realWork = await fs.realpath(work);
  const requestPath = path.join(realWork, "request.json");
  const resultPath = path.join(realWork, "result.json");
  const profilePath = path.join(realWork, "runner.sb");
  const temp = path.join(realWork, "tmp");
  await fs.mkdir(temp);
  await fs.writeFile(requestPath, JSON.stringify(request), "utf8");
  await fs.writeFile(profilePath, sandboxProfile(realWork), "utf8");

  const shellLimits = [
    `ulimit -t ${CPU_SECONDS}`,
    "ulimit -n 256",
    "ulimit -f 262144",
    'exec /usr/bin/sandbox-exec -f "$1" "$2" "$3" "$4" "$5" "$6"',
  ].join("; ");
  const child = spawn("/bin/sh", [
    "-c", shellLimits, "component-runner",
    profilePath, process.execPath, TSX_CLI, WORKER, requestPath, resultPath,
  ], {
    cwd: realWork,
    detached: true,
    env: {
      PATH: process.env.PATH ?? "",
      HOME: realWork,
      TMPDIR: temp,
      NODE_NO_WARNINGS: "1",
      NO_PROXY: "*",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  let stdout = "";
  child.stderr.on("data", (chunk: Buffer) => { stderr = diagnosticTail(stderr + chunk.toString()); });
  child.stdout.on("data", (chunk: Buffer) => { stdout = diagnosticTail(stdout + chunk.toString()); });
  let timedOut = false;
  let resourceFailure: string | null = null;
  const trackedGroups = new Set<number>();
  const collectDescendantGroups = () => {
    if (child.pid === undefined) return;
    try {
      const rows = execFileSync("/bin/ps", ["-A", "-o", "pid=,ppid=,pgid="], { encoding: "utf8" })
        .split("\n")
        .map((line) => line.trim().split(/\s+/).map(Number))
        .filter(([pid, ppid, pgid]) => Number.isFinite(pid) && Number.isFinite(ppid) && Number.isFinite(pgid));
      const descendants = new Set<number>([child.pid]);
      let changed = true;
      while (changed) {
        changed = false;
        for (const [pid, ppid] of rows) {
          if (!descendants.has(pid) && descendants.has(ppid)) {
            descendants.add(pid);
            changed = true;
          }
        }
      }
      for (const [pid, , pgid] of rows) if (descendants.has(pid)) trackedGroups.add(pgid);
    } catch { /* the root may already be reaped; retained groups remain killable */ }
  };
  const killGroup = () => {
    if (child.pid === undefined) return;
    // Chrome creates its own process group. Track the whole descendant tree,
    // not just the shell's pgid, and retain those groups after orphaning.
    collectDescendantGroups();
    for (const group of trackedGroups) {
      try { process.kill(-group, "SIGKILL"); } catch { /* already reaped */ }
    }
  };
  const timer = setTimeout(() => { timedOut = true; killGroup(); }, BAKE_TIMEOUT_MS);
  let monitorBusy = false;
  const monitor = setInterval(() => {
    if (monitorBusy || child.pid === undefined) return;
    monitorBusy = true;
    collectDescendantGroups();
    execFile("/bin/ps", ["-A", "-o", "pgid=,rss="], (error, output) => {
      if (error) {
        monitorBusy = false;
        return;
      }
      const rss = output.split("\n").reduce((sum, line) => {
        const [pgid, kb] = line.trim().split(/\s+/).map(Number);
        return trackedGroups.has(pgid) && Number.isFinite(kb) ? sum + kb : sum;
      }, 0);
      if (rss > MEMORY_KB) {
        resourceFailure = "component bake exceeded its 8GiB process-group memory budget";
        killGroup();
      }
      execFile("/usr/bin/du", ["-sk", realWork], (duError, duOutput) => {
        monitorBusy = false;
        if (duError) return;
        const used = Number.parseInt(duOutput.split(/\s+/, 1)[0] ?? "0", 10);
        if (used > TEMP_QUOTA_KB) {
          resourceFailure = "component bake exceeded its 512MiB temporary-storage budget";
          killGroup();
        }
      });
    });
  }, 2000);
  monitor.unref();

  try {
    const exitCode = await new Promise<number | null>((resolve, reject) => {
      child.once("error", reject);
      child.once("close", (code) => resolve(code));
    });
    if (timedOut) {
      const diagnostics = diagnosticTail(stderr || stdout);
      throw new ComponentBakeError(
        `component bake exceeded its 240s process budget${diagnostics ? `: ${diagnostics}` : ""}`,
        false,
      );
    }
    if (resourceFailure) throw new ComponentBakeError(resourceFailure, false);
    if (exitCode !== 0) {
      throw new ComponentBakeError(diagnosticTail(stderr || stdout) || `bake worker exited ${exitCode}`);
    }
    const stat = await fs.stat(resultPath);
    if (stat.size > MAX_RESULT_BYTES) throw new ComponentBakeError("component bake result exceeded its byte budget", false);
    return JSON.parse(await fs.readFile(resultPath, "utf8"));
  } catch (error) {
    if (error instanceof SyntaxError) throw new ComponentBakeError("bake worker returned malformed JSON", false);
    throw error;
  } finally {
    clearTimeout(timer);
    clearInterval(monitor);
    killGroup();
    await fs.rm(realWork, { recursive: true, force: true });
    activeBakes -= 1;
  }
}
