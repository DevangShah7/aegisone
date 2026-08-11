import type { Metadata } from "next";
import "./globals.css";
import { APP_NAME, APP_TAGLINE, DEVELOPER_NAME } from "@/lib/branding";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: {
    default: `${APP_NAME} — ${APP_TAGLINE}`,
    template: `%s — ${APP_NAME}`,
  },
  description: `${APP_NAME}: ${APP_TAGLINE}. Developed by ${DEVELOPER_NAME}.`,
  applicationName: APP_NAME,
  authors: [{ name: DEVELOPER_NAME }],
  generator: "Next.js",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};

export const viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}