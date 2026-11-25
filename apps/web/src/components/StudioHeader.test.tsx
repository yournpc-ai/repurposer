// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

import { StudioHeader } from "./StudioHeader"
import { StudioHeaderProvider, useStudioHeader } from "./StudioHeaderContext"

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, ...rest }: { children?: ReactNode; to?: string; [k: string]: unknown }) => (
    <a href={to} {...rest}>{children}</a>
  ),
  useRouterState: ({ select }: { select: (s: { location: { pathname: string } }) => string }) =>
    select({ location: { pathname: "/projects/proj-1" } }),
}))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/components/credits/CreditsPill", () => ({
  CreditsPill: () => <div data-testid="credits-pill">420</div>,
}))

vi.mock("@/components/notifications/NotificationBell", () => ({
  NotificationBell: () => <button type="button" data-testid="notification-bell">bell</button>,
}))

vi.mock("@/components/app-sidebar", () => ({
  AccountMenu: () => <div data-testid="account-menu" />,
}))

vi.mock("@/components/LogoMark", () => ({
  LogoMark: () => <span data-testid="logo-mark" />,
}))

afterEach(() => {
  cleanup()
})

function MockProjectRoute() {
  useStudioHeader({
    left: <span>Launch Cut v3</span>,
    actions: (
      <>
        <button type="button">Compact</button>
        <button type="button">Workbench</button>
      </>
    ),
  })
  return <div data-testid="route-body">Thread</div>
}

describe("StudioHeader unified single-row bar", () => {
  it("injects route left breadcrumb and right actions into ONE 48px header with hairline divider", () => {
    const { container, rerender } = render(
      <StudioHeaderProvider>
        <StudioHeader />
        <MockProjectRoute />
      </StudioHeaderProvider>,
    )

    const headers = container.querySelectorAll("header")
    expect(headers).toHaveLength(1)
    expect(headers[0].className).toContain("h-12")
    expect(screen.getByText("Launch Cut v3")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Compact" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "Workbench" })).toBeTruthy()
    expect(container.querySelector('[data-slot="studio-header-divider"]')).toBeTruthy()
    expect(screen.getByTestId("credits-pill")).toBeTruthy()
    expect(screen.getByTestId("notification-bell")).toBeTruthy()

    // Unmounting the route clears the injected slots cleanly (e.g. navigating to /home)
    rerender(
      <StudioHeaderProvider>
        <StudioHeader />
      </StudioHeaderProvider>,
    )
    expect(screen.queryByText("Launch Cut v3")).toBeNull()
    expect(container.querySelector('[data-slot="studio-header-divider"]')).toBeNull()
  })
})
