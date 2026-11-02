import assert from "node:assert/strict";
import test from "node:test";

import { assertComponentSource, ComponentPolicyError } from "./policy";

const valid = `export default function Visual({ parameters }: { parameters: { label: string } }) {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ opacity, width, height }}><span>{parameters.label}</span></AbsoluteFill>;
}`;

test("component policy accepts injected visual APIs and declared parameters", () => {
  assert.doesNotThrow(() => assertComponentSource(valid));
});

test("component policy rejects imports, re-exports and dynamic code", () => {
  for (const code of [
    `import x from "x"; ${valid}`,
    `export { default as x } from "x"; ${valid}`,
    `const load = () => import("x"); ${valid}`,
    `const run = () => eval("1"); ${valid}`,
  ]) {
    assert.throws(() => assertComponentSource(code), ComponentPolicyError);
  }
});

test("component policy rejects network, host state and external media", () => {
  for (const code of [
    `const send = () => fetch("https://example.test"); ${valid}`,
    `const host = process.env; ${valid}`,
    `const now = () => Date.now(); ${valid}`,
    `const random = () => Math.random(); ${valid}`,
    `const image = () => <img src="https://example.test/a.png" />; ${valid}`,
    `const style = { background: "url(https://example.test/a.png)" }; ${valid}`,
  ]) {
    assert.throws(() => assertComponentSource(code), ComponentPolicyError);
  }
});
