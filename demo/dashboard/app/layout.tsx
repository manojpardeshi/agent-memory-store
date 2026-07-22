import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Memory Handoff Lab",
  description: "Measured model-switching and context-transfer evidence.",
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
