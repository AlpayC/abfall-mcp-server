---
description: Add an ID resolver for a waste authority that needs internal identifiers
argument-hint: [authority or town, e.g. "Dresden" or "stadtreinigung_dresden_de"]
---

Add an ID resolver for: **$ARGUMENTS**

This applies to authorities that require internal identifiers which cannot be
derived from an address — `standort` in Dresden, `idHouseNumber` in Leipzig,
`streetnr` in Stuttgart. Work through it in this order:

1. **Confirm it is the right kind of problem.** Look up the authority and check
   what it actually demands:

   ```bash
   uv run python -c "from mcp_abfall import registry; [print(p.id, '|', p.title, '| open:', p.open_args) for p, _ in registry.search('$ARGUMENTS', limit=5)]"
   ```

   If it needs a plain-text street or town rather than an identifier, the
   generic suggestion loop in `resolve.py` already handles it — the bug is
   elsewhere, and a resolver is the wrong fix.

2. **Read the source module** under
   `vendor/hacs_waste_collection_schedule/custom_components/waste_collection_schedule/waste_collection_schedule/source/`
   to see which arguments `Source.__init__` takes and how they are used.

3. **Read the upstream wizard** for the same name under `.../wizard/`, if one
   exists. It shows the path through the portal. Treat it as a lead, not as
   truth — the Hamburg wizard was already stale, the portal had moved to a
   JavaScript component.

4. **Verify the portal live** before writing anything. Reproduce each step with
   `requests` and confirm the identifier you get matches the module's
   `TEST_CASES`. That check caught a wrong endpoint once already.

5. **Write the resolver** in `src/mcp_abfall/lookup.py`, following
   `resolve_hamburg` / `resolve_bsr`:

   - signature `(default_args, address, picker, *, min_confidence, timeout)`
   - `address` carries `city`, `district`, `street`, `house_number`
   - make every choice through `_choose(...)` so `picker` decides and the
     project-wide confidence threshold applies — never pick an option directly
   - register it in `RESOLVERS`

6. **Test it end to end** against a real address, through the MCP tool rather
   than the resolver alone.

7. **Add tests** in `tests/test_lookup.py` for the decision logic — no network.
   Then run:

   ```bash
   uv run ruff check src scripts tests && uv run pytest
   ```

8. Update the authority table in `README.md`, `README.de.md` and the
   `CHANGELOG.md` entry under *Unreleased*.

Do not commit unless asked.
