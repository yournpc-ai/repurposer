// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { ReactNode } from "react"

import { StudioHeader } from "./StudioHeader"
import { StudioHeaderProvider, useStudioHeader } from "./StudioHeaderContext"

let mockPathname = "/projects/proj-1"

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to, ...rest }: { children?: ReactNode; to?: string; [k: string]: unknown }) => (
    <a href={to} {...rest}>{children}</a>
  ),
  useRouterState: ({ select }: { select: (s: { location: { pathname: string } }) => string }) =>
    select({ location: { pathname: mockPathname } }),
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
    actions: <button type="button">Workbench</button>,
    hideNotifications: true,
  })
  return <div data-testid="route-body">Thread</div>
}

describe("StudioHeader unified single-row bar", () => {
  it("places credits before right actions without divider and hides notifications on project chat", () => {
    mockPathname = "/projects/proj-1"
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
    const credits = screen.getByTestId("credits-pill")
    const workbench = screen.getByRole("button", { name: "Workbench" })
    expect(credits.compareDocumentPosition(workbench) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(container.querySelector('[data-slot="studio-header-divider"]')).toBeNull()
    expect(screen.queryByTestId("notification-bell")).toBeNull()

    // Navigating away from project chat clears injected slots and shows notifications again
    mockPathname = "/home"
    rerender(
      <StudioHeaderProvider>
        <StudioHeader />
      </StudioHeaderProvider>,
    )
    expect(screen.queryByText("Launch Cut v3")).toBeNull()
    expect(screen.getByTestId("notification-bell")).toBeTruthy()
  })
})
