import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import type { RemotionProject } from "./contract";
import {
  assertRemotionProject,
  guardStaticFileResources,
  STATIC_FILE_RESOURCE_GUARD_BODY,
} from "./policy";

function project(visual: string): RemotionProject {
  const entry = `import React from "react";
import { Composition, registerRoot } from "remotion";
import Visual from "./Visual";
const Root = () => <Composition id="GeneratedVisual" component={Visual} fps={30} width={640} height={360} durationInFrames={60} />;
registerRoot(Root);
`;
  const files = [
    { path: "src/index.tsx", content: entry },
    { path: "src/Visual.tsx", content: visual },
  ].map((file) => ({ ...file, digest: createHash("sha256").update(file.content, "utf8").digest("hex") }));
  return {
    schema_version: 1,
    entry: "src/index.tsx",
    composition_id: "GeneratedVisual",
    files,
    props: {},
    props_schema: { type: "object", additionalProperties: false, properties: {}, required: [] },
  };
}

test("inline SVG local fragment references are allowed", () => {
  const source = project(`export default function Visual() {
    return <AbsoluteFill><svg width={640} height={360}>
      <defs>
        <filter id="soft"><feGaussianBlur stdDeviation={4} /></filter>
        <mask id="hole"><rect width={640} height={360} fill="white" /></mask>
      </defs>
      <rect width={640} height={360} filter="url(#soft)" mask="url(#hole)" fill="white" />
    </svg></AbsoluteFill>;
  }`);
  assert.doesNotThrow(() => assertRemotionProject(source, []));
});

test("declared JSON layout modules remain data and keep their original bytes", () => {
  const source = project(`import layout from "./layout.json";
    export default function Visual() { return <div>{layout.title}</div>; }`);
  const layout = (content: string) => ({
    path: "src/layout.json",
    content,
    digest: createHash("sha256").update(content, "utf8").digest("hex"),
  });
  assert.throws(() => assertRemotionProject(source, []), /does not resolve/);
  const file = layout('{"title":"Value","camera":{"x":320}}\n');
  source.files.push(file);
  assert.doesNotThrow(() => assertRemotionProject(source, []));
  assert.equal(guardStaticFileResources(file, []), file.content);
  source.files[2] = layout('{"title":}');
  assert.throws(() => assertRemotionProject(source, []), /valid JSON/);
  source.files[2] = layout('{"texture":"https://example.test/image.png"}');
  assert.throws(() => assertRemotionProject(source, []), /external URLs/);
});

test("external and data resources remain forbidden beside local fragments", () => {
  for (const value of [
    "data:image/svg+xml;base64,AAAA",
    "https://example.test/image.png",
    "url(//example.test/image.png)",
    "url(#safe) url(https://example.test/image.png)",
  ]) {
    const source = project(`export default function Visual() {
      const forbidden = ${JSON.stringify(value)};
      return <AbsoluteFill>{forbidden}</AbsoluteFill>;
    }`);
    assert.throws(() => assertRemotionProject(source, []), /external URLs, CSS and data resources/);
  }
});

test("staticFile accepts fixed resources through ordinary expressions", () => {
  const resourcePath = "source-snapshots/page.png";
  const visuals = [
    `const PAGE_IMG = ${JSON.stringify(resourcePath)};
     export default function Visual() {
       return <AbsoluteFill><Img src={staticFile(PAGE_IMG)} /></AbsoluteFill>;
     }`,
    `const PAGE_IMG = "ignored-by-the-runtime-binding.png";
     export default function Visual(PAGE_IMG: string) {
       return <AbsoluteFill><Img src={staticFile(PAGE_IMG)} /></AbsoluteFill>;
     }`,
    `export default function Visual({ page }: { page: string }) {
       return <AbsoluteFill><Img src={staticFile(page)} /></AbsoluteFill>;
     }`,
    `export default function Visual({ pages }: { pages: string[] }) {
       return <AbsoluteFill><Img src={staticFile(pages[0])} /></AbsoluteFill>;
     }`,
  ];
  for (const visual of visuals) {
    assert.doesNotThrow(() => assertRemotionProject(project(visual), [{ path: resourcePath }]));
  }
});

test("staticFile still rejects undeclared literals and malformed calls", () => {
  const visuals = [
    `export default function Visual() {
       return <AbsoluteFill><Img src={staticFile("source-snapshots/other.png")} /></AbsoluteFill>;
     }`,
    `export default function Visual() {
       return <AbsoluteFill><Img src={staticFile()} /></AbsoluteFill>;
     }`,
    `export default function Visual({ page }: { page: string }) {
       return <AbsoluteFill><Img src={staticFile(page, "source-snapshots/page.png")} /></AbsoluteFill>;
     }`,
  ];
  for (const visual of visuals) {
    assert.throws(() => assertRemotionProject(project(visual), [{ path: "source-snapshots/page.png" }]));
  }
});

test("staticFile cannot be aliased or detached from its guarded call", () => {
  const visuals = [
    `import { staticFile as load } from "remotion";
     export default function Visual() {
       return <AbsoluteFill>{load("source-snapshots/page.png")}</AbsoluteFill>;
     }`,
    `export default function Visual() {
       const load = staticFile;
       return <AbsoluteFill>{load("source-snapshots/page.png")}</AbsoluteFill>;
     }`,
  ];
  for (const visual of visuals) {
    assert.throws(
      () => assertRemotionProject(project(visual), [{ path: "source-snapshots/page.png" }]),
      /guard cannot be bypassed/,
    );
  }
});

test("the execution copy guards every direct staticFile call against the exact resource manifest", () => {
  const resourcePath = "source-snapshots/page.png";
  const source = project(`export default function Visual({ page }: { page: string }) {
    return <AbsoluteFill><Img src={staticFile(page)} /><Img src={staticFile("source-snapshots/page.png")} /></AbsoluteFill>;
  }`);
  const file = source.files.find(({ path }) => path === "src/Visual.tsx")!;
  const transformed = guardStaticFileResources(file, [{ path: resourcePath }]);
  assert.notEqual(transformed, file.content);
  assert.match(transformed, /import \{ staticFile as __repurposerOriginalStaticFile \} from "remotion"/);
  assert.match(transformed, /new Set\(\["source-snapshots\/page.png"\]\)/);
  assert.match(transformed, /__repurposerStaticFile\(page\)/);
  assert.match(transformed, /__repurposerStaticFile\("source-snapshots\/page.png"\)/);
  assert.equal(guardStaticFileResources(source.files[0], []), source.files[0].content);
});

test("the runtime guard accepts only exact declared paths", () => {
  const evaluate = new Function("resourcePath", "resourcePaths", "originalStaticFile", STATIC_FILE_RESOURCE_GUARD_BODY) as (
    resourcePath: unknown,
    resourcePaths: ReadonlySet<string>,
    originalStaticFile: (resourcePath: string) => string,
  ) => string;
  const paths = new Set(["source-snapshots/page.png"]);
  const original = (resourcePath: string) => `/assets/${resourcePath}`;
  assert.equal(evaluate("source-snapshots/page.png", paths, original), "/assets/source-snapshots/page.png");
  for (const resourcePath of [
    "source-snapshots/other.png",
    "../page.png",
    "https://example.test/page.png",
    null,
    7,
  ]) {
    assert.throws(() => evaluate(resourcePath, paths, original), /not a declared fixed resource/);
  }
});

test("instrumentation identifiers cannot collide with authored bindings", () => {
  const source = project(`const __repurposerStaticFile = "authored";
  const __repurposerOriginalStaticFile = "authored";
  const __repurposerResourcePaths = "authored";
  export default function Visual({ page }: { page: string }) {
    return <AbsoluteFill><Img src={staticFile(page)} />{__repurposerStaticFile}</AbsoluteFill>;
  }`);
  const file = source.files.find(({ path }) => path === "src/Visual.tsx")!;
  const transformed = guardStaticFileResources(file, [{ path: "source-snapshots/page.png" }]);
  assert.match(transformed, /staticFile as ___repurposerOriginalStaticFile/);
  assert.match(transformed, /const ___repurposerStaticFile =/);
  assert.match(transformed, /___repurposerStaticFile\(page\)/);
});
