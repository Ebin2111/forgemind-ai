"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { errorMessage, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";

const MIN_PASSWORD = 8;

/** Your own details and a way to change your password. */
export default function AccountPage() {
  const { session } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  useEffect(() => { document.title = "Account | ForgeMind AI"; }, []);

  const mismatch = again !== "" && again !== next;
  const valid = current !== "" && next.length >= MIN_PASSWORD && next === again;

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await api.changePassword(current, next);
      setDone(true);
      setCurrent(""); setNext(""); setAgain("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <header className="page-header">
        <div>
          <h1 className="page-title">My account</h1>
          <p className="page-sub">Your sign-in details.</p>
        </div>
      </header>

      <div className="panels two">
        <section className="panel">
          <h2 style={{ marginTop: 0 }}>Profile</h2>
          <p><span className="muted">Name</span><br />{session?.name || "-"}</p>
          <p><span className="muted">Email</span><br />{session?.email}</p>
          <p><span className="muted">Role</span><br /><span className={`badge${session?.role === "admin" ? " ok" : ""}`}>{titleCase(session?.role ?? "technician")}</span></p>
        </section>

        <section className="panel">
          <h2 style={{ marginTop: 0 }}>Change password</h2>
          {session && !session.auth_required ? (
            <p className="muted">Sign-in is switched off on this server, so there is no password to change.</p>
          ) : (
            <form className="form-grid" onSubmit={submit}>
              <label className="field"><span>Current password</span>
                <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required maxLength={200} />
              </label>
              <label className="field"><span>New password</span>
                <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required minLength={MIN_PASSWORD} maxLength={200} placeholder={`At least ${MIN_PASSWORD} characters`} />
              </label>
              <label className="field"><span>New password again</span>
                <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required maxLength={200} aria-invalid={mismatch} />
              </label>
              {mismatch && <p className="error">The two new passwords are not the same.</p>}
              {error && <p className="error" role="alert">{error}</p>}
              {done && <p role="status" style={{ color: "var(--ok)" }}>Password changed.</p>}
              <div className="btn-row"><button type="submit" disabled={busy || !valid}>{busy ? "Saving…" : "Change password"}</button></div>
            </form>
          )}
        </section>
      </div>
    </div>
  );
}