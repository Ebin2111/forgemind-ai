"use client";

import { createContext, useContext } from "react";

import type { Session } from "@/lib/auth";

/** Who is signed in, for pages that show or hide controls by role. Provided by AppShell. */
const SessionContext = createContext<Session | null>(null);

export const SessionProvider = SessionContext.Provider;

export function useSession(): { session: Session | null; isAdmin: boolean } {
  const session = useContext(SessionContext);
  // The server enforces every rule; this only decides what to show. Without a session nothing admin-only is shown.
  return { session, isAdmin: session?.role === "admin" };
}