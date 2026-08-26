"""Praxistest gegen die echten Portale.

Ruft `abfuhrtermine` fuer eine Reihe realer Adressen auf und zaehlt aus, was
dabei herauskommt. Das ist ausdruecklich kein Unit-Test: die Gegenstellen sind
fremde Server, einzelne Ausfaelle sind normal und sagen nichts ueber den Code.
Der Wert liegt darin, die Abdeckung nicht zu behaupten, sondern zu messen.

Bitte sparsam einsetzen - jeder Lauf belastet Nominatim und die Portale der
Traeger.

Aufruf:  uv run python scripts/smoke.py [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ADRESSEN = [
    "Kirchstraße 5, 48282 Emsdetten",
    "Marienplatz 1, 80331 München",
    "Rathausmarkt 1, 20095 Hamburg",
    "Domkloster 4, 50667 Köln",
    "Willy-Brandt-Straße 1, 10557 Berlin",
    "Marktplatz 1, 04109 Leipzig",
    "Königstraße 1, 70173 Stuttgart",
    "Am Markt 1, 28195 Bremen",
    "Wilhelmstraße 1, 47051 Duisburg",
    "Bahnhofstraße 1, 30159 Hannover",
    "Hauptstraße 1, 69117 Heidelberg",
    "Markt 1, 01067 Dresden",
    "Alter Markt 1, 24103 Kiel",
    "Marktplatz 1, 99084 Erfurt",
    "Rathausplatz 1, 66111 Saarbrücken",
    "Domplatz 1, 48143 Münster",
    "Marktplatz 1, 76133 Karlsruhe",
    "Bahnhofstraße 1, 90402 Nürnberg",
    "Zabelweg 1B, 22459 Hamburg",
    "Willy-Brandt-Straße 1, 10557 Berlin",
    "Marktstr. 1, 10317 Berlin",
]


async def _call(server, name: str, args: dict) -> dict:
    """Ruft ein Tool auf und packt die Antwort auf das reine dict aus."""
    result = await server.mcp.call_tool(name, args)

    payload = getattr(result, "structuredContent", None)
    if payload is None and isinstance(result, tuple):
        payload = result[1]
    if payload is None:
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = {"status": "unlesbar", "meldung": text[:200]}
                break
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    return payload if isinstance(payload, dict) else {"status": "unlesbar"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Praxistest gegen echte Portale.")
    parser.add_argument("--limit", type=int, default=len(ADRESSEN))
    parser.add_argument("--json", type=Path, help="Rohergebnisse hier ablegen.")
    args = parser.parse_args()

    logging.disable(logging.CRITICAL)
    from mcp_abfall import server

    zaehler: Counter[str] = Counter()
    protokoll = []

    for adresse in ADRESSEN[: args.limit]:
        try:
            antwort = asyncio.run(_call(server, "abfuhrtermine", {"adresse": adresse, "limit": 3}))
        except Exception as exc:
            antwort = {"status": "ausnahme", "meldung": f"{type(exc).__name__}: {exc}"}

        status = antwort.get("status", "?")
        zaehler[status] += 1
        protokoll.append({"adresse": adresse, "antwort": antwort})

        traeger = (antwort.get("traeger") or {}).get("traeger", "-")
        anzahl = antwort.get("anzahl_gesamt", "")
        detail = ""
        if status == "rueckfrage":
            detail = str(antwort.get("fehlende_angabe") or "Traegerauswahl")
        elif status != "ok":
            detail = str(antwort.get("meldung", ""))[:70]
        print(f"{status:14} {adresse[:38]:40} {str(traeger)[:28]:30} {anzahl} {detail}")

    print("\n--- Ergebnis ---")
    gesamt = sum(zaehler.values())
    for status, anzahl in zaehler.most_common():
        print(f"  {status:16} {anzahl:3}  ({anzahl / gesamt:.0%})")
    print(
        "\n'rueckfrage' ist kein Fehler: der Traeger braucht eine Angabe, die aus\n"
        "der Adresse allein nicht hervorgeht, und fragt danach statt zu raten."
    )

    if args.json:
        args.json.write_text(
            json.dumps(protokoll, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
        print(f"\nRohergebnisse: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
