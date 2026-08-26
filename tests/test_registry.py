"""Tests der Traegersuche.

Die Faelle hier sind keine erfundenen Beispiele: jeder einzelne ist ein Fehler,
der beim Bau aufgetreten ist. Die Ortssuche ist der Punkt, an dem dieser Server
still das Falsche tun kann - ein danebenliegender Treffer liefert klaglos den
Abfuhrkalender einer fremden Stadt.
"""

from __future__ import annotations

import pytest

from mcp_abfall import registry


@pytest.fixture(scope="module")
def providers():
    return registry.load()


def top_title(query: str) -> str | None:
    hits = registry.search(query, limit=1, min_score=0.5)
    return hits[0][0].title if hits else None


# --------------------------------------------------------------------------
# Datenbestand
# --------------------------------------------------------------------------


def test_registry_ist_gefuellt(providers):
    assert len(providers) > 900, "Die Registry sollte fast alle Traeger kennen."


def test_ids_sind_eindeutig(providers):
    ids = [p.id for p in providers]
    assert len(ids) == len(set(ids))


def test_alle_traeger_haben_quelle_und_titel(providers):
    for p in providers:
        assert p.source and p.title, f"unvollstaendiger Traeger: {p!r}"


# --------------------------------------------------------------------------
# Treffer, die kommen muessen
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "Köln", "München", "Hamburg", "Berlin", "Bremen", "Dresden", "Leipzig",
        "Stuttgart", "Hannover", "Nürnberg", "Kiel", "Mainz", "Erfurt",
        "Magdeburg", "Saarbrücken", "Potsdam", "Schwerin", "Wiesbaden",
        "Düsseldorf", "Kreis Steinfurt",
    ],
)
def test_grosse_staedte_werden_gefunden(query):
    assert top_title(query) is not None, f"kein Traeger fuer {query!r}"


def test_hamburg_trotz_fehlender_laenderangabe():
    """``stadtreinigung_hamburg`` setzt weder COUNTRY noch ein Laendersuffix.

    Ohne die Auswertung der README-Laendersektion fiel das Modul komplett aus
    der deutschen Registry heraus.
    """
    assert "Hamburg" in (top_title("Hamburg") or "")


def test_flektierte_ortsnamen():
    """"Bremen" heisst beim Traeger "Bremer", "Nuernberg" wird "Nuernberger"."""
    assert "Bremer" in (top_title("Bremen") or "")


# --------------------------------------------------------------------------
# Treffer, die ausbleiben muessen
# --------------------------------------------------------------------------


def test_kein_treffer_ueber_fremde_beispielorte():
    """Regression: TEST_CASES wurden an jeden Traeger ihres Moduls gehaengt.

    Dadurch fand die Suche nach "Offenbach" den "Abfallkalender Hattingen" -
    mit Bestwertung, weil der Testfall dort als Beispielort auftauchte.
    """
    assert "Hattingen" not in (top_title("Offenbach") or "")


def test_kein_treffer_ueber_geteilte_app_id():
    """Regression: ``app_abfallplus_de`` vergibt eine App-ID an viele Staedte.

    Der Testfall "Braunschweig" landete darueber unter dem Traeger "Berlin".
    """
    assert top_title("Braunschweig") != "Berlin"


def test_kein_treffer_ueber_strassennamen():
    """Regression: "Ludwig-Ruppel-Str." im ICS-Beispiel matchte "Ludwigsburg"."""
    title = top_title("Ludwigsburg") or ""
    assert "Frankfurt" not in title


def test_aehnliche_orte_bleiben_getrennt():
    """"Aach" und "Aachen" sind verschiedene Gemeinden."""
    assert top_title("Aachen") == "Stadt Aachen"


def test_unsinn_findet_nichts():
    assert registry.search("Kleinkleckersdorf am Nirgendwo", min_score=0.5) == []


# --------------------------------------------------------------------------
# Bausteine
# --------------------------------------------------------------------------


def test_normalize_loest_umlaute_auf():
    assert registry.normalize("Müllabfuhr Köln/Süd") == "muellabfuhr koeln sued"


def test_tokens_verwerfen_allerweltswoerter():
    assert registry.tokens("Abfallwirtschaftsbetrieb Landkreis Kassel") == {"kassel"}


def test_tokens_fallen_nicht_ins_leere():
    """Heisst ein Traeger nur aus Stoppwoertern, darf nicht nichts bleiben."""
    assert registry.tokens("Stadtreinigung") == set()
    assert registry._tokens_with_stopwords("Stadtreinigung") == {"stadtreinigung"}


def test_teiltreffer_in_langem_ortsnamen_wird_gedaempft():
    """Regression: der Beispielort "Bad Kreuznach OT Bad Muenster-Ebernburg"
    liess den AWB Bad Kreuznach bei der Suche nach "Muenster" gewinnen."""
    assert top_title("Münster") == "Abfallwirtschaftsbetriebe Münster"


def test_ortsebene_im_beispiel_zaehlt_voll():
    """Beispiele nennen mehrere Ebenen; jede fuer sich muss voll zaehlen."""
    q = registry.tokens("Erfurt")
    ganz = registry._match_example(q, "Adam-Ries-Straße 5, Erfurt")
    assert ganz == 1.0


def test_generischer_stadtteil_zieht_nicht_quer():
    """Regression: der Hamburger Stadtteil "Altstadt" traf den Traeger der
    Koblenzer Altstadt. Stadtteile sind daher keine Suchbegriffe mehr."""
    from mcp_abfall import geo

    place = geo.Place(query="x", display_name="x", city="Hamburg", district="Altstadt")
    assert [t for t, _ in place.search_terms()] == ["Hamburg"]


def test_adressartige_beispiele_zaehlen_nicht_als_ort():
    """Regression: der Beispielort "Berliner Platz 5" liess die Suche nach
    "Berlin" die Stadtreinigung Giessen finden."""
    assert registry._is_address("Berliner Platz 5")
    assert registry._is_address("Zabelweg 1B")
    assert not registry._is_address("Emsdetten")
    assert not registry._is_address("Kreis Steinfurt")
    assert top_title("Berlin") != "Stadtreinigung Gießen"
