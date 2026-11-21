import { Link } from "@tanstack/react-router"
import { FolderKanban, Home, PanelLeft, User } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

import { AccountConsole } from "@/components/account-console"
import { LogoMark } from "@/components/LogoMark"
import { Avatar } from "@/components/ui/avatar-clean"
import { Dialog } from "@/components/ui/dialog-clean"
import { IconButton } from "@/components/ui/icon-button-clean"
import { Popover } from "@/components/ui/popover-clean"
import { useIsMobile } from "@/hooks/use-mobile"
import { getUser } from "@/lib/auth"
import { useAuth } from "@/lib/auth-context"

export const SIDEBAR_COOKIE_NAME = "sidebar_state"

export function AccountMenu({ expanded = false }: { expanded?: boolean }) {
  const { t } = useTranslation()
  const { isAuthenticated } = useAuth()
  const trigger = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])
  const user = mounted && isAuthenticated ? getUser() : null
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
        {user ? <Avatar name={name} size={24} /> : <User size={18} />}
        {expanded && <span className="truncate">{name}</span>}
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        width={256}
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
          <Icon size={18} />
          {(expanded || mobile) && label}
        </Link>
      ))}
    </nav>
  )
  if (mobile)
    return (
      <Dialog
        open={mobileOpen}
        onOpenChange={setMobileOpen}
        title="Rookie Cut"
        closeLabel={t("common.close")}
      >
        {nav}
        <AccountMenu expanded />
      </Dialog>
    )
  return (
    <aside className="ui-as-side" data-expanded={expanded}>
      <div className="flex items-center gap-2">
        {expanded && (
          <>
            <LogoMark className="size-6" />
            <span className="flex-1 text-sm font-medium">Rookie Cut</span>
          </>
        )}
        <IconButton
          icon={<PanelLeft />}
          label={t(expanded ? "a11y.toggleSidebar" : "a11y.openSidebar")}
          onClick={toggle}
        />
      </div>
      {nav}
      <div className="mt-auto">
        <AccountMenu expanded={expanded} />
      </div>
    </aside>
  )
}
