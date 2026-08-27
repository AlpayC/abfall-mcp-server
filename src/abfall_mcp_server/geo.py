"""Geocoding deutscher Adressen ueber Nominatim (OpenStreetMap).

Der Zweck ist nicht die Koordinate, sondern die *Verwaltungshierarchie*: Fuer
"Emsdetten, Hauptstrasse 5" liefert Nominatim den Kreis Steinfurt - und erst
darueber ist der zustaendige Entsorgungstraeger zu finden, denn kaum ein
Traeger heisst nach jeder Gemeinde, die er bedient.

Nominatim ist ein Gemeinschaftsdienst mit einer Nutzungsrichtlinie: maximal
eine Anfrage pro Sekunde, aussagekraeftiger User-Agent, Caching erwuenscht.
Beides ist hier umgesetzt. Ueber ``ABFALL_MCP_NOMINATIM_URL`` laesst sich eine
eigene Instanz einsetzen, dann greift die Drosselung nicht.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

from . import __version__

DEFAULT_ENDPOINT = "https://nominatim.openstreetmap.org/search"
USER_AGENT = f"abfall-mcp-server/{__version__} (+https://github.com/mampfes/hacs_waste_collection_schedule)"

#: Nominatims Nutzungsrichtlinie: hoechstens eine Anfrage pro Sekunde.
_PUBLIC_MIN_INTERVAL = 1.0

_lock = threading.Lock()
_last_request = 0.0


class GeocodingError(RuntimeError):
    """Adresse konnte nicht aufgeloest werden."""


#: Wortbestandteile, an denen ein Adresssegment als Strasse erkennbar ist.
_STREET_HINTS = (
    "str.",
    "strasse",
    "straße",
    "weg",
    "platz",
    "allee",
    "ring",
    "gasse",
    "damm",
    "ufer",
    "chaussee",
)

_HOUSE_NUMBER = re.compile(r"\s+\d{1,4}\s*[a-zA-Z]?\b(?!\s*\d)")
_POSTCODE = re.compile(r"\b\d{5}\b")


def _looks_like_street(segment: str) -> bool:
    low = segment.casefold()
    return any(h in low for h in _STREET_HINTS)


_STREET_WITH_NUMBER = re.compile(r"^(?P<street>.*?[^\s\d].*?)\s+(?P<number>\d{1,4}\s*[a-zA-Z]?)$")


def parse_street(address: str) -> tuple[str | None, str | None]:
    """Liest Strasse und Hausnummer direkt aus der Eingabe.

    Notwendig, weil Nominatim bei einer unbekannten Hausnummer auf die
    Ortsebene zurueckfaellt und dann weder ``road`` noch ``house_number``
    liefert - die Angaben stehen aber in der Eingabe. Ohne diesen Rueckgriff
    fragte der Server nach der Strasse, die der Nutzer gerade genannt hatte.
    """
    treffer: list[tuple[str, str, bool]] = []
    for segment in (s.strip() for s in re.split(r"[,\n]", address or "")):
        if not segment or _POSTCODE.search(segment):
            continue
        m = _STREET_WITH_NUMBER.match(segment)
        if not m:
            continue
        street = m.group("street").strip(" ,.-")
        if not street:
            continue
        treffer.append((street, m.group("number").replace(" ", ""), _looks_like_street(street)))

    if not treffer:
        return None, None
    # Ein Segment mit erkennbarem Strassenwort schlaegt eines ohne.
    treffer.sort(key=lambda t: not t[2])
    street, number, _ = treffer[0]
    return street, number


def _norm_tokens(text: str) -> set[str]:
    text = text.casefold().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return {t for t in re.split(r"[^a-z0-9]+", text) if len(t) > 2}


def _place_mentioned(addr: dict, address: str) -> bool:
    """Kommt der gefundene Ort in der urspruenglichen Eingabe vor?

    Nur eine Plausibilitaetspruefung fuer vergroeberte Suchvarianten. Nennt
    die Eingabe gar keinen erkennbaren Ort - etwa bei einer blossen
    Postleitzahl -, gibt es nichts abzugleichen und es wird nichts
    beanstandet. Zahlen bleiben dabei aussen vor: die PLZ wird ohnehin
    getrennt geprueft, und eine Hausnummer sagt ueber den Ort nichts.
    """
    typed = {t for t in _norm_tokens(address) if not t.isdigit()}
    if not typed:
        return True
    names = [
        addr.get(k)
        for k in ("city", "town", "village", "municipality", "county", "suburb", "state")
    ]
    candidates = {t for name in names if name for t in _norm_tokens(name)}
    if not candidates:
        return True
    return bool(candidates & typed)


def address_variants(address: str) -> list[str]:
    """Zunehmend groebere Schreibweisen einer Adresse.

    Nominatim liefert fuer eine Hausnummer, die es nicht kennt, schlicht gar
    nichts - "Emsdetten, Am Bahnhof 1" bleibt leer, "Emsdetten" trifft. Fuer
    unseren Zweck genuegt ohnehin die Gemeinde, also tasten wir uns von der
    genauen Adresse zur Ortsangabe zurueck.
    """
    address = address.strip()
    out = [address]

    without_number = _HOUSE_NUMBER.sub("", address).strip(" ,")
    if without_number and without_number != address:
        out.append(without_number)

    segments = [s.strip() for s in re.split(r"[,\n]", without_number or address) if s.strip()]
    if len(segments) > 1:
        kept = [s for s in segments if not _looks_like_street(s)]
        if kept and len(kept) != len(segments):
            out.append(", ".join(kept))

    # Nur noch PLZ + Ort bzw. der letzte, meist ortsbezogene Abschnitt.
    plz_segments = [s for s in segments if _POSTCODE.search(s)]
    if plz_segments:
        out.append(plz_segments[-1])
    elif segments:
        out.append(segments[-1])

    seen: set[str] = set()
    unique = []
    for candidate in out:
        key = candidate.casefold()
        if candidate and key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


@dataclass(frozen=True)
class Place:
    """Aufgeloeste Adresse, reduziert auf die Verwaltungsebenen."""

    query: str
    display_name: str
    #: Die Schreibweise, mit der Nominatim tatsaechlich getroffen hat.
    matched_query: str | None = None
    municipality: str | None = None  # Gemeinde/Stadt
    city: str | None = None  # Stadt/Ort
    district: str | None = None  # Stadtteil
    county: str | None = None  # Landkreis
    state: str | None = None  # Bundesland
    postcode: str | None = None
    road: str | None = None
    house_number: str | None = None
    lat: float | None = None
    lon: float | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def search_terms(self) -> list[tuple[str, float]]:
        """Suchbegriffe fuer die Traegersuche, mit Gewicht.

        Absteigend nach Spezifitaet: die Gemeinde trifft am ehesten einen
        Traegernamen, der Landkreis faengt die vielen Faelle ab, in denen der
        Traeger nach dem Kreis benannt ist.

        Weder Bundesland noch Stadtteil stehen in der Liste, und beide aus
        demselben Grund: sie grenzen nicht ein, taeuschen aber einen Treffer
        vor. Ueber "Nordrhein-Westfalen" lieferte eine Emsdettener Adresse
        einmal den Kalender von Meschede, ueber den Hamburger Stadtteil
        "Altstadt" schlug der Traeger der Koblenzer Altstadt durch. Entsorgung
        ist nach Gemeinde und Kreis organisiert - genau diese beiden Ebenen
        tragen die Information.
        """
        terms: list[tuple[str, float]] = []
        seen: set[str] = set()

        def add(value: str | None, weight: float) -> None:
            if not value:
                return
            key = value.casefold()
            if key in seen:
                return
            seen.add(key)
            terms.append((value, weight))

        add(self.city, 1.0)
        add(self.municipality, 1.0)
        add(self.county, 0.95)
        return terms


def _cache_path() -> Path:
    base = os.environ.get("ABFALL_MCP_CACHE_DIR")
    root = Path(base) if base else Path.home() / ".cache" / "abfall-mcp-server"
    root.mkdir(parents=True, exist_ok=True)
    return root / "geocode.json"


def _load_cache() -> dict:
    p = _cache_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _store_cache(cache: dict) -> None:
    try:
        _cache_path().write_text(
            json.dumps(cache, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass  # Cache ist Beiwerk, kein Grund die Anfrage scheitern zu lassen


def _throttle(endpoint: str) -> None:
    """Haelt das 1-Anfrage-pro-Sekunde-Limit der oeffentlichen Instanz ein."""
    if endpoint != DEFAULT_ENDPOINT:
        return
    global _last_request
    with _lock:
        wait = _PUBLIC_MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _query_nominatim(query: str, timeout: float) -> dict | None:
    endpoint = os.environ.get("ABFALL_MCP_NOMINATIM_URL", DEFAULT_ENDPOINT)
    _throttle(endpoint)
    try:
        resp = requests.get(
            endpoint,
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": "1",
                "countrycodes": "de",
                "limit": "1",
                "accept-language": "de",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as exc:
        raise GeocodingError(f"Geocoding fehlgeschlagen: {exc}") from exc
    except ValueError as exc:
        raise GeocodingError(f"Geocoding lieferte kein JSON: {exc}") from exc
    return results[0] if results else None


def geocode(address: str, *, timeout: float = 15.0) -> Place:
    """Loest eine deutsche Freitext-Adresse auf."""
    address = (address or "").strip()
    if not address:
        raise GeocodingError("leere Adresse")

    cache = _load_cache()
    key = address.casefold()
    if key in cache:
        return Place(**cache[key])

    variants = address_variants(address)
    # Stand in der Eingabe eine PLZ, muss das Ergebnis sie bestaetigen. Ohne
    # diese Pruefung liefert Nominatim fuer die vergroeberte Variante
    # "Hauptstrasse, 48282 Emsdetten" die naechstbeste gleichnamige Strasse -
    # gefunden wurde so Ochtrup statt Emsdetten, also ein anderer Traeger.
    plz = _POSTCODE.search(address)
    expected_plz = plz.group(0) if plz else None

    hit = None
    used = address
    fallback: tuple[dict, str] | None = None

    for index, variant in enumerate(variants):
        candidate = _query_nominatim(variant, timeout)
        if candidate is None:
            continue
        if fallback is None:
            fallback = (candidate, variant)

        addr = candidate.get("address") or {}
        found_plz = addr.get("postcode")
        if expected_plz and found_plz and found_plz != expected_plz:
            continue
        # Bei einer vergroeberten Variante muss der gefundene Ort auch in der
        # Eingabe vorkommen. Sonst liefert "Emsdetten, Hauptstrasse 5" die
        # gleichnamige Strasse in Ochtrup - selber Kreis, andere Gemeinde.
        if index > 0 and not _place_mentioned(addr, address):
            continue

        hit, used = candidate, variant
        break

    if hit is None and fallback is not None:
        # Keine Variante liess sich bestaetigen: lieber das beste Ergebnis mit
        # ehrlichem Vermerk als gar keins.
        hit, used = fallback
        used = f"{used} (ungeprueft)"

    if hit is None:
        raise GeocodingError(
            f"Keine Adresse in Deutschland gefunden fuer {address!r} "
            f"(auch nicht als {', '.join(repr(v) for v in variants[1:])})"
            if len(variants) > 1
            else f"Keine Adresse in Deutschland gefunden fuer {address!r}"
        )

    addr = hit.get("address") or {}
    place = Place(
        query=address,
        display_name=hit.get("display_name", address),
        matched_query=used if used != address else None,
        municipality=addr.get("municipality") or addr.get("town") or addr.get("village"),
        city=addr.get("city") or addr.get("town") or addr.get("village"),
        district=addr.get("suburb") or addr.get("city_district") or addr.get("borough"),
        county=addr.get("county"),
        state=addr.get("state"),
        postcode=addr.get("postcode"),
        road=addr.get("road"),
        house_number=addr.get("house_number"),
        lat=_as_float(hit.get("lat")),
        lon=_as_float(hit.get("lon")),
    )

    cache[key] = asdict(place)
    _store_cache(cache)
    return place


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
