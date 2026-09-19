import path from "node:path"

import { defineConfig } from "vitest/config"

/** Contract-test config (Phase 3 Batch A): pure node, zero DOM — the web
 * contract seats (lifecycle stamp predicates / activity reducer / history
 * replay mapper / stream dispatch) test WITHOUT the app plugins: the app's
 * vite.config.ts carries tanstackStart()/devtools() which hang under
 * vitest, so this config wins (vitest prefers vitest.config.*) and wires
 * only the `@/` alias the sources use. */
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "src") },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
})
