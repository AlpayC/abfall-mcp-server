---
description: Update the vendored data source and rebuild the provider registry
allowed-tools: Bash(git submodule:*), Bash(git diff:*), Bash(git status:*), Bash(git log:*), Bash(uv run:*), Bash(uv sync)
---

Bring the vendored `hacs_waste_collection_schedule` up to date and rebuild the
registry. Both must move together — `data/providers.json` is generated from the
submodule, and CI fails if they disagree.

1. Record the current provider count and submodule commit:

   ```bash
   git submodule status vendor/hacs_waste_collection_schedule
   uv run python -c "import json; print(json.load(open('data/providers.json', encoding='utf-8'))['count'])"
   ```

2. Update the submodule and rebuild:

   ```bash
   git submodule update --remote --depth 1 vendor/hacs_waste_collection_schedule
   uv run python scripts/build_registry.py
   ```

3. Run the suite. Upstream occasionally renames a source module or changes an
   argument signature, which surfaces here:

   ```bash
   uv run ruff check src scripts tests && uv run pytest
   ```

4. Report:
   - provider count before → after, and the new submodule commit
   - whether tests pass
   - **a drop in the provider count needs an explanation** before this is
     committed: either something was removed upstream, or the country
     assignment in `scripts/build_registry.py` stopped matching. Check the
     README section parsing (`readme_modules`) if the drop is large.

Stage `vendor/` and `data/providers.json` in the same commit. Do not commit
unless asked.
