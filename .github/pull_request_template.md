## What this changes

<!-- Briefly: what changes and why. -->

## Checklist

- [ ] `uv run ruff check src scripts tests` passes
- [ ] `uv run pytest` passes
- [ ] If the submodule or the registry builder changed: `data/providers.json`
      rebuilt and committed alongside
- [ ] If this fixes a bug: a test case that pins it down

## For a new authority resolver

- [ ] The choice is made by `picker`, not by the resolver itself — so the same
      confidence threshold applies everywhere
- [ ] If nothing is unambiguous, the list goes back via `LookupNeedsChoice`
      instead of guessing
- [ ] Verified against a real address (please say which town in the PR — no
      full home address)
