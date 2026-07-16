/** Demo project constants and helpers.
 *
 * The demo project has a fixed UUID in the database, but the UI routes and
 * displays it via the short "demo" slug so users never see the long UUID.
 */

export const DEMO_PROJECT_ID = "11111111-1111-1111-1111-111111111111"
export const DEMO_PROJECT_SLUG = "demo"

/** Resolve a project route param (slug or UUID) to the real project id. */
export function resolveProjectId(id: string): string {
  return id === DEMO_PROJECT_SLUG ? DEMO_PROJECT_ID : id
}

/** Return the route param to use for a project: "demo" for the demo project. */
export function projectRouteParam(project: { id: string; is_demo?: boolean }): string {
  return project.is_demo ? DEMO_PROJECT_SLUG : project.id
}

/** True if the given id (slug or UUID) refers to the demo project. */
export function isDemoProjectId(id: string): boolean {
  return id === DEMO_PROJECT_SLUG || id === DEMO_PROJECT_ID
}
