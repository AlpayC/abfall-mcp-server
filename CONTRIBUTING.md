# Contributing

Thanks for your interest. The most common and most useful contribution is a
report that some waste authority does not work — more on that below.

Documentation is in English; the domain code is in German, because the domain
is (see *Style*). A German README is available at
[README.de.md](README.de.md).

## Setup

```bash
git clone --recurse-submodules https://github.com/AlpayC/mcp-abfall.git
cd mcp-abfall
uv sync
uv run python scripts/build_registry.py
uv run pytest
```

Without `--recurse-submodules` the data source under `vendor/` is missing;
`git submodule update --init --depth 1` fixes that.

## Before every pull request

```bash
uv run ruff check src scripts tests
uv run pytest
```

If you change the submodule or the registry builder, the rebuilt
`data/providers.json` belongs in the same commit. CI checks this: it rebuilds
the registry and fails if the result differs.

## The principle of this project

**When in doubt, ask — do not guess.**

A wrongly guessed town or street will cheerfully return the neighbouring
municipality's collection calendar. That is a wrong answer that looks like a
right one — the most expensive mistake this server can make, because nobody
notices it. Therefore:

- An assignment is only accepted unasked if it is confident enough
  (`resolve.CONFIDENCE_THRESHOLD`, `server.MIN_AUTO_FETCH`).
- If it is not, the list of options goes back to the caller
  (`status: "rueckfrage"`).
- An empty response from a portal is a suspicion, not a result.

If you want to lower these thresholds, please bring a test case showing that
nothing wrong slips through.

## Tests

The tests run without network access. Most of what is in `tests/` are
regressions: every case there is a bug that once did real damage — a search for
"Berlin" found Stadtreinigung Gießen, an address in Emsdetten returned
Meschede's calendar. When you fix a bug, the case belongs with it, plus one
sentence on what went wrong.

`scripts/smoke.py`, in contrast, talks to the real portals. That is not a test
but a measurement, and it does not belong in CI: other people's servers are not
a test subject, and every run puts load on them. Please use it sparingly.

## Adding or fixing an authority

The data comes from
[hacs_waste_collection_schedule](https://github.com/mampfes/hacs_waste_collection_schedule).
So the first question is where the contribution belongs:

- **The authority is missing entirely, or its portal changed** → that belongs
  upstream in that project. Everyone using it benefits, and we get it
  automatically with the next submodule update.
- **The authority exists but address resolution does not reach it** → that
  belongs here. Typically it requires an internal identifier (`standort`,
  `idHouseNumber`, `streetnr`) that cannot be derived from an address.

For the second case, the pattern lives in `src/mcp_abfall/lookup.py`: one
resolver per authority, reimplementing its address dialog. They all share the
same shape —

```python
def resolve_beispiel(default_args, address, picker, *, min_confidence, timeout):
    ...
    return {"interne_id": value}
```

`address` carries `city`, `district`, `street` and `house_number`. The choice
is not made by the resolver itself but by `picker` (which is
`resolve.pick_suggestion`) — that way the same threshold applies everywhere. If
nothing is unambiguous, `_choose` raises `LookupNeedsChoice` and the list goes
to the user. Register it in `RESOLVERS`, done.

The upstream wizards under
`vendor/hacs_waste_collection_schedule/custom_components/waste_collection_schedule/waste_collection_schedule/wizard/`
work as templates. They are meant to be interactive, but they show the path
through a portal. Do not rely on them blindly: the Hamburg wizard was already
stale when this was built, because the portal had moved on.

## Style

- **Domain code is written in German** — `Traeger`, `Abfuhrtermine`,
  `Rueckfrage` — because the domain is German and these terms have no clean
  English equivalents. Match the surrounding code instead of introducing
  English names. Umlauts are transliterated in code (`ae/oe/ue`) and spelled
  out in user-facing strings.
- Comments explain the *why*, especially for anything that looks like an odd
  special case. Most of those are scars.
- `ruff` decides the formalities.
