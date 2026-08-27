# Changelog

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed

- **Renamed** from `mcp-abfall` to `abfall-mcp-server` — repository, package,
  CLI command, Python module, Docker image and cache directory. The
  environment variables changed accordingly: `MCP_ABFALL_*` → `ABFALL_MCP_*`.
  GitHub redirects the old repository URL, but anyone with a local clone should
  update their remote, and existing configs that call `mcp-abfall` need the new
  command name. The registry entry in `server.json` moved to
  `io.github.AlpayC/abfall-mcp-server`, which has to match the repository for
  the registry's namespace check.

### Added

- Website: filterable tool cards with `invocation`, `schema` and a `view source`
  link into `server.py`, resources as their own section, and a searchable
  directory of all 995 authorities.
- Tools now declare MCP `ToolAnnotations`: `read_only_hint` on all of them, and
  `open_world_hint` where a municipal portal is contacted.

### Fixed

- The site rendered in the system font stack instead of Geist: the font
  variables sat on `<body>` while `--font-body` and `--font-code` were declared
  on `:root` and referenced them there.

## [0.1.0] – 2026-08-26

First release.

### Added

- MCP server with five tools: `abfuhrtermine` (address → collection dates),
  `finde_traeger`, `traeger_details`, `abfuhrtermine_fuer_traeger`,
  `abdeckung`; plus the resource `abfall://traeger`.
- stdio (default) and Streamable HTTP (`--http`) transports.
- Registry of **995 waste authorities** from 150 source modules, built from
  [hacs_waste_collection_schedule](https://github.com/mampfes/hacs_waste_collection_schedule).
- Location search with German stemming: "Bremen" finds "Bremer Stadtreinigung",
  "Nürnberg" finds "Nürnberger Land".
- Address resolution via Nominatim with a coarsening chain, postcode and place
  validation.
- Generic argument resolution through the suggestion lists that the source
  modules carry in their exceptions — covers around 320 authorities without
  any dedicated code.
- Dedicated address dialogs for authorities with internal identifiers:
  Abfall.IO (41 authorities), Stadtreinigung Hamburg (`hnId`), Berliner
  Stadtreinigungsbetriebe (`schedule_id`).
- Matching of abbreviated street names ("Bahnhofstr." ↔ "Bahnhofstraße") and
  house number ranges including street-side parity ("5" is in "1-9", not in
  "2-8").
- `scripts/smoke.py` measures coverage against the real portals instead of
  asserting it.

### Behaviour

- When a value cannot be determined unambiguously, the server returns
  `status: "rueckfrage"` with a concrete list of options instead of guessing. A
  wrongly guessed town cheerfully returns the neighbouring municipality's
  calendar — a wrong answer that looks like a right one.
- An empty list of collections is reported as `status: "leer"`, not as "no
  collection": several portals answer invalid arguments with an empty list
  rather than an error.
- An authority is only queried unasked when it matches the address confidently
  enough (`MIN_AUTO_FETCH`).

[Unreleased]: https://github.com/AlpayC/abfall-mcp-server/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AlpayC/abfall-mcp-server/releases/tag/v0.1.0
