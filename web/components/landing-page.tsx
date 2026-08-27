"use client";

import {
  ArrowDown,
  ArrowUpRight,
  Check,
  Clipboard,
  ExternalLink,
  GitBranch,
  Moon,
  Search,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { AnimatedShinyText } from "@/components/ui/animated-shiny-text";
import { BorderBeam } from "@/components/ui/border-beam";
import { GridPattern } from "@/components/ui/grid-pattern";
import { Marquee } from "@/components/ui/marquee";
import { NumberTicker } from "@/components/ui/number-ticker";
import {
  AnimatedSpan,
  Terminal,
  TypingAnimation,
} from "@/components/ui/terminal";
import { cn } from "@/lib/utils";

type Language = "de" | "en";

const ENDPOINT = "https://abfall-mcp.alpaycelik.dev/mcp";
const HOST = "abfall-mcp.alpaycelik.dev";
const REPO = "https://github.com/AlpayC/mcp-abfall";
const SOURCE = `${REPO}/blob/main/src/mcp_abfall/server.py`;
const VERSION = "v0.1.0";
const PROTOCOL = "2025-11-25";
const PROVIDERS = 995;
const SOURCES = 150;

/* Datenbasis: das Upstream-Projekt, aus dem die Traegerliste stammt. */
const UPSTREAM = "https://github.com/mampfes/hacs_waste_collection_schedule";
const UPSTREAM_NAME = "hacs_waste_collection_schedule";
const UPSTREAM_VERSION = "v2.32.0";

/* -------------------------------------------------------------------------
   Client-Zeilen. Eine Zeile pro Client, damit das Panel kompakt bleibt.
   ------------------------------------------------------------------------- */

const snippets = {
  Claude: `claude mcp add --transport http abfall ${ENDPOINT}`,
  Codex: `codex mcp add abfall --url ${ENDPOINT}`,
  ".mcp.json": `{ "mcpServers": { "abfall": { "url": "${ENDPOINT}" } } }`,
  Docker: `docker run -p 8000:8000 ghcr.io/alpayc/mcp-abfall:latest`,
  curl: `curl -X POST ${ENDPOINT} \\
  -H "Content-Type: application/json" \\
  -H "Accept: application/json, text/event-stream" \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`,
} as const;

type SnippetKey = keyof typeof snippets;

/* -------------------------------------------------------------------------
   Tools. Argumente, Art und Quellzeile entsprechen src/mcp_abfall/server.py:
   "read" kommt aus read_only_hint, "portal"/"registry" aus open_world_hint.
   ------------------------------------------------------------------------- */

type Arg = { n: string; t: string; req?: boolean; de: string; en: string };
type Kind = "portal" | "registry";

const tools: {
  name: string;
  kind: Kind;
  line: number;
  de: string;
  en: string;
  args: Arg[];
  call: string;
}[] = [
  {
    name: "abfuhrtermine",
    kind: "portal",
    line: 209,
    de: "Ermittelt den zuständigen Träger zu einer Adresse und liefert dessen Abfuhrtermine.",
    en: "Resolves the responsible authority for an address and returns its collection dates.",
    args: [
      { n: "adresse", t: "string", req: true, de: "Adresse oder Ort", en: "Address or town" },
      { n: "strasse", t: "string", de: "Falls nicht in der Adresse", en: "If not part of the address" },
      { n: "hausnummer", t: "string", de: "Hausnummer", en: "House number" },
      { n: "von / bis", t: "string", de: "Zeitraum, JJJJ-MM-TT", en: "Range, YYYY-MM-DD" },
      { n: "abfallarten", t: "string[]", de: "Teilwörter genügen", en: "Substrings work" },
      { n: "limit", t: "integer", de: "Standard 25", en: "Default 25" },
    ],
    call: `abfuhrtermine({\n  adresse: "Kirchstraße 5, 48282 Emsdetten",\n  abfallarten: ["Bio"]\n})`,
  },
  {
    name: "finde_traeger",
    kind: "registry",
    line: 365,
    de: "Sucht Entsorgungsträger nach Orts- oder Betriebsnamen, ohne Geocoding.",
    en: "Searches waste authorities by place or operator name, without geocoding.",
    args: [
      { n: "suchbegriff", t: "string", req: true, de: "Ort, Landkreis oder Betrieb", en: "Town, district or operator" },
      { n: "limit", t: "integer", de: "Standard 10", en: "Default 10" },
    ],
    call: `finde_traeger({ suchbegriff: "Kreis Steinfurt" })`,
  },
  {
    name: "traeger_details",
    kind: "registry",
    line: 389,
    de: "Zeigt Portal, erwartete Argumente, Vorbelegung und Beispielorte eines Trägers.",
    en: "Shows one authority's portal, expected arguments, presets and example places.",
    args: [
      { n: "traeger_id", t: "string", req: true, de: "ID aus finde_traeger", en: "ID from finde_traeger" },
    ],
    call: `traeger_details({ traeger_id: "abfall_io.egst-…" })`,
  },
  {
    name: "abfuhrtermine_fuer_traeger",
    kind: "portal",
    line: 420,
    de: "Fragt einen bekannten Träger gezielt ab — der Weg, um eine Rückfrage zu beantworten.",
    en: "Queries a known authority directly — the way to answer a follow-up question.",
    args: [
      { n: "traeger_id", t: "string", req: true, de: "ID aus finde_traeger", en: "ID from finde_traeger" },
      { n: "argumente", t: "object", de: "Argumente der Datenquelle", en: "Arguments of the data source" },
      { n: "adresse", t: "string", de: "Ergänzt Fehlendes", en: "Fills in what is missing" },
      { n: "von / bis", t: "string", de: "Zeitraum", en: "Range" },
      { n: "abfallarten", t: "string[]", de: "Nur diese Arten", en: "Only these types" },
      { n: "limit", t: "integer", de: "Standard 25", en: "Default 25" },
    ],
    call: `abfuhrtermine_fuer_traeger({\n  traeger_id: "…",\n  argumente: { ort: "Ahlen" }\n})`,
  },
  {
    name: "abdeckung",
    kind: "registry",
    line: 491,
    de: "Zählt erfasste Träger und Datenquellen.",
    en: "Counts registered authorities and data sources.",
    args: [],
    call: `abdeckung()`,
  },
];

const resources = [
  {
    title: "Entsorgungsträger",
    uri: "abfall://traeger",
    mime: "application/json",
    line: 518,
    de: "Alle erfassten Träger mit ID, Name und Portal — dieselbe Liste, die das Verzeichnis unten durchsucht.",
    en: "Every registered authority with ID, name and portal — the same list the directory below searches.",
  },
];

/* ------------------------------------------------------------------------- */

const copy = {
  de: {
    eyebrow: "Öffentlicher MCP-Server · Deutschland",
    headline: "Abfuhrtermine für",
    headlineAccent: "deinen KI-Assistenten.",
    ctaPrimary: "Server verbinden",
    ctaSecondary: "Tools ansehen",
    scrollHint: "Endpoint, Tools und Abdeckung",
    connect: "anschluss",
    connectNote: "Endpoint in den MCP-Client eintragen, Client neu starten. Danach steht der Server als „abfall“ bereit.",
    lede: "Abfuhrtermine aus den Portalen deutscher Entsorgungsträger — als MCP-Server für KI-Assistenten. Öffentlich, ohne Konto und ohne API-Key.",
    online: "erreichbar",
    offline: "nicht erreichbar",
    checking: "prüfe",
    traeger: "Träger",
    quellen: "Quellen",
    toolsWord: "Tools",
    resourceWord: "Resource",
    protokoll: "Protokoll",
    copy: "Kopieren",
    copied: "Kopiert",
    built: "Datenbasis:",
    demo: "beispiel",
    ask: "Wann wird bei mir die Biotonne geleert?",
    call: '→ abfuhrtermine({ adresse: "Kirchstraße 5, Emsdetten" })',
    result: "✓ Dienstag, 1. September · Biomüll · EGST Steinfurt",
    toolsLabel: "tools",
    toolsNote: "Tool- und Feldnamen sind deutsch, weil die Domäne es ist. Alle Tools lesen nur; „portal“ fragt dabei ein kommunales Portal an, „registry“ antwortet aus der mitgelieferten Trägerliste.",
    schema: "Schema",
    invocation: "Aufruf",
    viewSource: "Quelltext",
    filterAll: "alle",
    searchTools: "Tools durchsuchen …",
    noTools: "Kein Tool passt zu dieser Auswahl.",
    resourceLabel: "ressourcen",
    resourceNote: "Wird über resources/read gelesen, nicht als Tool aufgerufen.",
    coverage: "abdeckung",
    coverageNote: "Deutschland hat keine bundesweite Abfall-Schnittstelle. Rund 400 Träger betreiben eigene Portale hinter einer Handvoll Plattformen.",
    finderPlaceholder: "Verzeichnis filtern — Träger, Kreis oder Stadt …",
    finderHint: "Zuständig ist meist der Landkreis, nicht die Gemeinde. Etwa Steinfurt, Köln oder AWM.",
    finderLoading: "Verzeichnis wird geladen …",
    finderEmpty: "Kein Träger heisst",
    finderEmptyNote: "Das Verzeichnis führt Trägernamen. Wohnst du in einer kleinen Gemeinde, suche nach deinem Landkreis — oder frag den Server direkt, der löst die Adresse selbst auf.",
    finderOf: "von",
    finderMatch: "Treffer",
    finderMatches: "Treffer",
    finderAll: "Träger, alphabetisch",
    resolve: "auflösung",
    resolveNote: "Zwischen Alltagssprache und kommunalem Portal liegt eine Kette, die an jeder Stelle abbrechen darf.",
    chain: [
      ["Adresse", "Ort, Straße oder vollständige Anschrift."],
      ["Geocoding", "Nominatim prüft PLZ und Ort."],
      ["Zuständigkeit", "Passender Träger aus 995."],
      ["Portal", "Kommunale Quelle, live."],
      ["Termine", "Sortiert zurück."],
    ],
    ruleTitle: "Nachfragen statt raten",
    ruleText: "Ist eine Zuordnung nicht sicher genug, kommen konkrete Auswahlmöglichkeiten zurück statt eines Ergebnisses. Ein falsch geratener Ort liefert sonst klaglos den Kalender der Nachbargemeinde — falsch, aber unauffällig.",
    changelog: "Changelog",
    issues: "Issues",
    sourceWord: "Quelltext",
    builtOn: "gebaut auf",
  },
  en: {
    eyebrow: "Public MCP server · Germany",
    headline: "Collection dates for",
    headlineAccent: "your AI assistant.",
    ctaPrimary: "Connect the server",
    ctaSecondary: "See the tools",
    scrollHint: "Endpoint, tools and coverage",
    connect: "connect",
    connectNote: "Add the endpoint to your MCP client and restart it. The server then shows up as “abfall”.",
    lede: "Waste collection dates from the portals of German municipal authorities — as an MCP server for AI assistants. Public, no account, no API key.",
    online: "reachable",
    offline: "unreachable",
    checking: "checking",
    traeger: "authorities",
    quellen: "sources",
    toolsWord: "tools",
    resourceWord: "resource",
    protokoll: "protocol",
    copy: "Copy",
    copied: "Copied",
    built: "Data source:",
    demo: "example",
    ask: "When is my organic waste collected?",
    call: '→ abfuhrtermine({ adresse: "Kirchstraße 5, Emsdetten" })',
    result: "✓ Tuesday, 1 September · organic waste · EGST Steinfurt",
    toolsLabel: "tools",
    toolsNote: "Tool and field names are German because the domain is. All tools only read; “portal” queries a municipal portal, “registry” answers from the bundled authority list.",
    schema: "schema",
    invocation: "invocation",
    viewSource: "view source",
    filterAll: "all",
    searchTools: "Search tools …",
    noTools: "No tool matches this selection.",
    resourceLabel: "resources",
    resourceNote: "Read via resources/read, not called as a tool.",
    coverage: "coverage",
    coverageNote: "Germany has no nationwide waste API. Around 400 authorities run their own portals on top of a handful of platforms.",
    finderPlaceholder: "Filter the directory — authority, district or city …",
    finderHint: "Responsibility usually sits with the district, not the town. Try Steinfurt, Köln or AWM.",
    finderLoading: "Loading directory …",
    finderEmpty: "No authority is called",
    finderEmptyNote: "The directory lists authority names. If you live in a small municipality, search for your district — or just ask the server, which resolves the address itself.",
    finderOf: "of",
    finderMatch: "match",
    finderMatches: "matches",
    finderAll: "authorities, alphabetical",
    resolve: "resolution",
    resolveNote: "Between plain language and a municipal portal sits a chain that may stop at any step.",
    chain: [
      ["Address", "Town, street or full address."],
      ["Geocoding", "Nominatim validates postcode and place."],
      ["Responsibility", "The matching authority out of 995."],
      ["Portal", "Municipal source, live."],
      ["Dates", "Sorted, back to the assistant."],
    ],
    ruleTitle: "Ask instead of guessing",
    ruleText: "When a match is not confident enough, the server returns concrete options instead of a result. A wrongly guessed town would otherwise cheerfully return the neighbouring municipality's calendar — wrong, but unremarkable.",
    changelog: "Changelog",
    issues: "Issues",
    sourceWord: "Source",
    builtOn: "built on",
  },
} as const;

/* ------------------------------------------------------------------------- */

function CopyButton({ value, language }: { value: string; language: Language }) {
  const [copied, setCopied] = useState(false);
  const t = copy[language];
  return (
    <button
      className="copy"
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      }}
    >
      {copied ? <Check size={12} /> : <Clipboard size={12} />}
      {copied ? t.copied : t.copy}
    </button>
  );
}

function useHealth() {
  const [state, setState] = useState<"checking" | "online" | "offline">("checking");
  useEffect(() => {
    let active = true;
    fetch("/health", { signal: AbortSignal.timeout(5000) })
      .then((r) => active && setState(r.ok ? "online" : "offline"))
      .catch(() => active && setState("offline"));
    return () => {
      active = false;
    };
  }, []);
  return state;
}

function ConnectPanel({ language }: { language: Language }) {
  const [tab, setTab] = useState<SnippetKey>("Claude");
  return (
    <div className="panel">
      <BorderBeam colorFrom="var(--primary)" colorTo="var(--accent)" duration={10} size={80} />
      <div className="panel-top">
        <span className="lights"><i /><i /><i /></span>
        <span className="panel-url">{HOST}/mcp</span>
      </div>
      <div className="tabs" role="tablist" aria-label="MCP clients">
        {(Object.keys(snippets) as SnippetKey[]).map((key) => (
          <button
            aria-selected={tab === key}
            className={cn("tab", tab === key && "is-active")}
            key={key}
            onClick={() => setTab(key)}
            role="tab"
            type="button"
          >
            {key}
          </button>
        ))}
      </div>
      <div className="panel-body">
        <pre><code>{snippets[tab]}</code></pre>
        <CopyButton value={snippets[tab]} language={language} />
      </div>
    </div>
  );
}

function Head({ label, count }: { label: string; count?: string }) {
  return (
    <div className="sec-head">
      <h2>{label}</h2>
      {count && <span className="sec-count">{count}</span>}
    </div>
  );
}

/* --- Tools ---------------------------------------------------------------- */

/* "Aufruf" und "Schema" schalten denselben Kasten um, damit die Karte
   geschlossen kompakt bleibt. */
function ToolCard({
  tool,
  language,
}: {
  tool: (typeof tools)[number];
  language: Language;
}) {
  const t = copy[language];
  const [panel, setPanel] = useState<"call" | "schema" | null>(null);
  const hasSchema = tool.args.length > 0;

  return (
    <article className="card">
      <span className="card-name">{tool.name}</span>
      <p className="card-desc">{tool[language]}</p>

      <div className="card-foot">
        <span className="tag">read</span>
        <span className={cn("tag", tool.kind === "portal" ? "tag-alt" : "tag-mute")}>
          {tool.kind}
        </span>
        <button
          aria-expanded={panel === "call"}
          className={cn("foot-btn", panel === "call" && "is-on")}
          onClick={() => setPanel(panel === "call" ? null : "call")}
          type="button"
        >
          · {t.invocation}
        </button>
        {hasSchema && (
          <button
            aria-expanded={panel === "schema"}
            className={cn("foot-btn", panel === "schema" && "is-on")}
            onClick={() => setPanel(panel === "schema" ? null : "schema")}
            type="button"
          >
            · {t.schema}
          </button>
        )}
        <a className="foot-src" href={`${SOURCE}#L${tool.line}`} rel="noreferrer" target="_blank">
          {t.viewSource}
          <ExternalLink size={10} />
        </a>
      </div>

      {panel === "schema" && hasSchema && (
        <div className="args">
          {tool.args.map((a) => (
            <div className="arg" key={a.n}>
              <span className="arg-name">
                {a.n}
                {a.req && <span className="arg-req"> *</span>}
              </span>
              <span className="arg-type">{a.t}</span>
              <span className="arg-desc">{a[language]}</span>
            </div>
          ))}
        </div>
      )}

      {panel === "call" && <code className="call">{tool.call}</code>}
    </article>
  );
}

function ToolsSection({ language }: { language: Language }) {
  const t = copy[language];
  const [kind, setKind] = useState<Kind | "all">("all");
  const [query, setQuery] = useState("");

  const needle = query.trim().toLowerCase();
  const shown = tools.filter(
    (tool) =>
      (kind === "all" || tool.kind === kind) &&
      (needle.length === 0 ||
        tool.name.toLowerCase().includes(needle) ||
        tool[language].toLowerCase().includes(needle)),
  );

  const counts = {
    all: tools.length,
    portal: tools.filter((x) => x.kind === "portal").length,
    registry: tools.filter((x) => x.kind === "registry").length,
  };

  return (
    <section className="sec" id="tools">
      <Head label={t.toolsLabel} count={String(tools.length)} />
      <p className="sec-note">{t.toolsNote}</p>

      <div className="toolbar">
        <div className="chips">
          {(["all", "portal", "registry"] as const).map((key) => (
            <button
              className={cn("chip-filter", kind === key && "is-active")}
              key={key}
              onClick={() => setKind(key)}
              type="button"
            >
              {key === "all" ? t.filterAll : key}
              <i>{counts[key]}</i>
            </button>
          ))}
        </div>

        <div className="tool-search">
          <Search size={14} aria-hidden="true" />
          <input
            aria-label={t.searchTools}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t.searchTools}
            type="text"
            value={query}
          />
          {query && (
            <button aria-label="clear" onClick={() => setQuery("")} type="button">✕</button>
          )}
        </div>
      </div>

      {shown.length > 0 ? (
        <div className="cards">
          {shown.map((tool) => (
            <ToolCard key={tool.name} language={language} tool={tool} />
          ))}
        </div>
      ) : (
        <p className="note">{t.noTools}</p>
      )}
    </section>
  );
}

/* --- Trägerindex ---------------------------------------------------------- */

type Entry = { t: string; s: string; o?: string[] };

function fold(v: string) {
  return v
    .toLowerCase()
    .replaceAll("ä", "ae")
    .replaceAll("ö", "oe")
    .replaceAll("ü", "ue")
    .replaceAll("ß", "ss")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "");
}

function Mark({ text, needle }: { text: string; needle: string }) {
  const at = fold(text).indexOf(needle);
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark>{text.slice(at, at + needle.length)}</mark>
      {text.slice(at + needle.length)}
    </>
  );
}

function Finder({ language }: { language: Language }) {
  const t = copy[language];
  const [query, setQuery] = useState("");
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const asked = useRef(false);

  // Sofort laden: eine leere Liste waere eine schlechtere Auskunft als die
  // ersten Eintraege.
  useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    fetch("/traeger.json")
      .then((r) => r.json())
      .then((d) => setEntries(d.providers as Entry[]))
      .catch(() => setEntries([]));
  }, []);

  const needle = fold(query.trim());

  const hits = useMemo(() => {
    if (!entries) return [];
    if (needle.length < 2) return entries.map((e) => ({ e, rank: 0, place: undefined }));
    const out: { e: Entry; rank: number; place?: string }[] = [];
    for (const e of entries) {
      const title = fold(e.t);
      let rank = title.startsWith(needle) ? 1 : title.includes(needle) ? 3 : 99;
      let place: string | undefined;
      for (const o of e.o ?? []) {
        const f = fold(o);
        if (!f.includes(needle)) continue;
        // Ein Treffer auf dem Beispielort wiegt schwerer: gesucht wird der
        // eigene Wohnort, nicht der Name des Betriebs.
        const r = f.startsWith(needle) ? 0 : 2;
        if (r < rank) rank = r;
        place ??= o;
      }
      if (rank < 99) out.push({ e, rank, place });
    }
    out.sort((a, b) => a.rank - b.rank || a.e.t.localeCompare(b.e.t));
    return out;
  }, [entries, needle]);

  const shown = hits.slice(0, 6);
  const searching = needle.length >= 2;

  return (
    <div>
      <div className="finder">
        <Search size={15} aria-hidden="true" />
        <input
          aria-label={t.finderPlaceholder}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t.finderPlaceholder}
          type="text"
          value={query}
        />
        {query && (
          <button aria-label="clear" onClick={() => setQuery("")} type="button">✕</button>
        )}
      </div>

      {entries === null ? (
        <p className="note">{t.finderLoading}</p>
      ) : shown.length > 0 ? (
        <>
          <ul className="hits">
            {shown.map(({ e, place }) => (
              <li className="hit" key={`${e.t}·${e.s}`}>
                <span className="hit-name">
                  {searching ? <Mark text={e.t} needle={needle} /> : e.t}
                </span>
                <span className="hit-src">{e.s}</span>
                {place && (
                  <span className="hit-place"><Mark text={place} needle={needle} /></span>
                )}
              </li>
            ))}
          </ul>
          <p className="note">
            {!searching
              ? `${entries.length} ${t.finderAll} — ${t.finderHint}`
              : hits.length > shown.length
                ? `${shown.length} ${t.finderOf} ${hits.length} ${t.finderMatches}`
                : `${hits.length} ${hits.length === 1 ? t.finderMatch : t.finderMatches}`}
          </p>
        </>
      ) : (
        <p className="note">
          {t.finderEmpty} <b>{query.trim()}</b>. {t.finderEmptyNote}
        </p>
      )}
    </div>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const id = window.setTimeout(
      () => setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light"),
      0,
    );
    return () => window.clearTimeout(id);
  }, []);
  return (
    <button
      aria-label="Toggle theme"
      className="chip chip-icon"
      onClick={() => {
        const next = theme === "dark" ? "light" : "dark";
        setTheme(next);
        document.documentElement.classList.toggle("dark", next === "dark");
        document.documentElement.style.colorScheme = next;
        localStorage.setItem("theme", next);
      }}
      type="button"
    >
      {theme === "dark" ? <Sun size={13} /> : <Moon size={13} />}
    </button>
  );
}

const bandNames = [
  "AWB Köln", "Stadtreinigung Hamburg", "Berliner Stadtreinigungsbetriebe",
  "Kreis Steinfurt", "AWM München", "Bremer Stadtreinigung", "EBU Ulm",
  "ZKE Saarbrücken", "AWG Wuppertal", "Stadtreinigung Dresden",
  "Abfallwirtschaftsbetriebe Münster", "EDG Entsorgung Dortmund",
  "Landkreis Rosenheim", "ART Trier", "Kreis Gütersloh GEG",
  "Abfallwirtschaft Stadt Nürnberg", "SAB Magdeburg", "sds Schwerin",
];

/* ------------------------------------------------------------------------- */

export function LandingPage({ language }: { language: Language }) {
  const t = copy[language];
  const health = useHealth();
  const other = language === "de" ? "/en/" : "/";
  const otherLabel = language === "de" ? "EN" : "DE";
  const statusLabel =
    health === "online" ? t.online : health === "offline" ? t.offline : t.checking;

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  return (
    <div className="doc" lang={language}>
      <header className="bar">
        <div className="wrap bar-in">
          <a className="mark" href="#top"><span>abfall</span><span>/mcp</span></a>
          <div className="bar-actions">
            <a className="chip" href={other}>{otherLabel}</a>
            <ThemeToggle />
            <a aria-label="GitHub" className="chip chip-icon" href={REPO} rel="noreferrer" target="_blank">
              <GitBranch size={13} />
            </a>
          </div>
        </div>
      </header>

      <div className="hero-bg" aria-hidden="true">
        <GridPattern className="hero-grid" width={64} height={64} />
        <span className="glow" />
      </div>

      <main className="wrap" id="top">
        <section className="masthead">
          <div className="badge-row">
            <span className={cn("status-pill", `is-${health}`)}>
              <span className="ping" />
              <AnimatedShinyText>{statusLabel}</AnimatedShinyText>
            </span>
            <span className="label-mono">{t.eyebrow}</span>
          </div>

          <div className="title-line">
            <h1>
              <span className="block">{t.headline}</span>
              <span className="grad">{t.headlineAccent}</span>
            </h1>
            <span className="version">{VERSION}</span>
          </div>

          <p className="lede">{t.lede}</p>

          <div className={cn("facts", `is-${health}`)}>
            <span className="live-dot" />
            <span>{statusLabel}</span>
            <span className="sep">·</span>
            <span><b><NumberTicker value={PROVIDERS} /></b> {t.traeger}</span>
            <span className="sep">·</span>
            <span><b><NumberTicker value={SOURCES} /></b> {t.quellen}</span>
            <span className="sep">·</span>
            <span><b>{tools.length}</b> {t.toolsWord}</span>
            <span className="sep">·</span>
            <span><b>{resources.length}</b> {t.resourceWord}</span>
            <span className="sep">·</span>
            <span>{t.protokoll} <span className="val">{PROTOCOL}</span></span>
            <span className="sep">·</span>
            <a href={REPO} rel="noreferrer" target="_blank">
              github <b>AlpayC/mcp-abfall</b>
              <ExternalLink size={11} />
            </a>
          </div>

          <div className="cta-row">
            <a className="btn btn-primary" href="#connect">
              {t.ctaPrimary}
              <ArrowUpRight size={16} />
            </a>
            <a className="btn btn-ghost" href="#tools">
              {t.ctaSecondary}
              <ArrowDown size={16} />
            </a>
            <span className="icon-row">
              <a aria-label="GitHub" className="icon-btn" href={REPO} rel="noreferrer" target="_blank">
                <GitBranch size={18} strokeWidth={1.75} />
              </a>
              <a aria-label="MCP Registry" className="icon-btn" href="https://registry.modelcontextprotocol.io/" rel="noreferrer" target="_blank">
                <ExternalLink size={18} strokeWidth={1.75} />
              </a>
            </span>
          </div>

          <div className="scroll-hint">
            <ArrowDown size={14} />
            <span className="label-mono">{t.scrollHint}</span>
            <span className="line" />
          </div>
        </section>

        <section className="sec" id="connect">
          <Head label={t.connect} count={PROTOCOL} />
          <p className="sec-note">{t.connectNote}</p>
          <ConnectPanel language={language} />
          <a className="built" href={UPSTREAM} rel="noreferrer" target="_blank">
            <AnimatedShinyText>
              {t.built} {UPSTREAM_NAME} {UPSTREAM_VERSION} · MIT
            </AnimatedShinyText>
            <ExternalLink size={10} />
          </a>
        </section>

        <section className="sec">
          <Head label={t.demo} />
          <div className="demo">
            <Terminal className="demo-term" sequence startOnView>
              <TypingAnimation className="t-ask" duration={26} startOnView={false}>
                {`› ${t.ask}`}
              </TypingAnimation>
              <AnimatedSpan className="t-call">{t.call}</AnimatedSpan>
              <AnimatedSpan className="t-ok">{t.result}</AnimatedSpan>
            </Terminal>
          </div>
        </section>

        <ToolsSection language={language} />

        <section className="sec" id="resources">
          <Head label={t.resourceLabel} count={String(resources.length)} />
          <p className="sec-note">{t.resourceNote}</p>
          <div className="cards">
            {resources.map((r) => (
              <article className="card card-res" key={r.uri}>
                <span className="card-name">{r.title}</span>
                <p className="card-desc">{r[language]}</p>
                <dl className="res-meta">
                  <dt>uri</dt>
                  <dd>{r.uri}</dd>
                  <dt>mime</dt>
                  <dd>{r.mime}</dd>
                </dl>
                <div className="card-foot">
                  <a className="foot-src" href={`${SOURCE}#L${r.line}`} rel="noreferrer" target="_blank">
                    {t.viewSource}
                    <ExternalLink size={10} />
                  </a>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="sec" id="coverage">
          <Head label={t.coverage} count={`${PROVIDERS} × ${SOURCES}`} />
          <p className="sec-note">{t.coverageNote}</p>
          <Finder language={language} />
          <div className="band">
            <Marquee pauseOnHover style={{ ["--duration" as string]: "46s" }}>
              {bandNames.map((n) => <span className="band-item" key={n}>{n}</span>)}
            </Marquee>
          </div>
        </section>

        <section className="sec">
          <Head label={t.resolve} />
          <p className="sec-note">{t.resolveNote}</p>
          <ol className="chain">
            {t.chain.map(([step, text]) => (
              <li key={step}><dt>{step}</dt><dd>{text}</dd></li>
            ))}
          </ol>
          <div className="rule">
            <ShieldCheck size={17} aria-hidden="true" />
            <div>
              <h3>{t.ruleTitle}</h3>
              <p>{t.ruleText}</p>
            </div>
          </div>
        </section>
      </main>

      <footer className="wrap foot">
        <div className="foot-links">
          <a href={`${REPO}/blob/main/CHANGELOG.md`} rel="noreferrer" target="_blank">{t.changelog}</a>
          <span className="sep">·</span>
          <a href={`${REPO}/releases/tag/${VERSION}`} rel="noreferrer" target="_blank">{VERSION}</a>
          <span className="sep">·</span>
          <a href={`${REPO}/issues`} rel="noreferrer" target="_blank">{t.issues}</a>
          <span className="sep">·</span>
          <a href={REPO} rel="noreferrer" target="_blank">{t.sourceWord}</a>
          <span className="sep">·</span>
          <a href="/health">/health</a>
          <span className="sep">·</span>
          <a href={other}>{otherLabel}</a>
        </div>

        <div className="foot-links foot-right">
          <span>{t.builtOn}</span>
          <a href={UPSTREAM} rel="noreferrer" target="_blank">
            {UPSTREAM_NAME} {UPSTREAM_VERSION}
          </a>
          <span className="sep">·</span>
          <a href={UPSTREAM} rel="noreferrer" target="_blank">GitHub</a>
        </div>
      </footer>
    </div>
  );
}
