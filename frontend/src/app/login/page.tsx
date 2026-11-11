import type { Metadata } from "next";
import { Suspense } from "react";

import "@fontsource/barlow/400.css";
import "@fontsource/barlow/500.css";
import "@fontsource/barlow/600.css";
import "@fontsource/barlow/700.css";

import Logo from "@/components/Logo";
import LoginForm from "./LoginForm";
import styles from "./login.module.css";

export const metadata: Metadata = {
  title: "Sign in | ForgeMind AI",
  description: "Sign in to the ForgeMind AI Industrial Intelligence Copilot.",
};

export default function LoginPage() {
  return (
    <main className={styles.page}>
      <section className={styles.hero} aria-hidden="true" />

      <section className={styles.panel}>
        <div className={styles.card}>
          <div className={styles.brand}>
            <Logo />
          </div>
          <h1 className={styles.title}>Login Portal</h1>
          <Suspense fallback={null}>
            <LoginForm />
          </Suspense>
        </div>
        <p className={styles.tagline}>Engineering Intelligence. Empowering Industry.</p>
      </section>
    </main>
  );
}