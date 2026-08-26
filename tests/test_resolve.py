"""Tests der Adressverarbeitung und der Argumentauswahl.

Netzzugriff findet hier nicht statt - geprueft werden die Entscheidungen, die
der Server aus bereits vorliegenden Daten trifft. Gerade die Auswahllogik muss
im Zweifel lieber nachfragen als raten.
"""

from __future__ import annotations

import pytest

from mcp_abfall import geo, resolve
from mcp_abfall.registry import Provider

# --------------------------------------------------------------------------
# Adressvarianten
# --------------------------------------------------------------------------


def test_hausnummer_wird_abgetrennt():
    varianten = geo.address_variants("Kirchstraße 5, 48282 Emsdetten")
    assert varianten[0] == "Kirchstraße 5, 48282 Emsdetten"
    assert "Kirchstraße, 48282 Emsdetten" in varianten


def test_postleitzahl_bleibt_erhalten():
    """Die fuenfstellige PLZ darf nicht als Hausnummer verschwinden."""
    for variante in geo.address_variants("Hauptstraße 12a, 48282 Emsdetten"):
        assert "48282" in variante or "Hauptstraße" in variante
    assert "48282 Emsdetten" in geo.address_variants("Hauptstraße 12a, 48282 Emsdetten")


def test_ortsangabe_bleibt_als_letzte_variante():
    varianten = geo.address_variants("Emsdetten, Am Bahnhof 1")
    assert varianten[-1] in {"Emsdetten", "Am Bahnhof"}


def test_ortspruefung_erkennt_abweichung():
    """Regression: "Emsdetten, Hauptstrasse 5" traf die Hauptstrasse in Ochtrup."""
    assert not geo._place_mentioned({"city": "Ochtrup"}, "Emsdetten, Hauptstraße 5")
    assert geo._place_mentioned({"city": "Emsdetten"}, "Emsdetten, Hauptstraße 5")


def test_ortspruefung_ist_nachsichtig_ohne_ortsangabe():
    assert geo._place_mentioned({"city": "Ochtrup"}, "12345")


# --------------------------------------------------------------------------
# Suchbegriffe
# --------------------------------------------------------------------------


def test_bundesland_ist_kein_suchbegriff():
    """Regression: ueber "Nordrhein-Westfalen" lieferte eine Emsdettener
    Adresse den Abfuhrkalender von Meschede."""
    place = geo.Place(
        query="x",
        display_name="x",
        city="Emsdetten",
        county="Kreis Steinfurt",
        state="Nordrhein-Westfalen",
    )
    begriffe = [term for term, _ in place.search_terms()]
    assert "Nordrhein-Westfalen" not in begriffe
    assert begriffe == ["Emsdetten", "Kreis Steinfurt"]


def test_gemeinde_wiegt_schwerer_als_landkreis():
    place = geo.Place(query="x", display_name="x", city="Ahlen", county="Kreis Warendorf")
    gewichte = dict(place.search_terms())
    assert gewichte["Ahlen"] > gewichte["Kreis Warendorf"]


# --------------------------------------------------------------------------
# Argumentzuordnung
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argument,gruppe",
    [
        ("ort", "city"),
        ("city", "city"),
        ("f_id_kommune", "city"),
        ("strasse", "street"),
        ("street", "street"),
        ("f_id_strasse", "street"),
        ("hausnummer", "house_number"),
        ("f_id_strasse_hnr", "house_number"),
        ("unbekanntes_feld", None),
    ],
)
def test_argumentnamen_werden_zugeordnet(argument, gruppe):
    assert resolve._alias_group(argument) == gruppe


def test_ortsteil_wird_nicht_geraten():
    """Regression: der OSM-Ortsteil "Westum" wurde ins Feld ``bezirk`` geraten
    und liess eine sonst gueltige Abfrage scheitern."""
    place = geo.Place(query="x", display_name="x", city="Emsdetten", district="Westum")
    assert resolve._wanted_value("bezirk", place, {}) is None
    assert resolve._wanted_value("ortsteil", place, {}) is None


def test_ortsteil_wird_uebernommen_wenn_angegeben():
    place = geo.Place(query="x", display_name="x", city="Emsdetten", district="Westum")
    assert resolve._wanted_value("bezirk", place, {"district": "Sinningen"}) == "Sinningen"


def test_nutzerangabe_schlaegt_geocoding():
    place = geo.Place(query="x", display_name="x", city="Emsdetten", road="Kirchstraße")
    assert resolve._wanted_value("strasse", place, {"street": "Bahnhofstr."}) == "Bahnhofstr."


def test_guess_args_laesst_vorbelegtes_unberuehrt():
    provider = Provider(
        id="x", source="s", title="T",
        default_args={"city": "Meschede"},
        arg_specs=[],
    )
    place = geo.Place(query="x", display_name="x", city="Emsdetten")
    assert resolve.guess_args(provider, place, {}) == {}


# --------------------------------------------------------------------------
# Auswahl aus Vorschlagslisten
# --------------------------------------------------------------------------


def test_einzige_moeglichkeit_wird_genommen():
    """Traeger bieten pro Strasse oft nur "Alle Hausnummern" an."""
    wert, sicherheit = resolve.pick_suggestion("5", ["Alle Hausnummern"])
    assert wert == "Alle Hausnummern"
    assert sicherheit >= resolve.CONFIDENCE_THRESHOLD


def test_exakter_treffer_gewinnt():
    wert, sicherheit = resolve.pick_suggestion("Ahlen", ["Beckum", "Ahlen", "Beelen"])
    assert (wert, sicherheit) == ("Ahlen", 1.0)


def test_treffer_ignoriert_umlaute_und_schreibweise():
    wert, _ = resolve.pick_suggestion("muenster", ["Münster", "Ahlen"])
    assert wert == "Münster"


def test_mehrdeutiges_wird_nicht_geraten():
    """Bei aehnlich guten Kandidaten muss der Server nachfragen."""
    wert, sicherheit = resolve.pick_suggestion(
        "Hauptstraße", ["Hauptstraße Nord", "Hauptstraße Süd"]
    )
    assert wert is None or sicherheit < resolve.CONFIDENCE_THRESHOLD


def test_ohne_anhaltspunkt_wird_nicht_geraten():
    wert, _ = resolve.pick_suggestion(None, ["Ahlen", "Beckum", "Beelen"])
    assert wert is None


def test_leere_liste_liefert_nichts():
    assert resolve.pick_suggestion("Ahlen", []) == (None, 0.0)


# --------------------------------------------------------------------------
# Terminfilter
# --------------------------------------------------------------------------


def _termine():
    import datetime as dt

    from mcp_abfall.wcs import Pickup

    return [
        Pickup(dt.date(2026, 9, 1), "Biomüll"),
        Pickup(dt.date(2026, 9, 8), "Restmüll 2-Wo"),
        Pickup(dt.date(2026, 9, 15), "Papier"),
    ]


def test_filter_nach_zeitraum():
    import datetime as dt

    gefiltert = resolve.filter_pickups(_termine(), von=dt.date(2026, 9, 5), bis=dt.date(2026, 9, 10))
    assert [p.waste_type for p in gefiltert] == ["Restmüll 2-Wo"]


def test_filter_nach_abfallart_als_teilwort():
    gefiltert = resolve.filter_pickups(_termine(), arten=["rest"])
    assert [p.waste_type for p in gefiltert] == ["Restmüll 2-Wo"]


def test_filter_nach_abfallart_ignoriert_umlaute():
    gefiltert = resolve.filter_pickups(_termine(), arten=["Biomuell"])
    assert [p.waste_type for p in gefiltert] == ["Biomüll"]


def test_filter_ohne_angaben_aendert_nichts():
    assert len(resolve.filter_pickups(_termine())) == 3


# --------------------------------------------------------------------------
# Strassen- und Hausnummernabgleich
# --------------------------------------------------------------------------


def test_abgekuerzte_strasse_wird_erkannt():
    """Regression: "Bahnhofstrasse" fand den Listeneintrag "Bahnhofstr." nicht
    und loeste eine unnoetige Rueckfrage aus."""
    wert, sicherheit = resolve.pick_suggestion("Bahnhofstraße", ["Bahnhofstr.", "Marktplatz"])
    assert wert == "Bahnhofstr."
    assert sicherheit >= resolve.CONFIDENCE_THRESHOLD


def test_ausgeschriebene_strasse_wird_erkannt():
    wert, _ = resolve.pick_suggestion("Willy-Brandt-Str.", ["Willy-Brandt-Straße", "Markt"])
    assert wert == "Willy-Brandt-Straße"


@pytest.mark.parametrize(
    "hausnummer,vorschlaege,erwartet",
    [
        ("1", ["1-3", "11a", "12"], "1-3"),
        ("2", ["1-3", "2-8", "9-11"], "2-8"),
        ("5", ["1-9", "2-8"], "1-9"),
        ("7", ["1-5", "9-13"], None),
    ],
)
def test_hausnummernbereiche(hausnummer, vorschlaege, erwartet):
    wert, _ = resolve.pick_suggestion(hausnummer, vorschlaege)
    assert wert == erwartet


def test_hausnummer_haelt_strassenseite_ein():
    """Ein Bereich "2-8" laeuft ueber die geraden Nummern einer Seite."""
    assert resolve._house_number_matches("4", "2-8")
    assert not resolve._house_number_matches("5", "2-8")
    assert resolve._house_number_matches("5", "1-9")


def test_hausnummer_ausserhalb_des_bereichs():
    assert not resolve._house_number_matches("20", "2-8")


def test_fehlendes_pflichtargument_wird_benannt():
    """Statt eines nackten TypeError soll klar werden, was fehlt."""
    from mcp_abfall.registry import ArgSpec, Provider

    provider = Provider(
        id="x", source="ics", title="T",
        arg_specs=[ArgSpec(name="hnId", required=True)],
    )
    with pytest.raises(resolve.NeedsChoice) as info:
        resolve.fetch_for_provider(provider)
    assert info.value.argument == "hnId"
    assert "hnId" in str(info.value)


def test_strasse_wird_aus_der_eingabe_gelesen():
    """Regression: faellt Nominatim auf die Ortsebene zurueck, fehlt ``road``.

    Der Server fragte dann nach der Strasse, die der Nutzer gerade genannt
    hatte - "Marktplatz 1, 76133 Karlsruhe" endete in einer Rueckfrage mit
    1876 Auswahlmoeglichkeiten.
    """
    assert geo.parse_street("Marktplatz 1, 76133 Karlsruhe") == ("Marktplatz", "1")
    assert geo.parse_street("Willy-Brandt-Straße 1, 10557 Berlin") == (
        "Willy-Brandt-Straße",
        "1",
    )


def test_strasse_ohne_strassenwort():
    assert geo.parse_street("Am Markt 1, 28195 Bremen") == ("Am Markt", "1")


def test_reine_ortsangabe_liefert_keine_strasse():
    assert geo.parse_street("48282 Emsdetten") == (None, None)
    assert geo.parse_street("Köln") == (None, None)


def test_postleitzahl_wird_nicht_als_hausnummer_gelesen():
    strasse, nummer = geo.parse_street("10557 Berlin")
    assert (strasse, nummer) == (None, None)


def test_strassenwort_gewinnt_bei_mehreren_kandidaten():
    strasse, _ = geo.parse_street("Haus 7, Bahnhofstraße 12, 12345 Musterstadt")
    assert strasse == "Bahnhofstraße"


# --------------------------------------------------------------------------
# Postleitzahl als Entscheidungshilfe
# --------------------------------------------------------------------------


def test_postleitzahl_entscheidet_bei_gleichnamigen_strassen():
    """Regression: Berlin hat zwei Marktstrassen. Die Portale haengen die PLZ
    genau deshalb an - ohne sie auszuwerten kam eine Rueckfrage, obwohl die
    Adresse die PLZ mitbrachte."""
    wert, sicherheit = resolve.pick_suggestion(
        "Marktstr.",
        ["Marktstr. 1, 13597 Berlin (Spandau)", "Marktstr. 1, 10317 Berlin (Lichtenberg)"],
        postcode="10317",
    )
    assert wert == "Marktstr. 1, 10317 Berlin (Lichtenberg)"
    assert sicherheit >= resolve.CONFIDENCE_THRESHOLD


def test_postleitzahl_ohne_treffer_aendert_nichts():
    """Passt die PLZ auf keinen Vorschlag, darf sie nicht alles wegfiltern."""
    wert, _ = resolve.pick_suggestion(
        "Ahlen", ["Ahlen", "Beckum"], postcode="99999"
    )
    assert wert == "Ahlen"


def test_ohne_postleitzahl_wird_weiter_nachgefragt():
    wert, sicherheit = resolve.pick_suggestion(
        "Marktstr.", ["Marktstr. (13597)", "Marktstr. (10317)"]
    )
    assert wert is None or sicherheit < resolve.CONFIDENCE_THRESHOLD
