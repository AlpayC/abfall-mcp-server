# Notes for coding agents

MCP server for German waste collection calendars. This is the operational
summary; [CONTRIBUTING.md](CONTRIBUTING.md) is written for humans and carries
more context. Documentation is English, the domain code is German — see
*Style* below.

## Setup

```bash
git submodule update --init --depth 1   # without this the data source is missing
uv sync
```

## Commands

```bash
uv run pytest                              # ~100 tests, run offline, under 1 s
uv run ruff check src scripts tests        # lint; --fix clears most of it
uv run python scripts/build_registry.py    # rebuild data/providers.json
uv run abfall-mcp-server                   # server, stdio
uv run abfall-mcp-server --http            # server, HTTP on 127.0.0.1:8000
```

`scripts/smoke.py` talks to the **real portals**. It is not a test but a
measurement, and every run puts load on someone else's servers. Use it
deliberately, never in a loop, never in CI.

## The one principle

**When in doubt, ask — do not guess.**

A wrongly guessed town or street will cheerfully return the neighbouring
municipality's collection calendar. That is a wrong answer that looks like a
right one — the most expensive failure here, because nobody notices it.
Concretely:

- Assignments are only accepted above a threshold:
  `resolve.CONFIDENCE_THRESHOLD` for argument values, `server.MIN_AUTO_FETCH`
  for picking a provider.
- Below that, the list of options goes back to the caller
  (`status: "rueckfrage"`).
- Do not lower these thresholds to make a test address work. If you do, a test
  must demonstrate that nothing wrong slips through.

## Traps

Every one of these has already bitten this project.

**1. Never put the submodule on `sys.path`.** Its parent directory contains
Home Assistant glue including its own `calendar.py`, which shadows the stdlib
module — `requests` falls apart on import. `wcs.ensure_importable()` registers
only the inner package in `sys.modules` on purpose. Do not "simplify" it.

**2. `data/providers.json` belongs to the submodule commit.** Change one,
rebuild the other and commit them together. CI recomputes this and fails
otherwise. The build is deterministic and needs no network.

**3. An empty response is not a result.** Several portals answer invalid
arguments not with an error but with an empty list of collections. This must
stay visible as `status: "leer"` and must never pass as "no collection".

**4. Federal state and city district are not search terms.** They narrow
nothing down but fake a match. Via "Nordrhein-Westfalen" an address in
Emsdetten once returned Meschede's calendar; via Hamburg's "Altstadt" district
the provider for Koblenz's Altstadt won. See `geo.Place.search_terms`.

**5. Some example locations are street addresses.** "Berliner Platz 5" made a
search for "Berlin" find Stadtreinigung Gießen. `registry._is_address` filters
these out.

**6. Do not trust the upstream wizards blindly.** The Hamburg one was already
stale when this was built — the portal had moved to a JavaScript component.
They show the path through a portal, not its current state. Always verify live.

## Layout

| File | Responsibility |
|---|---|
| `wcs.py` | bridge to the submodule: import, read metadata, `fetch` |
| `registry.py` | 995 providers, location search with German stemming |
| `geo.py` | Nominatim, address variants, postcode and place validation |
| `resolve.py` | address → provider → arguments → collection dates |
| `lookup.py` | address dialogs for providers with internal IDs |
| `server.py` | MCP tools, stdio and HTTP |
| `scripts/build_registry.py` | produces `data/providers.json` |

Flow: `server.abfuhrtermine` → `resolve.resolve_address` (geocoding + provider
search) → `resolve.fetch_for_provider` (ID lookup, then fetch with the
suggestion loop) → `wcs.fetch`.

## Adding a provider resolver

The most useful contribution. It concerns providers that require internal
identifiers (`standort` in Dresden, `idHouseNumber` in Leipzig, `streetnr` in
Stuttgart). Follow the pattern in `src/abfall_mcp_server/lookup.py`:

```python
def resolve_beispiel(default_args, address, picker, *, min_confidence, timeout):
    ...
    return {"interne_id": value}
```

- `address` carries `city`, `district`, `street`, `house_number`.
- The choice is made by **`picker`** (which is `resolve.pick_suggestion`), not
  by the resolver itself — that is the only way the same threshold applies
  everywhere. `_choose` wraps this and raises `LookupNeedsChoice` when nothing
  is unambiguous.
- Register it in `RESOLVERS`.
- Verify against a real address before reporting done.

If a provider is missing **entirely**, that belongs upstream in
[hacs_waste_collection_schedule](https://github.com/mampfes/hacs_waste_collection_schedule)
and will arrive here with the next submodule update.

## Style

- **Domain code is written in German**: identifiers and comments use `Traeger`,
  `Rueckfrage`, `Abfuhrtermine`. This is deliberate — the domain is German, and
  the terms have no clean English equivalents. Match the surrounding code
  rather than introducing English names. Umlauts are transliterated in code
  (`ae/oe/ue`) and spelled out in user-facing strings.
- Comments explain *why*. Anything that looks like an odd special case is
  usually a scar — read the comment before changing it.
- Tests are mostly regressions. When you fix a bug, add the case with one
  sentence on what went wrong.

## Before you finish

```bash
uv run ruff check src scripts tests && uv run pytest
```

If you touched the submodule or the registry builder, also run
`uv run python scripts/build_registry.py` and commit the result.
