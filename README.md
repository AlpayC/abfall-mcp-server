# mcp-abfall

*English · [Deutsch](README.de.md)*

[![CI](https://github.com/AlpayC/mcp-abfall/actions/workflows/ci.yml/badge.svg)](https://github.com/AlpayC/mcp-abfall/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Providers: 995](https://img.shields.io/badge/waste%20authorities-995-green.svg)](data/providers.json)

MCP server for the waste collection calendars of German cities and districts.
Looks up collection dates — residual waste, organic waste, paper, packaging,
bulky waste, hazardous waste collection points — for a given address.

```
address ──▶ Nominatim ──▶ municipality + district ──▶ provider search (995)
                                                              │
                       collection dates ◀── portal ◀── resolve arguments
```

## Why this is not trivial

Waste management in Germany is organised municipally. There is **no nationwide
API** — roughly 400 public waste authorities each run their own portal, backed
by a handful of software platforms (Abfall.IO/AbfallPlus, AbfallNavi, Jumomind,
AWIDO, C-Trace, Müllmax, plus many plain ICS exports).

This server uses
[`mampfes/hacs_waste_collection_schedule`](https://github.com/mampfes/hacs_waste_collection_schedule)
(MIT) as its data source — an actively maintained project with over 950 source
modules. Its inner package is independent of Home Assistant and is wired in
here as a Git submodule.

The actual work of this project is turning an *address* into the responsible
waste authority **and its internal parameters**. In Home Assistant a human
clicks that together once; an MCP server has to do it on its own.

## Installation

The server runs **from a repository checkout**, not as an installed package: it
needs the data source under `vendor/` and the registry under `data/`, both
resolved relative to the project root. That is also why it is not on PyPI — a
wheel would install cleanly and still not work.

```bash
git clone --recurse-submodules https://github.com/AlpayC/mcp-abfall.git
cd mcp-abfall
uv sync
uv run pytest
```

`data/providers.json` is checked in, so the server starts right away. After a
submodule update, rebuild it:

```bash
uv run python scripts/build_registry.py
```

## Wiring it up

Locally over stdio — in `claude_desktop_config.json` or `.mcp.json`:

```json
{
  "mcpServers": {
    "abfall": {
      "command": "uv",
      "args": ["--directory", "/path/to/mcp-abfall", "run", "mcp-abfall"]
    }
  }
}
```

As an HTTP service:

```bash
uv run mcp-abfall --http --host 127.0.0.1 --port 8000
```

Keep in mind that every HTTP request puts load on the authorities' portals and
on Nominatim. For anything beyond personal use, put a cache in front and your
own Nominatim instance behind it (`MCP_ABFALL_NOMINATIM_URL`).

## Tools

Tool names and responses are German, because the domain and the users are.

| Tool | Purpose |
|---|---|
| `abfuhrtermine` | Address in, collection dates out. The usual entry point. |
| `finde_traeger` | Search authorities by place or company name, no geocoding. |
| `traeger_details` | Which arguments does an authority expect? |
| `abfuhrtermine_fuer_traeger` | Targeted query, e.g. to answer a follow-up question. |
| `abdeckung` | How many authorities and data sources are covered. |

Plus the resource `abfall://traeger` with the full list of authorities.

### Asking beats guessing

When a value cannot be determined unambiguously, the server returns
`status: "rueckfrage"` along with the concrete list of options instead of
guessing. That is deliberate: a wrongly guessed town cheerfully returns the
neighbouring municipality's calendar — a wrong answer that looks like a right
one.

## Coverage, measured

`scripts/build_registry.py` collects **995 waste authorities** from 150 source
modules.

`scripts/smoke.py` queries real addresses against the real portals. A run over
21 addresses across Germany (as of Aug 2026):

| Outcome | Share |
|---|---|
| Collection dates returned directly | 48 % |
| Follow-up question for a missing detail | 14 % |
| No authority returned dates | 38 % |

That is the measured number, not an estimate — and the reason to state it here:
"covers every German city" is true of the *authority list*, not of fully
automatic resolution from a bare address.

### Authorities with their own ID lookup

Some portals require internal identifiers that cannot be derived from an
address. For these, the portal's address dialog is reimplemented in
`lookup.py`:

| Authority | Identifier | Scope |
|---|---|---|
| Abfall.IO / AbfallPlus | `f_id_kommune`, `f_id_strasse`, … | 41 authorities |
| Stadtreinigung Hamburg | `hnId` | Hamburg |
| Berliner Stadtreinigungsbetriebe | `schedule_id` | Berlin |

The upstream wizard for Hamburg is stale by now — the portal moved its form to
a JavaScript component, whose address endpoint is read out of the page here.

### Where the remaining cases fail

* **Further ID arguments** with no lookup path: `standort` in Dresden,
  `idHouseNumber` in Leipzig, `streetnr` in Stuttgart. One more resolver each,
  following the same pattern as the three above.
* **Portals using different spellings** that ship no list of suggestions
  (Erfurt, Kiel).
* **Outages, rate limiting and malformed responses** on the authorities' side
  (Saarbrücken returns HTML instead of ICS).

## Layout

| File | Responsibility |
|---|---|
| `wcs.py` | Bridge to the vendored library; registers the package deliberately instead of putting it on `sys.path` (its parent directory holds a `calendar.py` that shadows the stdlib). |
| `registry.py` | Authority list and location search with German stemming. |
| `geo.py` | Nominatim, address variants, plausibility checks. |
| `resolve.py` | Address → authority → resolved arguments → collection dates. |
| `lookup.py` | Address dialogs for authorities with internal IDs (Abfall.IO, Hamburg, BSR). |
| `server.py` | MCP tools, stdio and HTTP. |

The registry is not built at runtime: `data/providers.json` is produced by a
script so that starting the server does not import 150 modules. Rebuild it
after a submodule update.

## Data sources and usage

Collection dates come from the portals of the respective waste authorities,
address resolution from [Nominatim](https://nominatim.openstreetmap.org/)
(OpenStreetMap). Nominatim has a usage policy — at most one request per second;
the server honours it and caches results in `~/.cache/mcp-abfall/`.

For dates something depends on (bulky waste, hazardous waste collection), it is
worth checking the portal address that every response carries.

## Contributing

The most useful contribution is a report that some authority does not work —
there is an [issue template](.github/ISSUE_TEMPLATE/provider.yml) with the
right questions. How to add an authority resolver is in
[CONTRIBUTING.md](CONTRIBUTING.md); security issues belong in a private report,
see [SECURITY.md](SECURITY.md). Changes are listed in the
[CHANGELOG](CHANGELOG.md). Agents working on this repository should read
[AGENTS.md](AGENTS.md).

One principle runs through the whole project and applies to contributions too:
**when in doubt, ask — do not guess.** A wrongly guessed town cheerfully
returns the neighbouring municipality's calendar — a wrong answer that looks
like a right one.

## License

MIT, see [LICENSE](LICENSE). The submodule
`vendor/hacs_waste_collection_schedule` is under its own MIT license,
Copyright (c) 2020 Steffen Zimmermann — this repository only references it, it
does not ship the code.
