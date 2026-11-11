import type { Metadata, Viewport } from "next";

import "@fontsource/barlow/400.css";
import "@fontsource/barlow/500.css";
import "@fontsource/barlow/600.css";
import "@fontsource/barlow/700.css";
import "./globals.css";

import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "ForgeMind AI",
  description: "Industrial Intelligence Copilot. Engineering Intelligence. Empowering Industry.",
};

export const viewport: Viewport = {
  themeColor: "#071a30",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}