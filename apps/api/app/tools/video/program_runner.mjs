// drawing-v1's only program entry point: JSON in, per-frame JSON commands out.
// Untrusted source runs without host capabilities in a permission-restricted process.
import vm from "node:vm";

let input = "";
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input);
const context = vm.createContext(Object.create(null), {
  codeGeneration: { strings: false, wasm: false },
});

try {
  new vm.Script(`
    Date = undefined;
    Math.random = () => { throw new Error("Math.random is unavailable; derive deterministic variation from ctx.frame"); };
  `).runInContext(context, { timeout: 100 });
  new vm.Script(`"use strict";\n${request.code}\n;globalThis.__render = render;`, {
    filename: "visual-program.js",
  }).runInContext(context, { timeout: 500 });
  if (typeof context.__render !== "function") throw new Error("render(ctx) is not defined");

  for (let frame = 0; frame < request.output.duration_frames; frame += 1) {
    const payload = {
      frame,
      time: frame / request.output.fps,
      durationFrames: request.output.duration_frames,
      fps: request.output.fps,
      width: request.output.width,
      height: request.output.height,
      parameters: request.parameters,
    };
    context.__payload = JSON.stringify(payload);
    const result = new vm.Script(`
      (() => {
        const value = JSON.parse(__payload);
        const freeze = (item) => {
          if (item && typeof item === "object") {
            Object.values(item).forEach(freeze);
            Object.freeze(item);
          }
          return item;
        };
        return JSON.stringify(__render(freeze(value)));
      })()
    `).runInContext(context, { timeout: 250 });
    if (result === undefined) throw new Error(`frame ${frame}: render returned no JSON value`);
    process.stdout.write(`${JSON.stringify({ frame, commands: JSON.parse(result) })}\n`);
  }
} catch (error) {
  process.stderr.write(error instanceof Error ? `${error.name}: ${error.message}\n` : String(error));
  process.exit(1);
}
