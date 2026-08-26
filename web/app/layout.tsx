import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://abfall-mcp.alpaycelik.dev"),
  title: {
    default: "Abfall MCP — Deutsche Abfuhrtermine für KI-Assistenten",
    template: "%s · Abfall MCP",
  },
  description:
    "Ein öffentlicher MCP-Server für Abfuhrtermine aus den Portalen deutscher Entsorgungsträger.",
  alternates: {
    canonical: "/",
    languages: { "de-DE": "/", "en-US": "/en/" },
  },
  openGraph: {
    type: "website",
    locale: "de_DE",
    alternateLocale: "en_US",
    url: "/",
    siteName: "Abfall MCP",
    title: "Abfall MCP — Abfuhrtermine für KI-Assistenten",
    description:
      "995 Entsorgungsträger, ein öffentlicher MCP-Endpoint und eine klare Regel: nachfragen statt raten.",
  },
  twitter: {
    card: "summary",
    title: "Abfall MCP",
    description: "German waste collection dates for AI assistants.",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#08090b" },
    { media: "(prefers-color-scheme: light)", color: "#f6f6f3" },
  ],
};

const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });
const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
});

const themeBootstrap = `try{var t=localStorage.getItem("theme");if(!t){t=matchMedia("(prefers-color-scheme: light)").matches?"light":"dark"}if(t==="dark"){document.documentElement.classList.add("dark")}document.documentElement.style.colorScheme=t}catch(e){}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="de" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
