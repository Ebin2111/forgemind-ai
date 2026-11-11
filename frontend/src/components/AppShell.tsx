"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import Icon from "@/components/Icon";
import Logo from "@/components/Logo";
import Sidebar from "@/components/Sidebar";
import { getSession, logout, type Session } from "@/lib/auth";
import { ICON_CLOSE, ICON_MENU } from "@/lib/nav";
import { SessionProvider } from "@/lib/session";

/** Pages that render on their own, without the sidebar (and without needing a session). */
const BARE_ROUTES = ["/login"];

type Gate = { state: "checking" } | { state: "offline" } | { state: "ok"; session: Session };

/** Sidebar + content frame around every page. On phones the sidebar is a slide-in drawer. */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [gate, setGate] = useState<Gate>({ state: "checking" });
  const bare = BARE_ROUTES.some((r) => pathname === r || pathname.startsWith(`${r}/`));

  // Nothing but the login page is shown until the server confirms who is signed in.
  const check = useCallback(async () => {
    setGate({ state: "checking" });
    try {
      const session = await getSession();
      if (!session) {
        router.replace(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
        return;
      }
      setGate({ state: "ok", session });
    } catch {
      setGate({ state: "offline" });
    }
  }, [router]);

  useEffect(() => {
    if (bare) setGate({ state: "checking" }); // the next visit to an app page asks the server again
    else void check();
  }, [bare, check]);

  async function signOut() {
    await logout();
    setGate({ state: "checking" });
    router.replace("/login");
  }

  // Close the drawer after navigating.
  useEffect(() => setOpen(false), [pathname]);

  // Escape closes the drawer; the page behind it does not scroll while it is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  if (bare) return <>{children}</>;

  if (gate.state !== "ok") {
    return (
      <div className="splash" role="status" aria-live="polite">
        <Logo size={44} tagline={false} />
        {gate.state === "checking" ? (
          <p>Checking your session…</p>
        ) : (
          <>
            <p>Can&apos;t reach the backend.</p>
            <p className="splash-hint">Start it from the project folder:</p>
            <code>python -m uvicorn backend.app.main:app --port 8000</code>
            <button type="button" onClick={() => void check()}>Try again</button>
          </>
        )}
      </div>
    );
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>

      <header className="mobilebar">
        <button
          type="button"
          className="iconbtn"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          aria-controls="app-sidebar"
        >
          <Icon d={open ? ICON_CLOSE : ICON_MENU} size={22} />
        </button>
        <Logo size={28} tagline={false} />
      </header>

      <div id="app-sidebar" className={`sidebar-wrap${open ? " open" : ""}`}>
        <Sidebar onNavigate={() => setOpen(false)} session={gate.session} onSignOut={signOut} />
      </div>
      {open && <button type="button" className="scrim" aria-label="Close menu" onClick={() => setOpen(false)} />}

      <main id="main" className="main">
        <SessionProvider value={gate.session}>{children}</SessionProvider>
      </main>
    </div>
  );
}