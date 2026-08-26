"""Aufloesung interner Standort-IDs einzelner Traeger.

Die meisten Sources nehmen Klartext ("Emsdetten", "Hauptstrasse") entgegen und
melden ungueltige Werte mit einer Vorschlagsliste zurueck - das genuegt fuer
rund 320 Traeger. Einige verlangen dagegen interne Kennungen, die aus einer
Adresse nicht herzuleiten sind, und lehnen Klartext entweder ab oder - noch
unangenehmer - liefern kommentarlos eine leere Terminliste.

Fuer diese Traeger wird hier der Adressdialog des jeweiligen Portals
nachgebaut, den der Upstream sonst interaktiv per Wizard fahren laesst. Die
Auswahl faellt anhand der Adresse; wo sie nicht eindeutig ist, wandert die
Liste zurueck an den Aufrufer, statt geraten zu werden.

Abgedeckt sind:

* ``abfall_io``               41 Traeger, ``f_id_kommune`` & Co.
* ``stadtreinigung_hamburg``  ``hnId``
* ``bsr_de``                  Berlin, ``schedule_id``

Jeder Auflöser steht in ``RESOLVERS`` und bekommt dieselben Angaben:
die Vorbelegung des Traegers, die gesuchte Adresse in den Feldern ``city``,
``street`` und ``house_number``, sowie den Auswaehler aus ``resolve.py``.
"""

from __future__ import annotations

import functools
import html as html_mod
import importlib
import re
from collections.abc import Callable

import requests

from . import wcs

wcs.ensure_importable()

BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

#: Reihenfolge, in der Abfall.IO die Auswahlfelder ausliefert.
STEPS = ("f_id_kommune", "f_id_bezirk", "f_id_strasse", "f_id_strasse_hnr")

#: Welches Adressfeld welchen Abfall.IO-Schritt speist.
STEP_FIELDS = {
    "f_id_kommune": "city",
    "f_id_bezirk": "district",
    "f_id_strasse": "street",
    "f_id_strasse_hnr": "house_number",
}

API_URL = "https://api.abfall.io"

#: Platzhalter-Eintraege der Auswahllisten ("Bitte auswaehlen...").
_PLACEHOLDER_VALUES = frozenset({"0", "-1", ""})


class LookupError_(RuntimeError):
    """Die ID-Aufloesung ist fehlgeschlagen."""


class LookupNeedsChoice(Exception):
    """Ein Auswahlschritt ist nicht eindeutig."""

    def __init__(self, argument: str, choices: list[tuple[str, str]], wanted: str | None):
        self.argument = argument
        self.choices = choices
        self.wanted = wanted
        super().__init__(
            f"{argument!r} ist nicht eindeutig"
            + (f" (gesucht: {wanted!r})" if wanted else "")
            + f"; {len(choices)} Auswahlmoeglichkeiten."
        )


@functools.lru_cache(maxsize=1)
def _wizard():
    """Der Upstream-Wizard, wegen ``OptionParser`` und ``MODUS_KEY``."""
    return importlib.import_module("waste_collection_schedule.wizard.abfall_io")


def _choices(html: str, variable: str) -> list[tuple[str, str]]:
    """Auswahlmoeglichkeiten eines Feldes aus der HTML-Antwort."""
    parser = _wizard().OptionParser(variable)
    parser.feed(html)
    if not parser.is_selector:
        return []
    return [
        (str(name), str(value))
        for name, value in parser.choices
        if str(value) not in _PLACEHOLDER_VALUES
    ]


def _text_field(html: str) -> str | None:
    """Name eines freien Texteingabefeldes, falls die Seite eines zeigt."""
    parser = _wizard().OptionParser(_wizard().OptionParser.TEXTBOXES)
    parser.feed(html)
    return parser.text_name if parser.is_text_input else None


def _next_page(key: str, answers: dict, html: str, timeout: float) -> str:
    """Naechster Schritt des Auswahldialogs."""
    wizard = _wizard()
    actions = wizard.ACTION_EXTRACTOR_PATTERN.findall(html)
    if not actions:
        raise LookupError_(
            "Abfall.IO lieferte keinen naechsten Schritt. Dieser Traeger ist "
            "moeglicherweise auf die GraphQL-Schnittstelle umgestellt - dann "
            "greift die Source 'abfall_io_graphql'."
        )
    resp = requests.post(
        API_URL,
        params={"key": key, "modus": wizard.MODUS_KEY, "waction": actions[0]},
        data=answers,
        headers=wizard.HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def _choose(
    argument: str, options: list[tuple[str, str]], wanted: str | None, picker, min_confidence: float
) -> str:
    """Waehlt einen Eintrag oder gibt die Liste an den Aufrufer zurueck."""
    names = [name for name, _ in options]
    choice, confidence = picker(wanted, names)
    if choice is None or confidence < min_confidence:
        raise LookupNeedsChoice(argument, options, wanted)
    return next(value for name, value in options if name == choice)


def resolve_abfall_io(
    default_args: dict,
    address: dict[str, str | None],
    picker,
    *,
    min_confidence: float = 0.85,
    timeout: float = 30.0,
) -> dict[str, str]:
    """Laeuft den Abfall.IO-Auswahldialog durch und liefert die ID-Argumente.

    ``picker`` bekommt ``(gesucht, [namen])`` und gibt ``(name, sicherheit)``
    zurueck - so bleibt die Auswahllogik dieselbe wie fuer alle anderen
    Sources, und ``min_confidence`` sorgt dafuer, dass auch dieselbe Schwelle
    gilt: hier eine Gemeinde zu raten waere genauso falsch wie anderswo.
    """
    key = str(default_args.get("key") or "")
    if not key:
        raise LookupError_("Diesem Traeger fehlt der Abfall.IO-Schluessel.")
    wanted = {step: address.get(field) for step, field in STEP_FIELDS.items()}
    wizard = _wizard()
    resp = requests.get(
        API_URL,
        params={"key": key, "modus": wizard.MODUS_KEY, "waction": "init"},
        headers=wizard.HEADERS,
        timeout=timeout,
    )
    if resp.status_code == 401:
        raise LookupError_(
            f"Abfall.IO lehnt den Schluessel {key!r} ab (HTTP 401). Der Traeger "
            "ist vermutlich auf die GraphQL-Schnittstelle umgezogen."
        )
    resp.raise_for_status()
    html = resp.text

    answers: dict[str, str] = {"key": key}
    resolved: dict[str, str] = {}

    for step in STEPS:
        options = _choices(html, step)

        if not options:
            # Manche Traeger fragen die Hausnummer als freies Textfeld ab.
            field = _text_field(html)
            if field and field in wanted and wanted[field]:
                answers[field] = str(wanted[field])
                resolved[field] = str(wanted[field])
                html = _next_page(key, answers, html, timeout)
            continue

        value = _choose(step, options, wanted.get(step), picker, min_confidence)
        answers[step] = value
        resolved[step] = value

        html = _next_page(key, answers, html, timeout)

    if not resolved:
        raise LookupError_("Abfall.IO bot keine Auswahlfelder an.")
    return resolved


# --------------------------------------------------------------------------
# Stadtreinigung Hamburg
# --------------------------------------------------------------------------

HAMBURG_PAGE = "https://www.stadtreinigung.hamburg/abfuhrkalender/"

#: Die Seite reicht die Adresse-API als Alpine-Komponente durch. Der Upstream-
#: Wizard kennt noch das alte Formular mit ``asId``/``hnId`` im HTML; das gibt
#: es dort nicht mehr, deshalb wird die URL aus der Seite gelesen.
_HAMBURG_ACTION = re.compile(r'PickupAddressProvider\(\{(.*?)\}\)', re.DOTALL)


def _hamburg_endpoint(session: requests.Session, timeout: float) -> str:
    page = session.get(HAMBURG_PAGE, timeout=timeout)
    page.raise_for_status()
    found = _HAMBURG_ACTION.search(page.text)
    if not found:
        raise LookupError_(
            "Die Adress-Schnittstelle der Stadtreinigung Hamburg war auf der "
            "Seite nicht zu finden - das Portal wurde vermutlich umgebaut."
        )
    config = html_mod.unescape(found.group(1))
    action = config.split('"action":"', 1)[-1].strip('"').replace("\\/", "/")
    if not action.startswith("/"):
        raise LookupError_(f"Unerwartete Adress-URL bei Hamburg: {action[:80]!r}")
    # Die URL traegt einen TYPO3-cHash, der ueber die gesamte Query gebildet
    # wird. Zusaetzliche Query-Parameter machen sie ungueltig (HTTP 404), die
    # Suche gehoert deshalb in den POST-Body.
    return "https://www.stadtreinigung.hamburg" + action


def resolve_hamburg(
    default_args: dict,
    address: dict[str, str | None],
    picker,
    *,
    min_confidence: float = 0.85,
    timeout: float = 30.0,
) -> dict[str, str]:
    """Ermittelt ``asId`` und ``hnId`` der Stadtreinigung Hamburg."""
    street = (address.get("street") or "").strip()
    if not street:
        raise LookupNeedsChoice("street", [], None)

    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)
        endpoint = _hamburg_endpoint(session, timeout)

        streets: list = []
        for query in _street_queries(street):
            resp = session.post(
                endpoint, data={"tx_srh_pickups[street]": query}, timeout=timeout
            )
            resp.raise_for_status()
            streets = resp.json() or []
            if streets:
                break

    if not streets:
        raise LookupError_(f"Hamburg kennt keine Strasse {street!r}.")

    options = [(str(s.get("name")), s) for s in streets if s.get("name")]
    chosen_name = _choose("street", [(n, n) for n, _ in options], street, picker, min_confidence)
    chosen = next(s for n, s in options if n == chosen_name)

    numbers = chosen.get("hnIds") or []
    if not numbers:
        raise LookupError_(f"Hamburg fuehrt keine Hausnummern zu {chosen_name!r}.")

    number_options = [
        (str(n.get("name")), str(n.get("hnId"))) for n in numbers if n.get("hnId") is not None
    ]
    hn_id = _choose(
        "hnId", number_options, address.get("house_number"), picker, min_confidence
    )
    return {"asId": str(chosen.get("asId")), "hnId": hn_id}


# --------------------------------------------------------------------------
# Berliner Stadtreinigungsbetriebe
# --------------------------------------------------------------------------

BSR_STREETS = "https://umnewforms.bsr.de/p/de.bsr.adressen.app/streetNames"
BSR_ADDRESSES = "https://umnewforms.bsr.de/p/de.bsr.adressen.app/plzSet/plzSet"


def _street_queries(street: str) -> list[str]:
    """Schreibweisen, unter denen ein Portal die Strasse fuehren koennte.

    Die Portale suchen nach Praefix und legen sich dabei auf eine Schreibweise
    fest: die BSR fuehrt "Willy-Brandt-Str.", Hamburg schreibt aus. Eine
    Anfrage nach der jeweils anderen Form findet nichts.
    """
    street = street.strip()
    variants = [street]
    lowered = street.casefold()
    if lowered.endswith(("straße", "strasse")):
        variants.append(re.sub(r"stra(ß|ss)e$", "Str.", street, flags=re.IGNORECASE))
        variants.append(re.sub(r"stra(ß|ss)e$", "", street, flags=re.IGNORECASE).rstrip("- "))
    elif lowered.endswith(("str.", "str")):
        variants.append(re.sub(r"str\.?$", "straße", street, flags=re.IGNORECASE))
    return list(dict.fromkeys(v for v in variants if v))


def resolve_bsr(
    default_args: dict,
    address: dict[str, str | None],
    picker,
    *,
    min_confidence: float = 0.85,
    timeout: float = 30.0,
) -> dict[str, str]:
    """Ermittelt die ``schedule_id`` der Berliner Stadtreinigungsbetriebe."""
    street = (address.get("street") or "").strip()
    number = (address.get("house_number") or "").strip()
    if not street:
        raise LookupNeedsChoice("street", [], None)
    if not number:
        raise LookupNeedsChoice("house_number", [], None)

    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)

        streets: list = []
        for query in _street_queries(street):
            resp = session.get(BSR_STREETS, params={"searchQuery": query}, timeout=timeout)
            resp.raise_for_status()
            streets = resp.json() or []
            if streets:
                break

        if not streets:
            raise LookupError_(f"Die BSR kennt keine Strasse {street!r}.")

        names = [(str(s["value"]), str(s["value"])) for s in streets if s.get("value")]
        chosen = _choose("street", names, street, picker, min_confidence)

        resp = session.get(
            BSR_ADDRESSES, params={"searchQuery": f"{chosen}:::{number}"}, timeout=timeout
        )
        resp.raise_for_status()
        matches = resp.json() or []

    if not matches:
        raise LookupError_(f"Die BSR kennt keine Hausnummer {number!r} in {chosen!r}.")

    options = [
        (str(m.get("label") or m.get("value")), str(m["value"]))
        for m in matches
        if m.get("value")
    ]
    # Mehrere Treffer sind entweder gleichnamige Strassen in verschiedenen
    # Bezirken - die trennt die Postleitzahl, die in den Bezeichnungen steht
    # und die der Auswaehler kennt - oder Aufgaenge und Hinterhaeuser
    # derselben Adresse. Letztere unterscheidet nur, wer dort wohnt.
    return {
        "schedule_id": _choose(
            "schedule_id", options, f"{chosen} {number}", picker, min_confidence
        )
    }


#: Traeger, deren interne IDs eigens aufgeloest werden muessen.
RESOLVERS: dict[str, Callable[..., dict[str, str]]] = {
    "abfall_io": resolve_abfall_io,
    "stadtreinigung_hamburg": resolve_hamburg,
    "bsr_de": resolve_bsr,
}
