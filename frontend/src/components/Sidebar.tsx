"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import Icon from "@/components/Icon";
import Logo from "@/components/Logo";
import { api } from "@/lib/api";
import type { Session } from "@/lib/auth";
import { NAV_SECTIONS, isActive } from "@/lib/nav";
import { titleCase } from "@/lib/format";

/** Main navigation. Pages that are not built yet are shown but not clickable. */
export default function Sidebar({ onNavigate, session, onSignOut }: {
  onNavigate?: () => void;
  session?: Session;
  onSignOut?: () => void;
}) {
  const pathname = usePathname() ?? "";
  const isAdmin = !session || session.role === "admin"; // no session = sign-in off; the server decides anyway

  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-brand">
        <Link href="/" aria-label="ForgeMind AI, home" onClick={onNavigate}>
          <Logo size={34} tagline={false} />
        </Link>
      </div>

      {NAV_SECTIONS.map((section) => ({ ...section, items: section.items.filter((i) => !i.adminOnly || isAdmin) }))
        .filter((section) => section.items.length > 0)
        .map((section) => (
        <div className="nav-section" key={section.title}>
          <p className="nav-heading">{section.title}</p>
          <ul>
            {section.items.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  {item.ready ? (
                    <Link
                      href={item.href}
                      className={`nav-link${active ? " active" : ""}`}
                      aria-current={active ? "page" : undefined}
                      onClick={onNavigate}
                    >
                      <Icon d={item.icon} />
                      {item.label}
                    </Link>
                  ) : (
                    <span className="nav-link disabled" aria-disabled="true" title="Coming soon">
                      <Icon d={item.icon} />
                      {item.label}
                      <span className="nav-soon">Soon</span>
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}

      <div className="sidebar-foot">
        {session && session.auth_required && (
          <div className="sidebar-user">
            <Link href="/account" onClick={onNavigate} title={`${session.email}: account and password`}
                  style={{ display: "grid", minWidth: 0, textDecoration: "none", color: "var(--text)" }}>
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text)" }}>{session.name || session.email}</span>
              <span style={{ fontSize: 11.5, color: session.role === "admin" ? "var(--ok)" : "var(--muted)" }}>{titleCase(session.role)}</span>
            </Link>
            <button type="button" className="ghost small" onClick={onSignOut}>Sign out</button>
          </div>
        )}
        <a href={api.docsUrl} target="_blank" rel="noreferrer">
          API documentation
        </a>
        <p>Engineering Intelligence. Empowering Industry.</p>
      </div>
    </nav>
  );
}