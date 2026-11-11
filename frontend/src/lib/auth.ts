/**
 * Sign-in client.
 *
 * Expects  POST {API}/api/auth/login  with JSON { email, password, remember }.
 * On success the server must set an HttpOnly session cookie (we send `credentials: "include"`),
 * so no token is ever stored in JavaScript-readable storage.
 */
import { API_BASE as BASE } from "@/lib/config";


export type AuthErrorKind = "invalid" | "rate_limited" | "unavailable" | "network" | "server";

export class AuthError extends Error {
  constructor(message: string, readonly kind: AuthErrorKind) {
    super(message);
    this.name = "AuthError";
  }
}

export interface Credentials {
  email: string;
  password: string;
  remember: boolean;
}

export async function login({ email, password, remember }: Credentials): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, remember }),
    });
  } catch {
    throw new AuthError("Can't reach the server. Check your connection and try again.", "network");
  }
  if (res.ok) return;

  if (res.status === 400 || res.status === 401 || res.status === 403 || res.status === 422)
    throw new AuthError("Incorrect email or password, or the account is switched off.", "invalid");
  if (res.status === 429)
    throw new AuthError("Too many attempts. Please wait a minute and try again.", "rate_limited");
  if (res.status === 404 || res.status === 405 || res.status === 501 || res.status === 503)
    throw new AuthError("Sign-in isn't available on this server yet. Contact your administrator.", "unavailable");
  throw new AuthError("Something went wrong on the server. Please try again.", "server");
}

/** Only follow in-app paths after sign-in ("/chat"), never other sites ("//evil.com", "https://..."). */
export function safeNextPath(next: string | null | undefined): string {
  return next && /^\/(?![/\\])/.test(next) ? next : "/";
}

export type Role = "admin" | "technician";

export interface Session {
  email: string;
  name: string;
  role: Role;
  auth_required: boolean;
}

/**
 * Who is signed in. Returns the session, or null when nobody is (HTTP 401).
 * Throws AuthError("network") when the backend cannot be reached, so callers can tell "signed out" from "server down".
 */
export async function getSession(): Promise<Session | null> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/auth/me`, { credentials: "include", cache: "no-store" });
  } catch {
    throw new AuthError("Can't reach the server.", "network");
  }
  if (res.status === 401) return null;
  if (!res.ok) throw new AuthError("The server returned an error.", "server");
  return (await res.json()) as Session;
}

/** End the session. Never throws: the cookie is cleared by the server when it is reachable. */
export async function logout(): Promise<void> {
  try {
    await fetch(`${BASE}/api/auth/logout`, { method: "POST", credentials: "include" });
  } catch {
    // Offline: the user still leaves the app; the cookie expires on its own.
  }
}