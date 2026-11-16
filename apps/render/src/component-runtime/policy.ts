import { createHash } from "node:crypto";
import path from "node:path";

import ts from "typescript";

import type { ProjectFile, RemotionProject } from "./contract";

export class ComponentPolicyError extends Error {}

const BANNED_IDENTIFIERS = new Set([
  "require", "module", "exports", "eval", "Function", "fetch", "XMLHttpRequest",
  "WebSocket", "EventSource", "process", "global", "globalThis", "window", "document",
  "navigator", "localStorage", "sessionStorage", "Deno", "Bun", "Date", "performance",
  "setTimeout", "setInterval", "setImmediate", "queueMicrotask", "delayRender",
  "continueRender",
]);
const BANNED_MEDIA_TAGS = new Set([
  "img", "image", "video", "audio", "iframe", "script", "link",
]);
const ALLOWED_REMOTION_IMPORTS = new Set([
  "AbsoluteFill", "Composition", "Sequence", "Series", "useCurrentFrame",
  "useVideoConfig", "interpolate", "spring", "Easing", "random", "Img",
  "staticFile", "registerRoot",
]);

function parseSource(file: ProjectFile): ts.SourceFile {
  const source = ts.createSourceFile(file.path, file.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const transpiled = ts.transpileModule(file.content, {
    fileName: file.path,
    reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const syntax = (transpiled.diagnostics ?? []).find((item) => item.category === ts.DiagnosticCategory.Error);
  if (syntax) {
    const position = syntax.start === undefined ? null : source.getLineAndCharacterOfPosition(syntax.start);
    const location = position ? `:${position.line + 1}:${position.character + 1}` : "";
    const excerpt = position ? source.text.split(/\r?\n/)[position.line]?.trim() : "";
    throw new ComponentPolicyError(
      `${file.path}${location}: TSX syntax error: ${ts.flattenDiagnosticMessageText(syntax.messageText, " ")}` +
      (excerpt ? `\nSource: ${excerpt.slice(0, 240)}` : ""),
    );
  }
  return source;
}

function resolveProjectImport(from: string, specifier: string, paths: ReadonlySet<string>): void {
  if (!specifier.startsWith("./") && !specifier.startsWith("../")) {
    throw new ComponentPolicyError(`undeclared dependency ${specifier} is not available`);
  }
  const base = path.posix.normalize(path.posix.join(path.posix.dirname(from), specifier));
  const candidates = [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`, `${base}/index.tsx`];
  if (base.startsWith("../") || !candidates.some((candidate) => paths.has(candidate))) {
    throw new ComponentPolicyError(`relative import ${specifier} does not resolve to a declared source file`);
  }
}

function assertImports(source: ts.SourceFile, paths: ReadonlySet<string> | null): void {
  for (const statement of source.statements) {
    if (ts.isImportDeclaration(statement)) {
      if (paths === null) throw new ComponentPolicyError("imports and re-exports are not available");
      if (!ts.isStringLiteral(statement.moduleSpecifier)) {
        throw new ComponentPolicyError("import module specifiers must be fixed strings");
      }
      const specifier = statement.moduleSpecifier.text;
      if (specifier === "react") continue;
      if (specifier === "remotion") {
        const clause = statement.importClause;
        if (!clause || clause.name || clause.isTypeOnly && !clause.namedBindings) {
          throw new ComponentPolicyError("remotion imports must name their audited APIs");
        }
        if (clause.namedBindings && !ts.isNamedImports(clause.namedBindings)) {
          throw new ComponentPolicyError("namespace Remotion imports are not available");
        }
        if (clause.namedBindings) {
          for (const element of clause.namedBindings.elements) {
            const imported = element.propertyName?.text ?? element.name.text;
            if (!ALLOWED_REMOTION_IMPORTS.has(imported)) {
              throw new ComponentPolicyError(`remotion.${imported} is not an allowed API`);
            }
            if (imported === "staticFile" && element.name.text !== "staticFile") {
              throw new ComponentPolicyError("staticFile must be imported without an alias so its resource guard cannot be bypassed");
            }
          }
        }
        continue;
      }
      resolveProjectImport(source.fileName, specifier, paths);
      continue;
    }
    if (ts.isImportEqualsDeclaration(statement) ||
        (ts.isExportDeclaration(statement) && statement.moduleSpecifier)) {
      throw new ComponentPolicyError("require-style imports and re-exports are not available");
    }
  }
}

function assertStaticFileCall(
  node: ts.CallExpression,
  resourcePaths: ReadonlySet<string> | null,
): void {
  if (resourcePaths === null) {
    throw new ComponentPolicyError("staticFile is not available without declared resources");
  }
  const argument = node.arguments.length === 1 ? node.arguments[0] : undefined;
  if (!argument || ts.isSpreadElement(argument)) {
    throw new ComponentPolicyError("staticFile requires exactly one resource path");
  }
  // Dynamic props, variables and computed paths are ordinary authoring code.
  // The execution copy wraps every call with the exact per-Clip whitelist below.
  // Reject a known-bad literal early; every other value is checked at runtime.
  if (ts.isStringLiteralLike(argument) && !resourcePaths.has(argument.text)) {
    throw new ComponentPolicyError(`staticFile path is not a declared fixed resource: ${argument.text}`);
  }
}

export const STATIC_FILE_RESOURCE_GUARD_BODY = `if (typeof resourcePath !== "string" || !resourcePaths.has(resourcePath)) {
  throw new Error(\`staticFile path is not a declared fixed resource: \${String(resourcePath)}\`);
}
return originalStaticFile(resourcePath);`;

/** Instrument only the disposable bake copy, never the immutable authored source.
 * Each direct staticFile call resolves through a guard closed over this Clip's
 * declared paths. The source digest still covers the exact bytes the Agent wrote. */
export function guardStaticFileResources(
  file: ProjectFile,
  resources: readonly { path: string }[],
): string {
  if (file.path.endsWith(".json")) return file.content;
  const source = parseSource(file);
  const identifiers = new Set<string>();
  const replacements: { start: number; end: number }[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isIdentifier(node)) identifiers.add(node.text);
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) &&
        node.expression.text === "staticFile") {
      replacements.push({ start: node.expression.getStart(source), end: node.expression.getEnd() });
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  if (!replacements.length) return file.content;

  const uniqueName = (base: string): string => {
    let candidate = base;
    while (identifiers.has(candidate)) candidate = `_${candidate}`;
    identifiers.add(candidate);
    return candidate;
  };
  const original = uniqueName("__repurposerOriginalStaticFile");
  const paths = uniqueName("__repurposerResourcePaths");
  const guarded = uniqueName("__repurposerStaticFile");
  const manifest = JSON.stringify(resources.map(({ path: resourcePath }) => resourcePath));
  const prelude = `import { staticFile as ${original} } from "remotion";
const ${paths}: ReadonlySet<string> = new Set(${manifest});
const ${guarded} = (resourcePath: string): string => {
  const resourcePaths = ${paths};
  const originalStaticFile = ${original};
  ${STATIC_FILE_RESOURCE_GUARD_BODY}
};
`;
  let content = file.content;
  for (const replacement of replacements.sort((a, b) => b.start - a.start)) {
    content = content.slice(0, replacement.start) + guarded + content.slice(replacement.end);
  }
  return prelude + content;
}

const LOCAL_SVG_FRAGMENT_URL = /url\(\s*#[A-Za-z_][A-Za-z0-9_.:-]*\s*\)/gi;

function containsExternalResourceText(text: string): boolean {
  // A bare local fragment never leaves the document and is required for inline
  // SVG filters, masks and paint servers. Every other URL/data form stays shut.
  const withoutLocalFragments = text.replace(LOCAL_SVG_FRAGMENT_URL, "");
  return /url\s*\(|@import\b|\bdata:|https?:\/\//i.test(withoutLocalFragments);
}

function assertNodes(source: ts.SourceFile, resourcePaths: ReadonlySet<string> | null): void {
  const visit = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      throw new ComponentPolicyError("dynamic import is not available");
    }
    if (ts.isIdentifier(node) && BANNED_IDENTIFIERS.has(node.text)) {
      throw new ComponentPolicyError(`${node.text} is not available`);
    }
    if (ts.isIdentifier(node) && node.text === "staticFile") {
      const importedName = ts.isImportSpecifier(node.parent);
      const directCall = ts.isCallExpression(node.parent) && node.parent.expression === node;
      if (!importedName && !directCall) {
        throw new ComponentPolicyError("staticFile must be called directly so its resource guard cannot be bypassed");
      }
    }
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "staticFile") {
      assertStaticFileCall(node, resourcePaths);
    }
    if (ts.isPropertyAccessExpression(node) &&
        ts.isIdentifier(node.expression) && node.expression.text === "Math" && node.name.text === "random") {
      throw new ComponentPolicyError("Math.random is not deterministic; use the supplied random(seed)");
    }
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      if (ts.isIdentifier(node.tagName) && BANNED_MEDIA_TAGS.has(node.tagName.text)) {
        throw new ComponentPolicyError(`<${node.tagName.text}> is not an allowed visual element`);
      }
      for (const attribute of node.attributes.properties) {
        if (!ts.isJsxAttribute(attribute) || !ts.isIdentifier(attribute.name)) continue;
        const name = attribute.name.text.toLowerCase();
        if (!["src", "srcset", "href", "poster", "xlink:href"].includes(name)) continue;
        const initializer = attribute.initializer;
        const fixedImg = ts.isIdentifier(node.tagName) && node.tagName.text === "Img" && name === "src" &&
          initializer && ts.isJsxExpression(initializer) && initializer.expression &&
          ts.isCallExpression(initializer.expression) && ts.isIdentifier(initializer.expression.expression) &&
          initializer.expression.expression.text === "staticFile";
        if (!fixedImg) throw new ComponentPolicyError(`JSX attribute ${attribute.name.text} may not load a resource`);
      }
    }
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) &&
        containsExternalResourceText(node.text)) {
      throw new ComponentPolicyError("external URLs, CSS and data resources are not available");
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}

/** Historical single-component source remains readable and bakeable. */
export function assertComponentSource(code: string): void {
  const file = { path: "generated.tsx", content: code, digest: "" };
  const source = parseSource(file);
  assertImports(source, null);
  assertNodes(source, null);
  const hasDefaultExport = source.statements.some((statement) =>
    ts.isExportAssignment(statement) ||
    (ts.canHaveModifiers(statement) && ts.getModifiers(statement)?.some(
      (modifier) => modifier.kind === ts.SyntaxKind.DefaultKeyword,
    )),
  );
  if (!hasDefaultExport) throw new ComponentPolicyError("remotion-project needs a default export");
}

function assertProps(project: RemotionProject): void {
  const required = new Set(project.props_schema.required ?? []);
  for (const key of required) {
    if (!(key in project.props)) throw new ComponentPolicyError(`required prop ${key} is absent`);
  }
  for (const [key, value] of Object.entries(project.props)) {
    const expected = project.props_schema.properties[key]?.type;
    const actual = value === null ? "null" : Array.isArray(value) ? "array" :
      typeof value === "number" && Number.isInteger(value) ? "integer" : typeof value;
    if (actual !== expected && !(expected === "number" && actual === "integer")) {
      throw new ComponentPolicyError(`prop ${key} does not match props_schema`);
    }
  }
}

export function assertRemotionProject(
  project: RemotionProject,
  resources: readonly { path: string }[],
): void {
  assertProps(project);
  const paths = new Set(project.files.map(({ path: filePath }) => filePath));
  const resourcePaths = new Set(resources.map(({ path: resourcePath }) => resourcePath));
  for (const file of project.files) {
    const actual = createHash("sha256").update(file.content, "utf8").digest("hex");
    if (actual !== file.digest) throw new ComponentPolicyError(`${file.path}: source digest mismatch`);
    if (file.path.endsWith(".json")) {
      try {
        JSON.parse(file.content, (_key, value: unknown) => {
          if (typeof value === "string" && containsExternalResourceText(value)) {
            throw new ComponentPolicyError("external URLs, CSS and data resources are not available");
          }
          return value;
        });
      } catch (error) {
        if (error instanceof ComponentPolicyError) throw error;
        throw new ComponentPolicyError(`${file.path}: project data file must contain valid JSON`);
      }
      continue;
    }
    const source = parseSource(file);
    assertImports(source, paths);
    assertNodes(source, resourcePaths);
  }
  const entry = parseSource(project.files.find(({ path }) => path === project.entry)!);
  let registersRoot = false;
  const inspectEntry = (node: ts.Node): void => {
    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "registerRoot") {
      registersRoot = true;
    }
    ts.forEachChild(node, inspectEntry);
  };
  inspectEntry(entry);
  if (!registersRoot) throw new ComponentPolicyError("project entry must call registerRoot");
}
