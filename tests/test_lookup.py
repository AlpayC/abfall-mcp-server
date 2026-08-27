"""Tests der traegerspezifischen ID-Aufloesung.

Die Netzwege selbst sind hier nicht geprueft - das taete nur so, als waere
ein fremdes Portal ein Testgegenstand. Geprueft wird, was der Server aus dem
entscheidet, was zurueckkommt.
"""

from __future__ import annotations

import pytest

from abfall_mcp_server import lookup


def test_traeger_mit_eigener_aufloesung():
    assert set(lookup.RESOLVERS) == {"abfall_io", "stadtreinigung_hamburg", "bsr_de"}


@pytest.mark.parametrize(
    "eingabe,erwartet",
    [
        ("Bahnhofstraße", ["Bahnhofstraße", "BahnhofStr.", "Bahnhof"]),
        ("Willy-Brandt-Str.", ["Willy-Brandt-Str.", "Willy-Brandt-straße"]),
        ("Am Markt", ["Am Markt"]),
    ],
)
def test_strassen_schreibweisen(eingabe, erwartet):
    """Die BSR fuehrt "Willy-Brandt-Str.", Hamburg schreibt aus - eine Anfrage
    in der jeweils anderen Form findet nichts."""
    assert lookup._street_queries(eingabe) == erwartet


def test_abfall_io_schritte_sind_adressfeldern_zugeordnet():
    assert lookup.STEP_FIELDS["f_id_kommune"] == "city"
    assert lookup.STEP_FIELDS["f_id_strasse"] == "street"
    assert lookup.STEP_FIELDS["f_id_strasse_hnr"] == "house_number"
    assert set(lookup.STEP_FIELDS) == set(lookup.STEPS)


def test_auswahl_bleibt_beim_aufrufer_wenn_unsicher():
    """Der Auswaehler entscheidet, nicht der Auflöser."""
    with pytest.raises(lookup.LookupNeedsChoice) as info:
        lookup._choose(
            "strasse",
            [("Hauptstr. Nord", "1"), ("Hauptstr. Sued", "2")],
            "Hauptstr.",
            lambda wanted, namen: (None, 0.4),
            0.85,
        )
    assert info.value.argument == "strasse"
    assert len(info.value.choices) == 2


def test_auswahl_liefert_den_internen_wert():
    """Gewaehlt wird ein Name, gebraucht wird die dahinterliegende ID."""
    wert = lookup._choose(
        "hnId",
        [("1A", "49698"), ("1B", "53814")],
        "1B",
        lambda wanted, namen: ("1B", 1.0),
        0.85,
    )
    assert wert == "53814"
