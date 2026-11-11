/** Sidebar navigation. Set `ready: true` when a page ships; until then it shows as "Soon" (no dead links). */
export interface NavItem {
  href: string;
  label: string;
  /** SVG path data, drawn on a 24x24 grid with a 1.8 stroke. */
  icon: string;
  ready: boolean;
  /** Shown to administrators only. */
  adminOnly?: boolean;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Overview",
    items: [
      { href: "/", label: "Dashboard", ready: true, icon: "M3 3h8v8H3zM13 3h8v5h-8zM13 10h8v11h-8zM3 13h8v8H3z" },
    ],
  },
  {
    title: "Assistant",
    items: [
      { href: "/chat", label: "Chat", ready: true, icon: "M21 12a8 8 0 01-11.6 7.1L3 21l1.9-5.4A8 8 0 1121 12z" },
      { href: "/troubleshooting", label: "Troubleshooting", ready: true, icon: "M12 3l10 18H2zM12 10v5M12 18h.01" },
    ],
  },
  {
    title: "Plant",
    items: [
      {
        href: "/equipment", label: "Equipment", ready: true,
        icon: "M12 15a3 3 0 100-6 3 3 0 000 6zM12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1",
      },
      { href: "/maintenance", label: "Maintenance", ready: true, icon: "M9 4h6v3H9zM7 5H5v16h14V5h-2M9 14l2 2 4-4" },
      { href: "/analytics", label: "Analytics", ready: true, icon: "M4 20V10M10 20V4M16 20v-7M22 20H2" },
    ],
  },
  {
    title: "Knowledge",
    items: [
      { href: "/documents", label: "Documents", ready: true, icon: "M6 3h9l5 5v13H6zM14 3v6h6M9 13h8M9 17h8" },
      { href: "/upload", label: "Upload", ready: true, adminOnly: true, icon: "M12 16V4M7 9l5-5 5 5M4 20h16" },
      {
        href: "/knowledge-base", label: "Knowledge Base", ready: true,
        icon: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
      },
    ],
  },
  {
    title: "Administration",
    items: [
      {
        href: "/users", label: "Users", ready: true, adminOnly: true,
        icon: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM22 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8",
      },
    ],
  },
];

export const ICON_MENU = "M3 6h18M3 12h18M3 18h18";
export const ICON_CLOSE = "M6 6l12 12M18 6L6 18";

export function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}