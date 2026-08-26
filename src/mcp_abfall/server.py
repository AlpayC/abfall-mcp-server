"""MCP-Server fuer Abfall-/Umweltkalender deutscher Staedte und Landkreise.

Start:
    mcp-abfall                 # stdio (Standard, fuer lokale MCP-Clients)
    mcp-abfall --http          # Streamable HTTP auf 127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from . import __version__, geo, registry, resolve, wcs

_LOG = logging.getLogger("mcp_abfall")

#: Ab diesem Trefferwert wird ein Traeger ungefragt abgefragt. Darunter ist die
#: Zuordnung Adresse -> Traeger nicht belastbar genug: ein Traeger, der nur
#: schwach passt, liefert klaglos den Kalender einer fremden Gemeinde - ein
#: falsches Ergebnis, das wie ein richtiges aussieht.
MIN_AUTO_FETCH = 0.6

INSTRUCTIONS = """\
Liefert Abfuhrtermine (Restmuell, Biotonne, Papier, Gelber Sack, Sperrmuell ...)
fuer Adressen in Deutschland aus den Kalendern der zustaendigen
Entsorgungstraeger.

Fuer die meisten Fragen genuegt `abfuhrtermine` mit der Adresse. Melden mehrere
Traeger Zustaendigkeit oder fehlt eine Angabe, kommt statt der Termine eine
Rueckfrage mit konkreten Auswahlmoeglichkeiten zurueck - diese dem Nutzer
vorlegen und den Aufruf mit der Auswahl wiederholen.

Wichtig: Die Daten stammen von den Portalen der Traeger und koennen sich
kurzfristig aendern. Bei Terminen, an denen etwas haengt (Sperrmuell,
Schadstoffmobil), lohnt der Blick auf die mitgelieferte Portal-Adresse.
"""

mcp = MCPServer(
    name="abfall-de",
    title="Abfallkalender Deutschland",
    version=__version__,
    instructions=INSTRUCTIONS,
)


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------


def _parse_date(value: str | None, label: str) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(
            f"{label} muss im Format JJJJ-MM-TT angegeben werden, war: {value!r}"
        ) from exc


def _shorten(values: list[str], limit: int = 60) -> dict:
    """Lange Auswahllisten fuer die Antwort kuerzen, aber ehrlich bleiben."""
    out: dict[str, Any] = {"anzahl": len(values)}
    if len(values) <= limit:
        out["auswahl"] = values
    else:
        out["auswahl"] = values[:limit]
        out["hinweis"] = (
            f"Nur die ersten {limit} von {len(values)} Werten. Bei Bedarf einen "
            "genaueren Suchbegriff angeben."
        )
    return out


def _needs_choice_response(exc: resolve.NeedsChoice) -> dict:
    return {
        "status": "rueckfrage",
        "traeger": exc.provider.summary(),
        "fehlende_angabe": exc.argument,
        "meldung": str(exc),
        **_shorten(exc.suggestions),
        "naechster_schritt": (
            "Den passenden Wert waehlen und `abfuhrtermine_fuer_traeger` mit "
            f"traeger_id={exc.provider.id!r} und "
            f"argumente={{{exc.argument!r}: <Wert>}} aufrufen."
        ),
    }


def _pickups_response(
    result: resolve.FetchResult,
    pickups: list[wcs.Pickup],
    place: geo.Place | None,
    limit: int,
) -> dict:
    out: dict[str, Any] = {
        "status": "ok",
        "traeger": result.provider.summary(),
        "termine": [p.as_dict() for p in pickups[:limit]],
        "anzahl_gesamt": len(pickups),
        "verwendete_argumente": result.args,
    }
    if place is not None:
        out["adresse"] = place.as_dict()
    if result.resolved:
        out["automatisch_ergaenzt"] = result.resolved
    if len(pickups) > limit:
        out["hinweis"] = f"{len(pickups)} Termine gefunden, {limit} angezeigt."
    return out


def _empty_result_note(result: resolve.FetchResult) -> dict:
    """Antwort fuer den Fall, dass ein Traeger gar keine Termine liefert.

    Das ist kein neutrales Ergebnis: mehrere Portale antworten auf falsche
    Argumente nicht mit einem Fehler, sondern mit einer leeren Liste. Diese
    Faelle muessen als solche kenntlich sein und nicht als "keine Abfuhr".
    """
    return {
        "status": "leer",
        "traeger": result.provider.summary(),
        "verwendete_argumente": result.args,
        "meldung": (
            "Der Traeger hat keine Termine zurueckgeliefert. Das bedeutet meist, "
            "dass eine Angabe (Ortsteil, Strasse, Hausnummer) nicht zur Adresse "
            "passt - mehrere Portale melden falsche Werte nicht als Fehler, "
            "sondern antworten leer."
        ),
        "naechster_schritt": (
            "Strasse und Hausnummer pruefen oder `traeger_details` aufrufen, um "
            "die erwarteten Argumente zu sehen."
        ),
    }


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------


@mcp.tool(
    title="Abfuhrtermine zu einer Adresse",
    description=(
        "Ermittelt den zustaendigen Entsorgungstraeger fuer eine deutsche "
        "Adresse und liefert dessen Abfuhrtermine. Erster Anlaufpunkt fuer "
        "Fragen wie 'Wann wird bei mir die Biotonne geleert?'."
    ),
)
def abfuhrtermine(
    adresse: Annotated[
        str,
        Field(description="Adresse oder Ort, z.B. 'Kirchstrasse 5, 48282 Emsdetten'."),
    ],
    strasse: Annotated[
        str | None,
        Field(description="Strasse, falls in der Adresse nicht enthalten."),
    ] = None,
    hausnummer: Annotated[str | None, Field(description="Hausnummer.")] = None,
    von: Annotated[
        str | None, Field(description="Fruehester Termin (JJJJ-MM-TT). Standard: heute.")
    ] = None,
    bis: Annotated[str | None, Field(description="Spaetester Termin (JJJJ-MM-TT).")] = None,
    abfallarten: Annotated[
        list[str] | None,
        Field(description="Nur diese Arten, z.B. ['Bio', 'Papier']. Teilwoerter genuegen."),
    ] = None,
    limit: Annotated[int, Field(description="Hoechstzahl der Termine.", ge=1, le=200)] = 25,
) -> dict:
    von_date = _parse_date(von, "von") or dt.date.today()
    bis_date = _parse_date(bis, "bis")

    try:
        resolution = resolve.resolve_address(adresse)
    except geo.GeocodingError as exc:
        return {
            "status": "fehler",
            "meldung": str(exc),
            "naechster_schritt": (
                "Adresse pruefen oder mit `finde_traeger` direkt nach dem "
                "Entsorgungstraeger suchen."
            ),
        }

    if not resolution.candidates:
        return {
            "status": "kein_traeger",
            "adresse": resolution.place.as_dict(),
            "meldung": (
                "Zu dieser Adresse wurde kein Entsorgungstraeger gefunden. "
                f"Erfasst sind {len(registry.load())} Traeger."
            ),
            "naechster_schritt": (
                "Mit `finde_traeger` nach dem Namen des oertlichen Betriebs "
                "suchen (z.B. 'AWB', 'Stadtreinigung' plus Ortsname)."
            ),
        }

    # Faellt Nominatim auf die Ortsebene zurueck, fehlen Strasse und
    # Hausnummer im Ergebnis, obwohl sie in der Eingabe stehen. Dann werden
    # sie aus dem Text gelesen, statt danach zu fragen.
    getippt_strasse, getippte_nummer = geo.parse_street(adresse)
    user_args = {
        "street": strasse or resolution.place.road or getippt_strasse,
        "house_number": hausnummer or resolution.place.house_number or getippte_nummer,
    }
    user_args = {k: v for k, v in user_args.items() if v}

    sicher = [c for c in resolution.candidates if c.score >= MIN_AUTO_FETCH]
    if not sicher:
        return {
            "status": "rueckfrage",
            "adresse": resolution.place.as_dict(),
            "meldung": (
                "Kein Traeger konnte dieser Adresse zweifelsfrei zugeordnet "
                "werden. Diese kommen in Frage:"
            ),
            "kandidaten": [c.as_dict() for c in resolution.candidates],
            "naechster_schritt": (
                "Den richtigen Traeger auswaehlen lassen und "
                "`abfuhrtermine_fuer_traeger` mit dessen ID aufrufen."
            ),
        }

    fehler: list[dict] = []
    rueckfrage: resolve.NeedsChoice | None = None

    for candidate in sicher:
        try:
            result = resolve.fetch_for_provider(
                candidate.provider, resolution.place, user_args
            )
        except resolve.NeedsChoice as exc:
            # Eine Rueckfrage ohne Auswahlmoeglichkeiten ist eine Sackgasse,
            # keine Frage - der naechste Traeger bekommt seine Chance. Und
            # selbst eine brauchbare Rueckfrage wird zurueckgestellt: liefert
            # ein weiterer Traeger einfach die Termine, ist das die bessere
            # Antwort. Genau daran scheiterte Berlin, wo ein Traeger mit
            # passendem Namen die BSR verdraengte.
            if exc.suggestions and rueckfrage is None:
                rueckfrage = exc
            elif not exc.suggestions:
                fehler.append({"traeger": exc.provider.title, "meldung": str(exc)})
            continue
        except resolve.ResolutionFailed as exc:
            fehler.append({"traeger": candidate.provider.title, "meldung": str(exc)})
            continue
        except Exception as exc:  # Portalausfall soll den naechsten Traeger nicht blockieren
            _LOG.warning("Abruf bei %s fehlgeschlagen", candidate.provider.title, exc_info=True)
            fehler.append(
                {
                    "traeger": candidate.provider.title,
                    "meldung": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        if not result.pickups:
            fehler.append(_empty_result_note(result))
            continue

        gefiltert = resolve.filter_pickups(
            result.pickups, von=von_date, bis=bis_date, arten=abfallarten
        )
        response = _pickups_response(result, gefiltert, resolution.place, limit)
        if not gefiltert:
            response["hinweis"] = (
                f"Der Traeger kennt {len(result.pickups)} Termine, aber keinen im "
                "gewaehlten Zeitraum bzw. fuer die gewaehlten Abfallarten."
            )
        if fehler:
            response["uebersprungen"] = fehler
        if len(sicher) > 1:
            response["weitere_traeger"] = [
                c.provider.summary()
                for c in sicher
                if c.provider.id != result.provider.id
            ][:3]
        return response

    if rueckfrage is not None:
        antwort = _needs_choice_response(rueckfrage)
        if fehler:
            antwort["uebersprungen"] = fehler
        return antwort

    return {
        "status": "fehlgeschlagen",
        "adresse": resolution.place.as_dict(),
        "meldung": "Kein zustaendiger Traeger lieferte Termine.",
        "versuche": fehler,
        "naechster_schritt": (
            "Strasse und Hausnummer angeben oder mit `finde_traeger` und "
            "`abfuhrtermine_fuer_traeger` gezielt abfragen."
        ),
    }


@mcp.tool(
    title="Entsorgungstraeger suchen",
    description=(
        "Sucht Entsorgungstraeger nach Orts- oder Betriebsnamen, ohne Geocoding. "
        "Nuetzlich, wenn die Adresssuche nichts findet oder der Betrieb bekannt ist."
    ),
)
def finde_traeger(
    suchbegriff: Annotated[
        str, Field(description="Ort, Landkreis oder Betriebsname, z.B. 'Kreis Steinfurt'.")
    ],
    limit: Annotated[int, Field(description="Hoechstzahl der Treffer.", ge=1, le=50)] = 10,
) -> dict:
    hits = registry.search(suchbegriff, limit=limit)
    return {
        "status": "ok" if hits else "leer",
        "suchbegriff": suchbegriff,
        "treffer": [
            {**provider.summary(), "treffer": round(score, 2)} for provider, score in hits
        ],
        "erfasste_traeger": len(registry.load()),
    }


@mcp.tool(
    title="Details zu einem Traeger",
    description=(
        "Zeigt, welche Argumente ein Traeger erwartet, welche Orte als Beispiel "
        "hinterlegt sind und wo sein Portal liegt."
    ),
)
def traeger_details(
    traeger_id: Annotated[str, Field(description="ID aus `finde_traeger`.")],
) -> dict:
    provider = registry.get(traeger_id)
    if provider is None:
        return {
            "status": "unbekannt",
            "meldung": f"Kein Traeger mit der ID {traeger_id!r}.",
            "naechster_schritt": "Mit `finde_traeger` die gueltige ID ermitteln.",
        }
    return {
        "status": "ok",
        "id": provider.id,
        "traeger": provider.title,
        "portal": provider.url,
        "datenquelle": provider.source,
        "beschreibung": provider.doc,
        "argumente": [spec.as_dict() for spec in provider.arg_specs],
        "pflichtargumente_offen": provider.open_args,
        "vorbelegt": provider.default_args,
        "beispiele": provider.examples[:10],
    }


@mcp.tool(
    title="Abfuhrtermine eines bestimmten Traegers",
    description=(
        "Fragt einen Traeger direkt ab - fuer Rueckfragen aus `abfuhrtermine` "
        "oder wenn der Traeger bereits feststeht."
    ),
)
def abfuhrtermine_fuer_traeger(
    traeger_id: Annotated[str, Field(description="ID aus `finde_traeger`.")],
    argumente: Annotated[
        dict[str, Any] | None,
        Field(description="Argumente der Datenquelle, z.B. {'ort': 'Ahlen', 'strasse': 'Bahnhofstr.'}."),
    ] = None,
    adresse: Annotated[
        str | None,
        Field(description="Optionale Adresse, um fehlende Argumente zu ergaenzen."),
    ] = None,
    von: Annotated[str | None, Field(description="Fruehester Termin (JJJJ-MM-TT).")] = None,
    bis: Annotated[str | None, Field(description="Spaetester Termin (JJJJ-MM-TT).")] = None,
    abfallarten: Annotated[list[str] | None, Field(description="Nur diese Arten.")] = None,
    limit: Annotated[int, Field(description="Hoechstzahl der Termine.", ge=1, le=200)] = 25,
) -> dict:
    provider = registry.get(traeger_id)
    if provider is None:
        return {
            "status": "unbekannt",
            "meldung": f"Kein Traeger mit der ID {traeger_id!r}.",
            "naechster_schritt": "Mit `finde_traeger` die gueltige ID ermitteln.",
        }

    von_date = _parse_date(von, "von") or dt.date.today()
    bis_date = _parse_date(bis, "bis")

    place = None
    if adresse:
        try:
            place = geo.geocode(adresse)
        except geo.GeocodingError as exc:
            _LOG.info("Geocoding fuer %r fehlgeschlagen: %s", adresse, exc)

    try:
        result = resolve.fetch_for_provider(provider, place, {}, extra=argumente or {})
    except resolve.NeedsChoice as exc:
        return _needs_choice_response(exc)
    except resolve.ResolutionFailed as exc:
        return {
            "status": "fehler",
            "traeger": provider.summary(),
            "meldung": str(exc),
            "naechster_schritt": "`traeger_details` zeigt die erwarteten Argumente.",
        }
    except Exception as exc:
        _LOG.warning("Abruf bei %s fehlgeschlagen", provider.title, exc_info=True)
        return {
            "status": "fehler",
            "traeger": provider.summary(),
            "meldung": f"{type(exc).__name__}: {exc}",
        }

    if not result.pickups:
        return _empty_result_note(result)

    gefiltert = resolve.filter_pickups(
        result.pickups, von=von_date, bis=bis_date, arten=abfallarten
    )
    response = _pickups_response(result, gefiltert, place, limit)
    if not gefiltert:
        response["hinweis"] = (
            f"Der Traeger kennt {len(result.pickups)} Termine, aber keinen im "
            "gewaehlten Zeitraum bzw. fuer die gewaehlten Abfallarten."
        )
    return response


@mcp.tool(
    title="Abdeckung",
    description="Zeigt, wie viele Entsorgungstraeger und Datenquellen erfasst sind.",
)
def abdeckung() -> dict:
    providers = registry.load()
    per_source: dict[str, int] = {}
    for provider in providers:
        per_source[provider.source] = per_source.get(provider.source, 0) + 1
    groesste = sorted(per_source.items(), key=lambda kv: -kv[1])[:10]
    return {
        "status": "ok",
        "traeger_gesamt": len(providers),
        "datenquellen": len(per_source),
        "groesste_datenquellen": [
            {"quelle": name, "traeger": anzahl} for name, anzahl in groesste
        ],
        "hinweis": (
            "Abfallwirtschaft ist in Deutschland kommunal organisiert; es gibt "
            "keine bundesweite Schnittstelle. Die Daten stammen aus den Portalen "
            "der einzelnen Traeger."
        ),
    }


@mcp.resource(
    "abfall://traeger",
    name="Entsorgungstraeger",
    description="Alle erfassten Entsorgungstraeger mit ID, Name und Portal.",
    mime_type="application/json",
)
def traeger_liste() -> list[dict]:
    return [provider.summary() for provider in registry.load()]


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mcp-abfall",
        description="MCP-Server fuer deutsche Abfall-/Umweltkalender.",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Streamable HTTP statt stdio.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Nur mit --http.")
    parser.add_argument("--port", type=int, default=8000, help="Nur mit --http.")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args(argv)

    # stdio ist der MCP-Kanal: Logs muessen auf stderr, sonst zerstoeren sie
    # den Protokollstrom.
    logging.basicConfig(level=args.log_level, stream=sys.stderr)

    try:
        registry.load()
    except FileNotFoundError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1

    if args.http:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
