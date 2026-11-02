import ts from "typescript";

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

/**
 * Source-policy diagnostics, not a security sandbox. The bake worker also has
 * a minimal environment and a hard process lifetime; deployment isolation is
 * still required before treating authored code as hostile input.
 */
export function assertComponentSource(code: string): void {
  const source = ts.createSourceFile("generated.tsx", code, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const transpiled = ts.transpileModule(code, {
    fileName: "generated.tsx",
    reportDiagnostics: true,
    compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  });
  const syntax = (transpiled.diagnostics ?? []).find((item) => item.category === ts.DiagnosticCategory.Error);
  if (syntax) {
    throw new ComponentPolicyError(`TSX syntax error: ${ts.flattenDiagnosticMessageText(syntax.messageText, " ")}`);
  }

  const hasDefaultExport = source.statements.some((statement) =>
    ts.isExportAssignment(statement) ||
    (ts.canHaveModifiers(statement) && ts.getModifiers(statement)?.some(
      (modifier) => modifier.kind === ts.SyntaxKind.DefaultKeyword,
    )),
  );
  if (!hasDefaultExport) throw new ComponentPolicyError("component-v1 needs a default export");

  const visit = (node: ts.Node): void => {
    if (ts.isImportDeclaration(node) || ts.isImportEqualsDeclaration(node) ||
        (ts.isExportDeclaration(node) && node.moduleSpecifier)) {
      throw new ComponentPolicyError("imports and re-exports are not available");
    }
    if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) {
      throw new ComponentPolicyError("dynamic import is not available");
    }
    if (ts.isIdentifier(node) && BANNED_IDENTIFIERS.has(node.text)) {
      throw new ComponentPolicyError(`${node.text} is not available`);
    }
    if (ts.isPropertyAccessExpression(node) &&
        ts.isIdentifier(node.expression) && node.expression.text === "Math" && node.name.text === "random") {
      throw new ComponentPolicyError("Math.random is not deterministic; use the supplied random(seed)");
    }
    if ((ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) &&
        ts.isIdentifier(node.tagName) && BANNED_MEDIA_TAGS.has(node.tagName.text.toLowerCase())) {
      throw new ComponentPolicyError(`<${node.tagName.text}> is not an allowed visual element`);
    }
    if (ts.isJsxAttribute(node) && ts.isIdentifier(node.name) &&
        ["src", "srcset", "href", "poster", "xlink:href"].includes(node.name.text.toLowerCase())) {
      throw new ComponentPolicyError(`JSX attribute ${node.name.text} may not load a resource`);
    }
    if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) &&
        /url\s*\(|@import\b|\bdata:/i.test(node.text)) {
      throw new ComponentPolicyError("external CSS/data resources are not available");
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
}
