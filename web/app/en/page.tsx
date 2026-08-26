import type { Metadata } from "next";

import { LandingPage } from "@/components/landing-page";

export const metadata: Metadata = {
  title: "German waste collection dates for AI assistants",
  description:
    "A public MCP server for waste collection dates from German municipal providers.",
  alternates: {
    canonical: "/en/",
    languages: { "de-DE": "/", "en-US": "/en/" },
  },
  openGraph: {
    locale: "en_US",
    url: "/en/",
    title: "Abfall MCP — German waste collection dates for AI assistants",
    description:
      "995 providers, one public MCP endpoint, and one clear rule: ask instead of guessing.",
  },
};

export default function EnglishHome() {
  return <LandingPage language="en" />;
}
