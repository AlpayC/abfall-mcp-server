"""Tests der Bruecke zur vendorierten waste_collection_schedule."""

from __future__ import annotations

import datetime as dt

from mcp_abfall import wcs


def test_stdlib_wird_nicht_ueberschattet():
    """Regression: das Elternverzeichnis der Bibliothek enthaelt den
    Home-Assistant-Glue mit einem eigenen ``calendar.py``. Lag es auf dem
    sys.path, importierte ``requests`` dieses statt der stdlib und brach ab.
    """
    import calendar

    wcs.ensure_importable()
    assert hasattr(calendar, "timegm") or hasattr(calendar, "monthrange")
    assert "waste_collection_schedule" in __import__("sys").modules


def test_sources_sind_auffindbar():
    namen = wcs.list_source_names()
    assert len(namen) > 900
    for erwartet in ("abfall_io", "jumomind_de", "abfallnavi_de", "ics"):
        assert erwartet in namen


def test_metadaten_werden_gelesen():
    meta = wcs.read_meta("abfall_io")
    assert meta.title == "Abfall.IO / AbfallPlus"
    assert meta.country == "de"
    assert len(meta.extra_info) > 30


def test_extra_info_als_funktion_wird_ausgewertet():
    """Manche Module liefern EXTRA_INFO als Liste, andere als Funktion."""
    meta = wcs.read_meta("jumomind_de")
    assert meta.extra_info and isinstance(meta.extra_info[0], dict)


def test_ungueltiger_modulname_wird_abgewiesen():
    import pytest

    for name in ("../etc/passwd", "os.path", "a\\b"):
        with pytest.raises(ValueError):
            wcs.import_source(name)


def test_termin_serialisiert_deutsch():
    p = wcs.Pickup(date=dt.date(2026, 9, 1), waste_type="Biomüll")
    d = p.as_dict()
    assert d["datum"] == "2026-09-01"
    assert d["wochentag"] == "Dienstag"
    assert d["abfallart"] == "Biomüll"
    assert "tage_bis" in d
