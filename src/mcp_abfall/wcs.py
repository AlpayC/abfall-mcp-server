"""Bruecke zur vendorierten waste_collection_schedule-Bibliothek (MIT, mampfes).

Das innere Package ``waste_collection_schedule`` ist Home-Assistant-unabhaengig:
die Source-Module importieren nur ``requests`` & Co. plus ``Collection``. Wir
legen es auf den sys.path und sprechen die Source-Klassen direkt an, statt den
HA-geformten ``SourceShell`` zu benutzen.
"""

from __future__ import annotations

import datetime as dt
import functools
import importlib
import importlib.util
import pkgutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Das eigentliche Python-Package im Submodule.
WCS_PKG = (
    _REPO_ROOT
    / "vendor"
    / "hacs_waste_collection_schedule"
    / "custom_components"
    / "waste_collection_schedule"
    / "waste_collection_schedule"
)

_PKG_NAME = "waste_collection_schedule"


class VendorMissingError(RuntimeError):
    """Das Submodule wurde nicht ausgecheckt."""


def ensure_importable() -> None:
    """Registriert das vendorierte Package importierbar (idempotent).

    Bewusst *nicht* ueber ``sys.path``: das Elternverzeichnis enthaelt den
    Home-Assistant-Glue der Integration, darunter ein ``calendar.py``, das die
    stdlib ``calendar`` ueberschatten und dadurch u.a. ``requests`` zerlegen
    wuerde. Stattdessen haengen wir genau das innere Package per Spec in
    ``sys.modules`` ein; Submodul-Importe wie
    ``waste_collection_schedule.source.abfall_io`` laufen danach normal.
    """
    if _PKG_NAME in sys.modules:
        return
    init = WCS_PKG / "__init__.py"
    if not init.is_file():
        raise VendorMissingError(
            f"waste_collection_schedule nicht gefunden unter {WCS_PKG}. "
            "Bitte 'git submodule update --init --depth 1' ausfuehren."
        )
    spec = importlib.util.spec_from_file_location(
        _PKG_NAME, init, submodule_search_locations=[str(WCS_PKG)]
    )
    if spec is None or spec.loader is None:
        raise VendorMissingError(f"konnte {_PKG_NAME} nicht laden ({init})")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PKG_NAME] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[_PKG_NAME]
        raise


@functools.lru_cache(maxsize=1)
def source_package() -> ModuleType:
    ensure_importable()
    return importlib.import_module("waste_collection_schedule.source")


@functools.lru_cache(maxsize=1)
def list_source_names() -> tuple[str, ...]:
    """Alle verfuegbaren Source-Modulnamen (weltweit, alle Laender)."""
    pkg = source_package()
    return tuple(
        sorted(m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.ispkg)
    )


@functools.cache
def import_source(name: str) -> ModuleType:
    """Importiert ein Source-Modul, z.B. ``abfall_io``."""
    if "." in name or "/" in name or "\\" in name:
        raise ValueError(f"ungueltiger Source-Name: {name!r}")
    ensure_importable()
    return importlib.import_module(f"waste_collection_schedule.source.{name}")


@dataclass(frozen=True)
class Pickup:
    """Ein Abfuhrtermin, JSON-serialisierbar."""

    date: dt.date
    waste_type: str
    icon: str | None = None
    location: str | None = None
    description: str | None = None

    @property
    def days_until(self) -> int:
        return (self.date - dt.date.today()).days

    def as_dict(self) -> dict:
        d = {
            "datum": self.date.isoformat(),
            "wochentag": _WEEKDAYS[self.date.weekday()],
            "abfallart": self.waste_type,
            "tage_bis": self.days_until,
        }
        if self.location:
            d["ort"] = self.location
        if self.description:
            d["hinweis"] = self.description
        return d


_WEEKDAYS = (
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
)


@dataclass
class SourceMeta:
    """Statische Metadaten eines Source-Moduls."""

    name: str
    title: str
    description: str = ""
    url: str | None = None
    country: str | None = None
    extra_info: list[dict] = field(default_factory=list)
    param_translations: dict = field(default_factory=dict)
    test_cases: dict = field(default_factory=dict)


def read_meta(name: str) -> SourceMeta:
    """Liest TITLE/URL/COUNTRY/EXTRA_INFO eines Source-Moduls aus.

    ``EXTRA_INFO`` ist mal eine Liste, mal eine Funktion, die eine Liste
    zurueckgibt - beides kommt im Upstream vor.
    """
    mod = import_source(name)
    raw = getattr(mod, "EXTRA_INFO", [])
    if callable(raw):
        try:
            raw = raw()
        except Exception:
            raw = []
    extra = [e for e in (raw or []) if isinstance(e, dict)]
    return SourceMeta(
        name=name,
        title=str(getattr(mod, "TITLE", name)),
        description=str(getattr(mod, "DESCRIPTION", "") or ""),
        url=getattr(mod, "URL", None),
        country=getattr(mod, "COUNTRY", None),
        extra_info=extra,
        param_translations=getattr(mod, "PARAM_TRANSLATIONS", {}) or {},
        test_cases=getattr(mod, "TEST_CASES", {}) or {},
    )


def fetch(name: str, args: dict) -> list[Pickup]:
    """Instanziiert die Source und holt die Termine.

    Fehler werden bewusst nicht geschluckt - der Server uebersetzt sie in
    verstaendliche Meldungen inklusive der Argument-Vorschlaege, die manche
    Sources in ihren Exceptions mitliefern.
    """
    mod = import_source(name)
    source = mod.Source(**args)
    entries = source.fetch() or []
    out: list[Pickup] = []
    for e in entries:
        date = getattr(e, "date", None)
        if isinstance(date, dt.datetime):
            date = date.date()
        if not isinstance(date, dt.date):
            continue
        out.append(
            Pickup(
                date=date,
                waste_type=str(getattr(e, "type", "") or "").strip() or "Abfuhr",
                icon=e.get("icon") if hasattr(e, "get") else None,
                location=e.get("location") if hasattr(e, "get") else None,
                description=e.get("description") if hasattr(e, "get") else None,
            )
        )
    out.sort(key=lambda p: (p.date, p.waste_type))
    return out
