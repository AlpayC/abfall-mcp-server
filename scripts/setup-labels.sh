#!/usr/bin/env bash
# Create the labels this repository actually uses.
#
# The issue templates, the Dependabot config and the data-source workflow all
# assign labels. GitHub does not create unknown labels on demand - it silently
# drops them - so they have to exist beforehand.
#
# Requires the GitHub CLI, authenticated:
#   winget install GitHub.cli   # Windows
#   brew install gh             # macOS
#   gh auth login
#
# Usage:
#   scripts/setup-labels.sh                    # current repository
#   scripts/setup-labels.sh OWNER/REPO         # a specific one

set -euo pipefail

repo="${1:-}"
target=()
[ -n "$repo" ] && target=(--repo "$repo")

if ! command -v gh >/dev/null 2>&1; then
    echo "GitHub CLI (gh) not found. See the header of this script." >&2
    exit 1
fi

# --force creates the label or updates an existing one, so this is safe to
# re-run - and it fixes up GitHub's stock "bug" label, which ships with a
# generic description.
create() {
    printf '  %-14s %s\n' "$1" "$3"
    gh label create "$1" --color "$2" --description "$3" --force "${target[@]}" >/dev/null
}

echo "Creating labels${repo:+ in $repo}:"

# Referenced by .github/ISSUE_TEMPLATE/bug.yml
create bug          d73a4a "Something in the server is broken"

# Referenced by .github/ISSUE_TEMPLATE/provider.yml
create authority    0e8a16 "A specific waste authority returns no or wrong dates"

# Referenced by .github/dependabot.yml
create dependencies 0366d6 "Dependency updates"
create ci           fbca04 "Workflows, build and tooling"

# Referenced by .github/workflows/update-registry.yml
create data-source  5319e7 "Vendored waste_collection_schedule and the generated registry"

echo "Done."
