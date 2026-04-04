import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OVERLORD11 — Tactical Command Interface",
  description: "Full-stack AI platform with internal execution engine",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" style={{ height: "100%", overflow: "hidden" }}>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body style={{ height: "100%", overflow: "hidden", background: "var(--bg-base)" }}>
        {children}
      </body>
    </html>
  );
}
