import { Link, useMatch } from "@tanstack/react-router"
import { FolderKanban, Home, PanelLeft, User } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { AccountConsole } from "@/components/account-console"
import { LogoMark } from "@/components/LogoMark"
import { ProjectConversationsTree } from "@/components/project/ProjectConversationsTree"
import { Avatar } from "@/components/ui/avatar-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Popover } from "@/components/ui/popover-clean"
import { useIsMobile } from "@/hooks/use-mobile"
import { useAuth } from "@/lib/auth-context"

export const SIDEBAR_COOKIE_NAME = "sidebar_state"

export function AccountMenu({ expanded = false }: { expanded?: boolean }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const name = user?.name || user?.email || t("common.guest")
  return (
    <div className="relative min-w-0">
      <button
        ref={trigger}
        type="button"
        className="ui-as-side__item"
        aria-label={name}
        title={name}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen(!open)}
      >
        <span className="grid size-6 shrink-0 place-items-center">
          {user ? <Avatar name={name} size={24} /> : <User size={18} />}
        </span>
        {expanded && <span className="ui-as-side__label truncate">{name}</span>}
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        width={user ? 296 : 160}
        align="start"
        aria-label={name}
        focusOnOpen
      >
        <AccountConsole
          onClose={() => {
            trigger.current?.focus()
            setOpen(false)
          }}
        />
      </Popover>
    </div>
  )
}

export function AppSidebar({ defaultOpen }: { defaultOpen: boolean }) {
  const { t } = useTranslation()
  const mobile = useIsMobile()
  const projectMatch = useMatch({ from: "/_app/projects/$id", shouldThrow: false })
  const activeProjectId = projectMatch?.params.id
  const activeConversationId = (projectMatch?.search as { c?: string } | undefined)?.c
  const [expanded, setExpanded] = useState(defaultOpen)
  const [mobileOpen, setMobileOpen] = useState(false)
  function toggle() {
    if (mobile) setMobileOpen(!mobileOpen)
    else {
      document.cookie = `${SIDEBAR_COOKIE_NAME}=${!expanded}; path=/; max-age=604800`
      setExpanded(!expanded)
    }
  }
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "b") {
        event.preventDefault()
        toggle()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [mobile, mobileOpen, expanded])
  const nav = (
    <nav className="flex flex-col gap-1">
      {(
        [
          { to: "/home", label: t("nav.home"), Icon: Home },
          { to: "/projects", label: t("nav.myProjects"), Icon: FolderKanban },
        ] as const
      ).map(({ to, label, Icon }) => (
        <Link
          key={to}
          to={to}
          title={label}
          aria-label={label}
          className="ui-as-side__item"
          activeProps={{ "aria-current": "page" }}
          onClick={() => setMobileOpen(false)}
        >
          <Icon size={16} />
          <span className="ui-as-side__label truncate">{label}</span>
        </Link>
      ))}
    </nav>
  )
  if (mobile)
    return (
      <Dialog
        open={mobileOpen}
        onOpenChange={setMobileOpen}
        title="RookieCut"
        closeLabel={t("common.close")}
      >
        {nav}
        {activeProjectId ? (
          <ProjectConversationsTree
            projectId={activeProjectId}
            activeConversationId={activeConversationId}
            onNavigate={() => setMobileOpen(false)}
          />
        ) : null}
        <AccountMenu expanded />
      </Dialog>
    )
  return (
    <aside className="ui-as-side" data-expanded={expanded}>
      <div className="flex items-center">
        <div aria-hidden={!expanded} className="ui-as-side__label flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
          <LogoMark className="size-6" />
          <span className="text-sm font-medium">RookieCut</span>
        </div>
        <IconButton
          className="ui-as-side__toggle"
          aria-expanded={expanded}
          icon={<PanelLeft />}
          label={t(expanded ? "a11y.toggleSidebar" : "a11y.openSidebar")}
          onClick={toggle}
        />
      </div>
      {nav}
      {expanded && activeProjectId ? (
        <ProjectConversationsTree
          projectId={activeProjectId}
          activeConversationId={activeConversationId}
        />
      ) : null}
      <div className="mt-auto">
        <AccountMenu expanded={expanded} />
      </div>
    </aside>
  )
}
