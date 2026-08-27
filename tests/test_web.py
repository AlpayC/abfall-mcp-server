"""Prueft, dass die Website nicht von der Serverwirklichkeit abweicht.

Die Landingpage fuehrt Tool-Namen und die Zeilennummern, auf die ihre
"Quelltext"-Links zeigen. Beides ist von Hand gepflegt und driftet lautlos,
sobald jemand server.py umstellt - beim Einfuegen der Tool-Annotationen sind
alle sechs Zeilennummern um bis zu 21 Zeilen verrutscht, ohne dass etwas
gemeckert haette.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "web" / "components" / "landing-page.tsx"
SERVER = ROOT / "src" / "abfall_mcp_server" / "server.py"

pytestmark = pytest.mark.skipif(
    not PAGE.is_file(), reason="Website nicht ausgecheckt"
)


def _page_entries() -> list[tuple[str, int]]:
    """Die Paare aus Name und hinterlegter Zeile, in der Reihenfolge der Datei."""
    text = PAGE.read_text(encoding="utf-8")
    names = re.findall(r'^\s+name: "([^"]+)",$', text, re.MULTILINE)
    lines = [int(x) for x in re.findall(r"^\s+line: (\d+),$", text, re.MULTILINE)]
    # Die Resource fuehrt statt "name" ein "uri" - sie haengt hinten an.
    uris = re.findall(r'^\s+uri: "([^"]+)",$', text, re.MULTILINE)
    return list(zip(names + uris, lines, strict=True))


def _server_definitions() -> dict[str, int]:
    """Funktionsname -> Zeilennummer der Definition in server.py."""
    out = {}
    for i, line in enumerate(SERVER.read_text(encoding="utf-8").splitlines(), start=1):
        m = re.match(r"^def ([a-z_]+)\(", line)
        if m:
            out[m.group(1)] = i
    return out


def test_zeilennummern_zeigen_auf_die_definitionen():
    """Jeder "Quelltext"-Link muss auf die Definition zeigen, die er meint."""
    defs = _server_definitions()
    # Die Resource heisst auf der Seite nach ihrer URI, im Server nach der Funktion.
    alias = {"abfall://traeger": "traeger_liste"}

    falsch = []
    for name, line in _page_entries():
        fn = alias.get(name, name)
        assert fn in defs, f"{fn!r} gibt es in server.py nicht (mehr)"
        if defs[fn] != line:
            falsch.append(f"{name}: Seite sagt {line}, server.py steht auf {defs[fn]}")
    assert not falsch, "Zeilennummern veraltet:\n  " + "\n  ".join(falsch)


def test_alle_tools_stehen_auf_der_seite():
    """Kommt ein Tool dazu, soll es nicht stillschweigend fehlen."""
    import asyncio

    from abfall_mcp_server import server

    vorhanden = {t.name for t in asyncio.run(server.mcp.list_tools())}
    genannt = {name for name, _ in _page_entries()}
    fehlt = vorhanden - genannt
    assert not fehlt, f"Auf der Seite fehlen: {sorted(fehlt)}"


def test_versionsnummer_ist_ueberall_dieselbe():
    """Die Version steht an drei Stellen und muss zusammenpassen.

    __init__.py ist die Quelle, an der sich der Release-Workflow orientiert;
    server.json meldet sie an die MCP-Registry, die Website zeigt sie an. Laufen
    sie auseinander, bricht das Release erst beim Tag-Abgleich ab - oder, noch
    unangenehmer, die Seite wirbt mit einer Version, die es nicht gibt.
    """
    import json

    from abfall_mcp_server import __version__

    server_json = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    seite = re.search(
        r'^const VERSION = "v([^"]+)";$', PAGE.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert seite, "Auf der Seite ist keine Version zu finden"

    assert server_json["version"] == __version__, (
        f"server.json: {server_json['version']}, __init__.py: {__version__}"
    )
    assert seite.group(1) == __version__, (
        f"Website: {seite.group(1)}, __init__.py: {__version__}"
    )
