# Security

## Supported versions

The most recent released version is maintained.

| Version | Supported |
|---|---|
| 0.1.x | yes |

## Reporting a vulnerability

Please do **not** open a public issue for it. Use GitHub's private reporting
instead:

> **Security** tab → **Report a vulnerability**

Helpful: what happens, how to reproduce it, and what impact you see. You will
get a reply as soon as I get to it — this is a spare-time project, not a
product with an on-call rotation.

## What this server does

Relevant context for assessing reports:

- The server **calls third-party portals** — those of the waste authorities —
  and [Nominatim](https://nominatim.openstreetmap.org/) for address
  resolution. Their responses are untrusted and get parsed.
- It **processes addresses**. Those are personal data. They go to Nominatim and
  to the respective portal, because there are no collection dates without them.
  Resolved addresses are cached under `~/.cache/mcp-abfall/`, or under the path
  set in `MCP_ABFALL_CACHE_DIR`.
- It **holds no credentials** and needs none.
- Executing source modules from the submodule is intentional: it is the data
  source. Anyone who does not trust the submodule should not run this project.

## HTTP mode

`--http` binds to `127.0.0.1` by default and has **no authentication**. Anyone
exposing the server beyond their own machine has to provide access control
themselves — and should keep in mind that every request puts load on the
authorities' portals and on Nominatim.
