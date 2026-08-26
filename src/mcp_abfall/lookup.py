"""Aufloesung numerischer Standort-IDs fuer Abfall.IO / AbfallPlus.

Die meisten Sources nehmen Klartext ("Emsdetten", "Hauptstrasse") entgegen und
melden ungueltige Werte mit einer Vorschlagsliste zurueck - das genuegt fuer
rund 320 Traeger. ``abfall_io`` aber verlangt interne Zahlen-IDs
(``f_id_kommune=2592``) und kennt keinen Klartext. Betroffen sind 41 der 46
Traeger mit ID-Pflichtargumenten, also praktisch alle.

Der Upstream loest das mit einem interaktiven Wizard. Dessen HTML-Parser wird
hier weiterverwendet - nur eben ohne Rueckfrage an der Konsole: die Auswahl
faellt anhand der Adresse, und wo sie nicht eindeutig ist, wandert die Liste
zurueck an den Aufrufer.
"""

from __future__ import annotations

import functools
import importlib

import requests

from . import wcs

wcs.ensure_importable()

#: Reihenfolge, in der Abfall.IO die Auswahlfelder ausliefert.
STEPS = ("f_id_kommune", "f_id_bezirk", "f_id_strasse", "f_id_strasse_hnr")

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


def resolve_ids(
    key: str,
    wanted: dict[str, str | None],
    picker,
    *,
    min_confidence: float = 0.85,
    timeout: float = 30.0,
) -> dict[str, str]:
    """Laeuft den Auswahldialog durch und liefert die ID-Argumente.

    ``wanted`` ordnet jedem Schritt den gesuchten Klartext zu (Gemeinde,
    Strasse, Hausnummer). ``picker`` bekommt ``(gesucht, [namen])`` und gibt
    ``(name, sicherheit)`` zurueck - so bleibt die Auswahllogik dieselbe wie
    fuer alle anderen Sources, und ``min_confidence`` sorgt dafuer, dass auch
    dieselbe Schwelle gilt: hier eine Gemeinde zu raten waere genauso falsch
    wie anderswo.
    """
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

        target = wanted.get(step)
        names = [name for name, _ in options]
        choice, confidence = picker(target, names)
        if choice is None or confidence < min_confidence:
            raise LookupNeedsChoice(step, options, target)

        value = next(v for n, v in options if n == choice)
        answers[step] = value
        resolved[step] = value

        html = _next_page(key, answers, html, timeout)

    if not resolved:
        raise LookupError_("Abfall.IO bot keine Auswahlfelder an.")
    return resolved
