"use client";

import {
  ArrowDown,
  ArrowRight,
  CalendarDays,
  Check,
  Clipboard,
  Database,
  ExternalLink,
  GitBranch,
  MapPin,
  Moon,
  Network,
  Search,
  ShieldCheck,
  Unplug,
  Sun,
} from "lucide-react";
import { useEffect, useState } from "react";

import { AnimatedGridPattern } from "@/components/ui/animated-grid-pattern";
import { BorderBeam } from "@/components/ui/border-beam";
import { NumberTicker } from "@/components/ui/number-ticker";
import {
  AnimatedSpan,
  Terminal,
  TypingAnimation,
} from "@/components/ui/terminal";
import { cn } from "@/lib/utils";

type Language = "de" | "en";

const ENDPOINT = "https://abfall-mcp.alpaycelik.dev/mcp";

const snippets = {
  codex: `[mcp_servers.abfall]\nurl = "${ENDPOINT}"`,
  claude: `{
  "mcpServers": {
    "abfall": {
      "url": "${ENDPOINT}"
    }
  }
}`,
  json: `{
  "mcpServers": {
    "abfall": {
      "type": "http",
      "url": "${ENDPOINT}"
    }
  }
}`,
  curl: `curl -X POST ${ENDPOINT} \\
  -H "Content-Type: application/json" \\
  -H "Accept: application/json, text/event-stream" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"hello","version":"1.0"}}}'`,
};

const tools = [
  {
    name: "abfuhrtermine",
    icon: CalendarDays,
    de: "Findet den zuständigen Träger zu einer Adresse und liefert die nächsten Abfuhrtermine.",
    en: "Finds the responsible provider for an address and returns upcoming collection dates.",
    input: 'adresse: "Kirchstraße 5, 48282 Emsdetten"',
  },
  {
    name: "finde_traeger",
    icon: Search,
    de: "Sucht direkt nach Orts-, Landkreis- oder Betriebsnamen, ganz ohne Geocoding.",
    en: "Searches directly by city, district, or operator name without geocoding.",
    input: 'suchbegriff: "Kreis Steinfurt"',
  },
  {
    name: "traeger_details",
    icon: Database,
    de: "Zeigt Portal, erwartete Argumente, Beispiele und offene Pflichtangaben.",
    en: "Shows the portal, required arguments, examples, and missing mandatory fields.",
    input: 'traeger_id: "..."',
  },
  {
    name: "abfuhrtermine_fuer_traeger",
    icon: Network,
    de: "Fragt einen bekannten Träger gezielt ab und löst dessen Adressdialog auf.",
    en: "Queries a known provider directly and resolves its address selection flow.",
    input: 'traeger_id: "...", argumente: { ... }',
  },
  {
    name: "abdeckung",
    icon: MapPin,
    de: "Gibt einen transparenten Überblick über erfasste Träger und Datenquellen.",
    en: "Returns a transparent overview of registered providers and data sources.",
    input: "keine Argumente / no arguments",
  },
];

const copy = {
  de: {
    nav: ["Verbindung", "Tools", "Über den Server"],
    eyebrow: "ÖFFENTLICHER MCP-SERVER · DEUTSCHLAND",
    titleA: "Abfuhrtermine für deinen",
    titleB: "KI-Assistenten.",
    intro:
      "Ein offener MCP-Server verbindet KI-Assistenten mit den Abfallkalendern deutscher Städte und Landkreise — direkt aus den Portalen der zuständigen Entsorgungsträger.",
    connect: "MCP verbinden",
    explore: "Tools ansehen",
    labels: ["Öffentlich", "5 Tools", "1 Resource", "Kein API-Key"],
    terminalPrompt: "Wann wird bei mir die Biotonne geleert?",
    terminalCall: "→ abfuhrtermine({ adresse: \"Kirchstraße 5, Emsdetten\" })",
    terminalResult: "✓ Nächster Termin: Dienstag, 1. September",
    live: "Live Endpoint",
    checking: "Status wird geprüft",
    online: "Betriebsbereit",
    offline: "Status nicht erreichbar",
    endpointNote: "Streamable HTTP · Protokoll 2025-11-25",
    statProviders: "Entsorgungsträger",
    statSources: "Datenquellen",
    statTools: "MCP-Tools",
    connectionEyebrow: "01 / VERBINDUNG",
    connectionTitle: "In zwei Minuten startklar.",
    connectionText:
      "Der Server ist öffentlich erreichbar. Füge den Endpoint zu deinem MCP-Client hinzu — ohne Installation, Konto oder API-Key.",
    copied: "Kopiert",
    copy: "Kopieren",
    configHint:
      "Konfiguration speichern und den Client neu starten. Danach steht der Server als „abfall“ zur Verfügung.",
    flowEyebrow: "02 / SO FUNKTIONIERT’S",
    flowTitle: "Eine Frage rein. Verlässliche Termine raus.",
    flowText:
      "Zwischen Alltagssprache und kommunalen Portalen liegt ein vorsichtiger Auflösungsprozess. Unsichere Zuordnungen werden nicht versteckt.",
    flow: [
      ["Adresse", "Der Assistent übergibt Ort, Straße oder vollständige Adresse."],
      ["Geocoding", "Nominatim normalisiert den Ort und prüft Postleitzahl sowie Straße."],
      ["Zuständigkeit", "Der passende Entsorgungsträger wird aus 995 Einträgen ermittelt."],
      ["Portal", "Die originale kommunale Datenquelle wird live abgefragt."],
      ["Termine", "Sortierte Abfuhrdaten kommen strukturiert zum Assistenten zurück."],
    ],
    principleTitle: "Nachfragen statt raten.",
    principleText:
      "Liegt eine Zuordnung unter der Sicherheitsschwelle, liefert der Server konkrete Auswahlmöglichkeiten zurück. So wird aus einer falschen Adresse nicht unbemerkt ein plausibel wirkender Kalender.",
    toolsEyebrow: "02 / TOOLS & RESOURCE",
    toolsTitle: "Klein genug, um klar zu bleiben.",
    toolsText:
      "Fünf fokussierte Tools decken den Weg von der freien Adressfrage bis zur gezielten Provider-Abfrage ab.",
    invoke: "Beispiel",
    resource: "Resource",
    resourceText:
      "Alle erfassten Entsorgungsträger als maschinenlesbare Liste mit ID, Name und Portal.",
    coverageEyebrow: "03 / ÜBER DEN SERVER",
    coverageTitle: "Kommunal organisiert. Gemeinsam zugänglich.",
    coverageText:
      "Deutschland hat keine zentrale Abfall-API. Dieser Server vereinheitlicht 150 unterschiedliche Datenquellen hinter einer einzigen, offenen Schnittstelle.",
    coverageCards: [
      ["Direkt", "Adresse wird eindeutig erkannt und Termine werden sofort geliefert."],
      ["Mit Rückfrage", "Der Assistent bittet um Ortsteil, Straße oder eine Auswahl."],
      ["Transparent", "Quelle, Portal und verwendete Argumente bleiben in der Antwort sichtbar."],
    ],
    openTitle: "Offen gebaut. Selbst hostbar.",
    openText:
      "Quellcode, Container und Registry-Eintrag sind öffentlich. Der gehostete Endpoint ist der schnellste Start; für volle Kontrolle kannst du denselben Server selbst betreiben.",
    source: "Quellcode ansehen",
    registry: "MCP Registry",
    finalEyebrow: "DEINE TONNE WARTET NICHT",
    finalTitle: "Gib deinem Assistenten einen Kalender.",
    finalText: "Ein Endpoint. Fünf Tools. Fast tausend kommunale Entsorgungsträger.",
    footer: "Offener MCP-Server für deutsche Abfuhrtermine.",
  },
  en: {
    nav: ["Connect", "Tools", "About"],
    eyebrow: "PUBLIC MCP SERVER · GERMANY",
    titleA: "Collection dates for your",
    titleB: "AI assistant.",
    intro:
      "An open MCP server connects AI assistants to waste collection calendars across Germany — sourced directly from the responsible municipal providers.",
    connect: "Connect MCP",
    explore: "Explore tools",
    labels: ["Public", "5 tools", "1 resource", "No API key"],
    terminalPrompt: "When will my organic waste be collected?",
    terminalCall: "→ abfuhrtermine({ adresse: \"Kirchstraße 5, Emsdetten\" })",
    terminalResult: "✓ Next collection: Tuesday, September 1",
    live: "Live endpoint",
    checking: "Checking status",
    online: "Operational",
    offline: "Status unavailable",
    endpointNote: "Streamable HTTP · Protocol 2025-11-25",
    statProviders: "waste providers",
    statSources: "data sources",
    statTools: "MCP tools",
    connectionEyebrow: "01 / CONNECTION",
    connectionTitle: "Ready in two minutes.",
    connectionText:
      "The server is publicly available. Add the endpoint to your MCP client — no installation, account, or API key required.",
    copied: "Copied",
    copy: "Copy",
    configHint:
      "Save the configuration and restart your client. The server will then be available as “abfall”.",
    flowEyebrow: "02 / HOW IT WORKS",
    flowTitle: "One question in. Reliable dates out.",
    flowText:
      "A careful resolution process sits between natural language and municipal portals. Uncertain matches are never hidden.",
    flow: [
      ["Address", "The assistant sends a city, street, or complete address."],
      ["Geocoding", "Nominatim normalizes the location and validates postcode and street."],
      ["Responsibility", "The matching provider is selected from 995 entries."],
      ["Portal", "The original municipal data source is queried live."],
      ["Dates", "Sorted collection dates return to the assistant as structured data."],
    ],
    principleTitle: "Ask instead of guessing.",
    principleText:
      "When a match falls below the confidence threshold, the server returns concrete choices. A wrong address can never silently turn into a plausible-looking calendar.",
    toolsEyebrow: "02 / TOOLS & RESOURCE",
    toolsTitle: "Small enough to stay clear.",
    toolsText:
      "Five focused tools cover the path from a free-form address question to a targeted provider query.",
    invoke: "Example",
    resource: "Resource",
    resourceText:
      "Every registered waste provider as a machine-readable list with ID, name, and portal.",
    coverageEyebrow: "03 / ABOUT",
    coverageTitle: "Organized locally. Accessible together.",
    coverageText:
      "Germany has no central waste collection API. This server unifies 150 different data sources behind a single open interface.",
    coverageCards: [
      ["Direct", "The address resolves clearly and dates are returned immediately."],
      ["With a question", "The assistant asks for a district, street, or explicit choice."],
      ["Transparent", "Source, portal, and arguments used remain visible in the response."],
    ],
    openTitle: "Openly built. Self-hostable.",
    openText:
      "Source code, container, and registry entry are public. The hosted endpoint is the fastest start; run the same server yourself when you need full control.",
    source: "View source",
    registry: "MCP Registry",
    finalEyebrow: "YOUR BIN WON’T WAIT",
    finalTitle: "Give your assistant a calendar.",
    finalText: "One endpoint. Five tools. Nearly one thousand municipal waste providers.",
    footer: "Open MCP server for German waste collection dates.",
  },
} as const;

const tabLabels = { codex: "Codex", claude: "Claude", json: "JSON", curl: "cURL" };
type SnippetKey = keyof typeof snippets;

function CopyButton({ value, language }: { value: string; language: Language }) {
  const [copied, setCopied] = useState(false);
  const t = copy[language];

  async function handleCopy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <button className="copy-button" onClick={handleCopy} type="button">
      {copied ? <Check size={15} /> : <Clipboard size={15} />}
      {copied ? t.copied : t.copy}
    </button>
  );
}

function Status({ language }: { language: Language }) {
  const [status, setStatus] = useState<"checking" | "online" | "offline">("checking");
  const t = copy[language];

  useEffect(() => {
    let active = true;
    fetch("/health", { signal: AbortSignal.timeout(5000) })
      .then((response) => {
        if (active) setStatus(response.ok ? "online" : "offline");
      })
      .catch(() => {
        if (active) setStatus("offline");
      });
    return () => {
      active = false;
    };
  }, []);

  const label = status === "online" ? t.online : status === "offline" ? t.offline : t.checking;
  return (
    <span className={cn("live-status", `is-${status}`)}>
      <span className="status-dot" />
      {label}
    </span>
  );
}

function ConnectionPanel({ language }: { language: Language }) {
  const [activeTab, setActiveTab] = useState<SnippetKey>("codex");
  const t = copy[language];
  const snippet = snippets[activeTab];

  return (
    <div className="connection-panel">
      <div className="connection-tabs" role="tablist" aria-label="MCP clients">
        {(Object.keys(tabLabels) as SnippetKey[]).map((key) => (
          <button
            aria-selected={activeTab === key}
            className={cn("connection-tab", activeTab === key && "is-active")}
            key={key}
            onClick={() => setActiveTab(key)}
            role="tab"
            type="button"
          >
            {tabLabels[key]}
          </button>
        ))}
      </div>
      <div className="code-window">
        <div className="code-window-topline">
          <span>{activeTab === "codex" ? "~/.codex/config.toml" : activeTab}</span>
          <CopyButton value={snippet} language={language} />
        </div>
        <pre><code>{snippet}</code></pre>
      </div>
      <p className="config-hint"><Check size={16} aria-hidden="true" />{t.configHint}</p>
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const timer = window.setTimeout(
      () =>
        setTheme(
          document.documentElement.classList.contains("dark") ? "dark" : "light",
        ),
      0,
    );
    return () => window.clearTimeout(timer);
  }, []);

  function toggleTheme() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    document.documentElement.style.colorScheme = next;
    localStorage.setItem("theme", next);
  }

  return (
    <button
      aria-label="Toggle theme"
      className="theme-toggle"
      onClick={toggleTheme}
      type="button"
    >
      {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
    </button>
  );
}

export function LandingPage({ language }: { language: Language }) {
  const t = copy[language];
  const localePath = language === "de" ? "/en/" : "/";
  const localeLabel = language === "de" ? "EN" : "DE";

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  return (
    <div className="site-shell" lang={language}>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="Abfall MCP home">
          <span className="brand-mark" aria-hidden="true"><span /><span /><span /></span>
          <span>ABFALL</span><span className="brand-slash">{"//MCP"}</span>
        </a>
        <nav className="desktop-nav" aria-label="Primary navigation">
          {t.nav.map((item, index) => (
            <a href={["#connection", "#tools", "#about"][index]} key={item}>{item}</a>
          ))}
        </nav>
        <div className="header-actions">
          <a className="language-switch" href={localePath}>
            <span>{language.toUpperCase()}</span><ArrowRight size={13} aria-hidden="true" /><strong>{localeLabel}</strong>
          </a>
          <ThemeToggle />
          <a className="github-link" href="https://github.com/AlpayC/mcp-abfall" target="_blank" rel="noreferrer" aria-label="GitHub repository"><GitBranch size={18} /></a>
        </div>
      </header>

      <main id="top">
        <section className="hero section-frame">
          <AnimatedGridPattern className="hero-grid" maxOpacity={0.13} numSquares={22} width={56} height={56} duration={5} />
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-pulse" />{t.eyebrow}</div>
            <h1>{t.titleA}<span>{t.titleB}</span></h1>
            <p className="hero-intro">{t.intro}</p>
            <div className="hero-actions">
              <a className="primary-button" href="#connection"><Unplug size={17} />{t.connect}<ArrowDown size={16} /></a>
              <a className="text-button" href="#tools">{t.explore}<ArrowRight size={16} /></a>
            </div>
            <div className="badge-row" aria-label="Server facts">
              {t.labels.map((label, index) => <span key={label}>{index === 0 && <span className="badge-dot" />}{label}</span>)}
            </div>
          </div>

          <div className="hero-demo">
            <div className="terminal-label"><span>ASSISTANT / MCP</span><span className="terminal-id">01</span></div>
            <Terminal className="hero-terminal" sequence startOnView={false}>
              <TypingAnimation className="terminal-question" duration={24} startOnView={false}>{`› ${t.terminalPrompt}`}</TypingAnimation>
              <AnimatedSpan className="terminal-call">{t.terminalCall}</AnimatedSpan>
              <AnimatedSpan className="terminal-result">{t.terminalResult}</AnimatedSpan>
            </Terminal>
            <div className="endpoint-card">
              <BorderBeam colorFrom="var(--primary)" colorTo="var(--accent)" duration={8} size={70} />
              <div className="endpoint-head"><span>{t.live}</span><Status language={language} /></div>
              <div className="endpoint-value"><code>{ENDPOINT}</code><CopyButton value={ENDPOINT} language={language} /></div>
              <span className="endpoint-note">{t.endpointNote}</span>
            </div>
          </div>
        </section>

        <section className="stats-strip" aria-label="Coverage statistics">
          <div><strong><NumberTicker value={995} /></strong><span>{t.statProviders}</span></div>
          <div><strong><NumberTicker value={150} /></strong><span>{t.statSources}</span></div>
          <div><strong><NumberTicker value={5} /></strong><span>{t.statTools}</span></div>
          <div className="stats-protocol"><strong>2025-11-25</strong><span>MCP protocol</span></div>
        </section>

        <section className="content-section section-frame" id="connection">
          <div className="section-intro sticky-intro"><span className="section-eyebrow">{t.connectionEyebrow}</span><h2>{t.connectionTitle}</h2><p>{t.connectionText}</p></div>
          <ConnectionPanel language={language} />
        </section>

        <section className="tools-section section-frame" id="tools">
          <div className="section-intro wide-intro"><span className="section-eyebrow">{t.toolsEyebrow}</span><h2>{t.toolsTitle}</h2><p>{t.toolsText}</p></div>
          <div className="tool-list">
            {tools.map((tool, index) => {
              const Icon = tool.icon;
              return <article className="tool-row" key={tool.name}><span className="tool-index">0{index + 1}</span><div className="tool-icon"><Icon size={21} strokeWidth={1.8} /></div><div className="tool-copy"><h3>{tool.name}</h3><p>{tool[language]}</p></div><div className="tool-example"><span>{t.invoke}</span><code>{tool.input}</code></div></article>;
            })}
          </div>
          <article className="resource-card"><div className="resource-badge">R</div><div><span>{t.resource}</span><h3>abfall://traeger</h3><p>{t.resourceText}</p></div><Database size={42} strokeWidth={1.2} /></article>
        </section>

        <section className="about-section section-frame" id="about">
          <div className="section-intro compact-intro"><span className="section-eyebrow">{t.coverageEyebrow}</span><h2>{t.coverageTitle}</h2><p>{t.coverageText}</p></div>
          <div className="about-grid">
            <article>
              <div className="about-icon"><ShieldCheck size={21} /></div>
              <span>CONFIDENCE FIRST</span>
              <h3>{t.principleTitle}</h3>
              <p>{t.principleText}</p>
            </article>
            <article>
              <div className="about-icon"><Network size={21} /></div>
              <span>995 × 150</span>
              <h3>{t.coverageCards[2][0]}</h3>
              <p>{t.coverageCards[2][1]}</p>
            </article>
            <article>
              <div className="about-icon"><GitBranch size={21} /></div>
              <span>OPEN SOURCE · MIT</span>
              <h3>{t.openTitle}</h3>
              <p>{t.openText}</p>
              <div className="about-links"><a href="https://github.com/AlpayC/mcp-abfall" target="_blank" rel="noreferrer">{t.source}<ExternalLink size={13} /></a><a href="https://registry.modelcontextprotocol.io/" target="_blank" rel="noreferrer">{t.registry}<ExternalLink size={13} /></a></div>
            </article>
          </div>
        </section>
      </main>

      <footer className="site-footer section-frame">
        <div className="brand footer-brand"><span className="brand-mark" aria-hidden="true"><span /><span /><span /></span><span>ABFALL</span><span className="brand-slash">{"//MCP"}</span></div>
        <p>{t.footer}</p>
        <div><a href="/health">Status</a><a href={ENDPOINT}>Endpoint</a><a href="https://github.com/AlpayC/mcp-abfall" target="_blank" rel="noreferrer">GitHub</a><a href={localePath}>{localeLabel}</a></div>
      </footer>
    </div>
  );
}
