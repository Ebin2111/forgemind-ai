"use client";

import { FormEvent, useEffect, useId, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AuthError, getSession, login, safeNextPath } from "@/lib/auth";
import styles from "./login.module.css";

const EMAIL_PATTERN = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;
const MIN_PASSWORD = 8;

function Icon({ d }: { d: string }) {
  return (
    <svg className={styles.icon} width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

export default function LoginForm() {
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const id = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false); // off by default: the sign-in ends when the browser closes
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Already signed in (or sign-in is switched off on the server): go straight to the app.
  useEffect(() => {
    let cancelled = false;
    getSession().then((s) => { if (s && !cancelled) router.replace(next); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [router, next]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setNotice(null);

    const trimmed = email.trim();
    const errors: typeof fieldErrors = {};
    if (!EMAIL_PATTERN.test(trimmed)) errors.email = "Enter a valid email address, like name@example.com.";
    if (!password) errors.password = "Enter your password.";
    else if (password.length < MIN_PASSWORD) errors.password = `Password must be at least ${MIN_PASSWORD} characters.`;
    setFieldErrors(errors);
    setFormError(null);
    if (errors.email || errors.password) return;

    setBusy(true);
    try {
      await login({ email: trimmed, password, remember });
      router.replace(next);
    } catch (err) {
      setFormError(err instanceof AuthError ? err.message : "Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={onSubmit} noValidate>
      <div className={styles.field}>
        <label htmlFor={`${id}-email`} className={styles.label}>
          <Icon d="M3 6h18v12H3zM3 7l9 6 9-6" /> Email Address
        </label>
        <input
          id={`${id}-email`}
          className={styles.input}
          type="email"
          name="email"
          autoComplete="username"
          inputMode="email"
          placeholder="Enter your email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={!!fieldErrors.email}
          aria-describedby={fieldErrors.email ? `${id}-email-err` : undefined}
          disabled={busy}
        />
        {fieldErrors.email && <p id={`${id}-email-err`} className={styles.fieldError}>{fieldErrors.email}</p>}
      </div>

      <div className={styles.field}>
        <label htmlFor={`${id}-password`} className={styles.label}>
          <Icon d="M6 11h12v9H6zM8 11V8a4 4 0 018 0v3" /> Password
        </label>
        <div className={styles.passwordWrap}>
          <input
            id={`${id}-password`}
            className={styles.input}
            type={showPassword ? "text" : "password"}
            name="password"
            autoComplete="current-password"
            placeholder="Enter your password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={!!fieldErrors.password}
            aria-describedby={fieldErrors.password ? `${id}-password-err` : undefined}
            disabled={busy}
          />
          <button
            type="button"
            className={styles.eye}
            onClick={() => setShowPassword((v) => !v)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            aria-pressed={showPassword}
          >
            <Icon d={showPassword ? "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z"
                                  : "M3 3l18 18M10.6 6.1A9.8 9.8 0 0112 6c6 0 10 6 10 6a17 17 0 01-3.2 3.7M6.6 6.7C3.8 8.6 2 12 2 12s4 7 10 7c1.6 0 3-.4 4.2-1M9.9 9.9a3 3 0 004.2 4.2"} />
          </button>
        </div>
        {fieldErrors.password && <p id={`${id}-password-err`} className={styles.fieldError}>{fieldErrors.password}</p>}
      </div>

      <div className={styles.options}>
        <label className={styles.check}>
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} disabled={busy} />
          Remember Me
        </label>
        <button
          type="button"
          className={styles.link}
          onClick={() => setNotice("Password resets are handled by your administrator. Please contact them.")}
        >
          Forgot password?
        </button>
      </div>

      <div aria-live="polite">
        {formError && <p className={styles.formError} role="alert">{formError}</p>}
        {notice && <p className={styles.notice}>{notice}</p>}
      </div>

      <button type="submit" className={styles.submit} disabled={busy}>
        {busy ? "Signing in…" : <>Sign In <span aria-hidden="true">→</span></>}
      </button>

      <div className={styles.divider}><span>or continue with</span></div>

      <div className={styles.social}>
        <button type="button" className={styles.socialBtn} disabled title="Single sign-on isn't set up yet">
          Continue with Google
        </button>
        <button type="button" className={styles.socialBtn} disabled title="Single sign-on isn't set up yet">
          Continue with Microsoft
        </button>
      </div>
    </form>
  );
}