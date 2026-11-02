import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import { createRequire } from "node:module";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { ComponentBakeRequest } from "./contract";

const require = createRequire(import.meta.url);
const WORKER = fileURLToPath(new URL("./worker.ts", import.meta.url));
const TSX_CLI = require.resolve("tsx/cli");
const MAX_RESULT_BYTES = 40 * 1024 * 1024;
const BAKE_TIMEOUT_MS = 240_000;

export class ComponentBakeError extends Error {}

/** Deployment guard, not a sandbox claim. The worker still needs real
 * unprivileged/filesystem/egress/resource isolation before this is enabled. */
export function componentBakeEnabled(): boolean {
  return process.env.COMPONENT_BAKE_ENABLED === "true";
}

export function assertComponentBakeEnabled(): void {
  if (!componentBakeEnabled()) {
    throw new ComponentBakeError(
      "component-v1 bake is disabled because this deployment has no verified isolated component runner",
    );
  }
}

function diagnosticTail(value: string): string {
  return value.trim().slice(-4000);
}

/** Run one bake in a killable process group with no business environment. */
export async function bakeComponent(request: ComponentBakeRequest): Promise<unknown> {
  assertComponentBakeEnabled();
  const work = await fs.mkdtemp(path.join(os.tmpdir(), "component-v1-"));
  const requestPath = path.join(work, "request.json");
  const resultPath = path.join(work, "result.json");
  const temp = path.join(work, "tmp");
  await fs.mkdir(temp);
  await fs.writeFile(requestPath, JSON.stringify(request), "utf8");

  const child = spawn(process.execPath, [TSX_CLI, WORKER, requestPath, resultPath], {
    cwd: work,
    detached: true,
    env: {
      PATH: process.env.PATH ?? "",
      HOME: work,
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
  const killGroup = () => {
    if (child.pid === undefined || child.exitCode !== null || child.signalCode !== null) return;
    try { process.kill(-child.pid, "SIGKILL"); } catch { child.kill("SIGKILL"); }
  };
  const timer = setTimeout(() => { timedOut = true; killGroup(); }, BAKE_TIMEOUT_MS);

  try {
    const exitCode = await new Promise<number | null>((resolve, reject) => {
      child.once("error", reject);
      child.once("close", (code) => resolve(code));
    });
    if (timedOut) throw new ComponentBakeError("component bake exceeded its 240s process budget");
    if (exitCode !== 0) {
      throw new ComponentBakeError(diagnosticTail(stderr || stdout) || `bake worker exited ${exitCode}`);
    }
    const stat = await fs.stat(resultPath);
    if (stat.size > MAX_RESULT_BYTES) throw new ComponentBakeError("component bake result exceeded its byte budget");
    return JSON.parse(await fs.readFile(resultPath, "utf8"));
  } catch (error) {
    if (error instanceof SyntaxError) throw new ComponentBakeError("bake worker returned malformed JSON");
    throw error;
  } finally {
    clearTimeout(timer);
    killGroup();
    await fs.rm(work, { recursive: true, force: true });
  }
}
