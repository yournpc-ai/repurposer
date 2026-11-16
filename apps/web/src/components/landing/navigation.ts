export type NavMenuId = "features" | "pricing" | "faq"

export type NavMenu = {
  id: NavMenuId
  items: { key: string }[]
}

export const NAV_MENUS: NavMenu[] = [
  {
    id: "features",
    items: [
      { key: "conversation" },
      { key: "animation" },
      { key: "mixedMedia" },
      { key: "revision" },
    ],
  },
  {
    id: "pricing",
    items: [
      { key: "topup" },
      { key: "noSubscription" },
      { key: "noReset" },
      { key: "packages" },
    ],
  },
  {
    id: "faq",
    items: [
      { key: "inputs" },
      { key: "revision" },
      { key: "videoTypes" },
      { key: "download" },
    ],
  },
]
