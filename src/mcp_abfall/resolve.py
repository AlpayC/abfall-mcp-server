"""Von der Adresse zu abrufbaren Abfuhrterminen.

Zwei Schritte, die im Server auch einzeln nutzbar sind:

1. **Traeger finden** - Nominatim liefert Gemeinde, Landkreis und Bundesland,
   damit wird die Registry durchsucht. Der Umweg ueber den Landkreis ist
   noetig, weil ein Traeger fast nie nach jeder Gemeinde heisst, die er
   bedient: "Emsdetten" findet man nur ueber "Kreis Steinfurt".

2. **Argumente aufloesen** - jede Source will andere Parameter (``ort`` und
   ``strasse``, ``f_id_kommune``, ``city_id`` ...). Statt das fuer 150 Module
   einzeln zu pflegen, wird der generische Mechanismus des Upstreams genutzt:
   Sources werfen bei unbekannten Werten eine Exception, die die Liste der
   gueltigen Werte mitfuehrt. Wir raten aus der Adresse einen Startwert,
   fangen die Exception, waehlen den passenden Vorschlag und versuchen es
   erneut. Ist keine Wahl eindeutig, wird die Liste an den Aufrufer
   zurueckgegeben statt zu raten - ein falsch geratener Ort liefert sonst
   klaglos die Termine der Nachbargemeinde.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from dataclasses import dataclass, field

from . import geo, lookup, registry, wcs
from .registry import Provider, normalize

wcs.ensure_importable()

from waste_collection_schedule.exceptions import (
    SourceArgumentException,
    SourceArgumentSuggestionsExceptionBase,
)

#: Argumentnamen, unter denen die Sources dieselbe Sache fuehren.
ARG_ALIASES: dict[str, frozenset[str]] = {
    "city": frozenset(
        {
            "city", "ort", "gemeinde", "kommune", "place", "town", "city_name",
            "municipality", "stadt", "ortschaft", "location", "district_name",
        }
    ),
    "street": frozenset(
        {"street", "strasse", "street_name", "str", "streetname", "strassenname"}
    ),
    "house_number": frozenset(
        {
            "house_number", "hnr", "hausnummer", "housenumber", "number",
            "house_no", "nr", "hausnr", "house",
        }
    ),
    "district": frozenset({"district", "ortsteil", "bezirk", "suburb", "area", "stadtteil"}),
    "postcode": frozenset({"postcode", "zip", "plz", "zip_code", "postleitzahl"}),
}


class NeedsChoice(Exception):
    """Ein Argument ist offen und kann nicht zuverlaessig geraten werden."""

    def __init__(
        self,
        provider: Provider,
        argument: str,
        suggestions: list[str],
        args: dict,
        message: str,
    ) -> None:
        self.provider = provider
        self.argument = argument
        self.suggestions = suggestions
        self.args = args
        super().__init__(message)


class ResolutionFailed(Exception):
    """Die Source liess sich mit den vorhandenen Angaben nicht abfragen."""


@dataclass
class Candidate:
    """Ein moeglicher Traeger fuer eine Adresse."""

    provider: Provider
    score: float
    matched_on: str

    def as_dict(self) -> dict:
        d = self.provider.summary()
        d["treffer"] = round(self.score, 2)
        d["gefunden_ueber"] = self.matched_on
        return d


@dataclass
class Resolution:
    """Ergebnis der Traegersuche zu einer Adresse."""

    place: geo.Place
    candidates: list[Candidate] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "adresse": self.place.as_dict(),
            "traeger": [c.as_dict() for c in self.candidates],
        }


# --------------------------------------------------------------------------
# Schritt 1: Traeger finden
# --------------------------------------------------------------------------


def find_providers(place: geo.Place, limit: int = 6) -> list[Candidate]:
    """Sucht Traeger zu einer aufgeloesten Adresse.

    Jede Verwaltungsebene wird einzeln gesucht und mit ihrer Spezifitaet
    gewichtet; pro Traeger zaehlt der beste Treffer.
    """
    best: dict[str, Candidate] = {}
    for term, weight in place.search_terms():
        for provider, raw in registry.search(term, limit=limit * 3, min_score=0.5):
            value = raw * weight
            current = best.get(provider.id)
            if current is None or value > current.score:
                best[provider.id] = Candidate(provider, value, term)

    ranked = sorted(best.values(), key=lambda c: (-c.score, c.provider.title))
    return ranked[:limit]


def resolve_address(address: str, limit: int = 6) -> Resolution:
    """Adresse geocodieren und passende Traeger suchen."""
    place = geo.geocode(address)
    return Resolution(place=place, candidates=find_providers(place, limit=limit))


# --------------------------------------------------------------------------
# Schritt 2: Argumente aufloesen
# --------------------------------------------------------------------------


def _alias_group(arg_name: str) -> str | None:
    low = arg_name.casefold()
    for group, names in ARG_ALIASES.items():
        if low in names:
            return group
    # f_id_strasse, id_ort, ... - die Sources praefixen gern.
    for group, names in ARG_ALIASES.items():
        if any(low.endswith("_" + n) or low.startswith(n + "_") for n in names):
            return group
    return None


def _wanted_value(arg_name: str, place: geo.Place, user: dict) -> str | None:
    """Welchen Wert wir fuer dieses Argument aus der Adresse erwarten.

    Der Ortsteil steht bewusst nicht drin. Was OpenStreetMap als ``suburb``
    fuehrt, ist selten der Bezirk, den ein Entsorgungstraeger meint: fuer eine
    Emsdettener Adresse liefert OSM "Westum", der Traeger kennt den Namen
    nicht und lehnt die sonst gueltige Abfrage ab. Ein Ortsteil muss also
    ausdruecklich angegeben werden, statt geraten zu werden.
    """
    group = _alias_group(arg_name)
    if group is None:
        return None
    if user.get(group):
        return str(user[group])
    return {
        "city": place.city or place.municipality,
        "street": place.road,
        "house_number": place.house_number,
        "postcode": place.postcode,
    }.get(group)


def guess_args(provider: Provider, place: geo.Place, user: dict) -> dict:
    """Startbelegung der offenen Argumente aus Adresse und Nutzerangaben."""
    out: dict = {}
    for spec in provider.arg_specs:
        if spec.name in provider.default_args:
            continue
        value = _wanted_value(spec.name, place, user)
        if value:
            out[spec.name] = value
    return out


#: "Bahnhofstr" -> "Bahnhofstrasse". Innerhalb von "strasse" greift die
#: Wortgrenze nicht, dort bleibt alles unveraendert.
_STREET_ABBREV = re.compile(r"str\b")


def _canon(value: str) -> str:
    """Vergleichsform eines Strassen- oder Ortsnamens.

    Portale und Adressen kuerzen "Strasse" unterschiedlich ab. Ohne diese
    Vereinheitlichung fand der Server "Bahnhofstrasse" nicht in einer Liste,
    die den Eintrag als "Bahnhofstr." fuehrt - und fragte nach, obwohl die
    Angabe vorlag.
    """
    return _STREET_ABBREV.sub("strasse", normalize(value))


_HOUSE_NUMBER = re.compile(r"^\s*(\d{1,4})\s*([a-zA-Z]?)\s*$")
_HOUSE_RANGE = re.compile(r"^\s*(\d{1,4})\s*[a-zA-Z]?\s*-\s*(\d{1,4})\s*[a-zA-Z]?\s*$")


def _house_number_matches(wanted: str, value: str) -> bool:
    """Deckt ein Vorschlag wie "1-3" die gesuchte Hausnummer ab?

    Viele Portale fassen Hausnummern zu Bereichen zusammen. Ohne diese
    Pruefung fragt der Server nach, obwohl die Nummer laengst vorliegt.
    Deutsche Bereiche laufen ueblicherweise auf einer Strassenseite, also
    nur ueber gerade oder nur ueber ungerade Nummern - endet der Bereich auf
    derselben Paritaet, in der er beginnt, wird sie mitgeprueft.
    """
    number = _HOUSE_NUMBER.match(wanted)
    if not number:
        return False
    target = int(number.group(1))

    span = _HOUSE_RANGE.match(value)
    if not span:
        return False
    low, high = int(span.group(1)), int(span.group(2))
    if low > high:
        low, high = high, low
    if not low <= target <= high:
        return False
    if low % 2 == high % 2:
        return target % 2 == low % 2
    return True


def pick_suggestion(wanted: str | None, suggestions: list) -> tuple[str | None, float]:
    """Waehlt aus einer Vorschlagsliste den passenden Wert.

    Gibt zusaetzlich die Sicherheit zurueck; der Aufrufer entscheidet, ob sie
    reicht. Blind den ersten Vorschlag zu nehmen waere hier der teuerste
    Fehler, den der Server machen kann.
    """
    if not suggestions:
        return None, 0.0
    values = [s if isinstance(s, str) else str(s) for s in suggestions]
    # Eine einzige Moeglichkeit ist keine Wahl. Das ist der Normalfall bei
    # Traegern, die pro Strasse nur "Alle Hausnummern" anbieten.
    if len(values) == 1:
        return values[0], 0.95
    if not wanted:
        return None, 0.0

    target = _canon(wanted)
    canon = {v: _canon(v) for v in values}

    exact = [v for v in values if canon[v] == target]
    if len(exact) == 1:
        return exact[0], 1.0
    if exact:
        return exact[0], 0.8

    # In beide Richtungen: das Portal kuerzt mal ("Bahnhofstr. 1-5"), die
    # Adresse mal ("Bahnhofstrasse" fuer "Bahnhofstrasse Nord").
    im_bereich = [v for v in values if _house_number_matches(wanted, v)]
    if len(im_bereich) == 1:
        return im_bereich[0], 0.9

    prefixed = [
        v for v in values if canon[v].startswith(target) or target.startswith(canon[v])
    ]
    if len(prefixed) == 1:
        return prefixed[0], 0.9

    scored = sorted(
        ((difflib.SequenceMatcher(None, target, canon[v]).ratio(), v) for v in values),
        reverse=True,
    )
    top_score, top_value = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    # Nur wenn der beste Vorschlag sich klar vom zweitbesten abhebt.
    if top_score >= 0.85 and top_score - runner_up >= 0.05:
        return top_value, top_score
    return None, top_score


#: Ab hier gilt eine Zuordnung als sicher genug, um ungefragt zu greifen.
CONFIDENCE_THRESHOLD = 0.85

#: Mehr Runden braucht keine Source; schuetzt vor Endlosschleifen.
MAX_ROUNDS = 8


def _resolve_ids_if_needed(
    provider: Provider,
    args: dict,
    place: geo.Place | None,
    user_args: dict,
    pinned: dict,
) -> tuple[dict, list[dict]]:
    """Ersetzt geratene Klartextwerte in ID-Feldern durch echte IDs.

    ``abfall_io`` verlangt Zahlen-IDs und meldet Klartext nicht als Fehler,
    sondern liefert stillschweigend eine leere Terminliste - der teuerste
    Fehlerfall ueberhaupt, weil er wie ein Ergebnis aussieht. Deshalb wird
    hier vorab der Auswahldialog des Anbieters durchlaufen.
    """
    steps = [s for s in lookup.STEPS if s in {spec.name for spec in provider.arg_specs}]
    if not steps or not args.get("key"):
        return args, []
    if all(str(args.get(s, "")).isdigit() for s in steps if s in args) and all(
        s in args for s in steps if s in provider.open_args
    ):
        return args, []  # bereits IDs, nichts zu tun

    wanted = {
        step: (pinned.get(step) or _wanted_value(step, place, user_args) if place else pinned.get(step))
        for step in lookup.STEPS
    }

    try:
        ids = lookup.resolve_ids(
            str(args["key"]),
            wanted,
            pick_suggestion,
            min_confidence=CONFIDENCE_THRESHOLD,
        )
    except lookup.LookupNeedsChoice as exc:
        raise NeedsChoice(
            provider=provider,
            argument=exc.argument,
            suggestions=[name for name, _ in exc.choices],
            args=dict(args),
            message=(
                f"{provider.title}: {exc.argument!r} ist nicht eindeutig"
                + (f" (gesucht: {exc.wanted!r})" if exc.wanted else "")
                + f". {len(exc.choices)} Auswahlmoeglichkeiten."
            ),
        ) from exc
    except lookup.LookupError_ as exc:
        raise ResolutionFailed(f"{provider.title}: {exc}") from exc
    except Exception as exc:
        raise ResolutionFailed(
            f"{provider.title}: ID-Aufloesung fehlgeschlagen ({type(exc).__name__}: {exc})"
        ) from exc

    merged = dict(args)
    merged.update(ids)
    merged.update(pinned)  # ausdrueckliche Nutzerangaben bleiben unangetastet
    trace = [
        {"argument": name, "gewaehlt": value, "quelle": "Abfall.IO-Auswahldialog"}
        for name, value in ids.items()
    ]
    return merged, trace


@dataclass
class FetchResult:
    provider: Provider
    args: dict
    pickups: list[wcs.Pickup]
    #: Welche Argumente unterwegs automatisch gesetzt wurden.
    resolved: list[dict] = field(default_factory=list)


def fetch_for_provider(
    provider: Provider,
    place: geo.Place | None = None,
    user_args: dict | None = None,
    extra: dict | None = None,
) -> FetchResult:
    """Fragt einen Traeger ab und loest fehlende Argumente unterwegs auf.

    ``user_args`` sind semantische Angaben (``street``, ``house_number``, ...),
    ``extra`` sind rohe Source-Argumente, die unveraendert durchgereicht und
    nie ueberschrieben werden.
    """
    user_args = user_args or {}
    pinned = dict(extra or {})

    args: dict = dict(provider.default_args)
    if place is not None:
        args.update(guess_args(provider, place, user_args))
    args.update(pinned)

    resolved: list[dict] = []

    args, id_steps = _resolve_ids_if_needed(provider, args, place, user_args, pinned)
    resolved.extend(id_steps)

    # Pflichtargumente, die niemand befuellen konnte, wuerden beim Aufruf zu
    # einem nackten TypeError fuehren. Besser vorher benennen, was fehlt.
    fehlend = [
        spec.name
        for spec in provider.arg_specs
        if spec.required and spec.name not in args
    ]
    if fehlend:
        raise NeedsChoice(
            provider=provider,
            argument=fehlend[0],
            suggestions=[],
            args=dict(args),
            message=(
                f"{provider.title} verlangt "
                + ", ".join(repr(name) for name in fehlend)
                + ". Diese Angabe geht aus der Adresse nicht hervor - "
                "`traeger_details` zeigt, was der Traeger erwartet."
            ),
        )

    for _ in range(MAX_ROUNDS):
        try:
            return FetchResult(
                provider=provider,
                args=dict(args),
                pickups=wcs.fetch(provider.source, args),
                resolved=resolved,
            )
        except SourceArgumentSuggestionsExceptionBase as exc:
            argument = exc.argument
            if argument in pinned:
                raise ResolutionFailed(
                    f"{provider.title}: Wert {pinned[argument]!r} fuer {argument!r} "
                    f"wurde nicht akzeptiert. {exc.simple_message}"
                ) from exc

            suggestions = [
                s if isinstance(s, str) else str(s) for s in (exc.suggestions or [])
            ]
            wanted = _wanted_value(argument, place, user_args) if place else None
            if wanted is None:
                wanted = user_args.get(argument)

            choice, confidence = pick_suggestion(wanted, suggestions)
            if choice is None or confidence < CONFIDENCE_THRESHOLD:
                raise NeedsChoice(
                    provider=provider,
                    argument=argument,
                    suggestions=suggestions,
                    args=dict(args),
                    message=(
                        f"{provider.title}: Argument {argument!r} ist nicht eindeutig"
                        + (f" (gesucht: {wanted!r})" if wanted else "")
                        + f". {len(suggestions)} moegliche Werte."
                    ),
                ) from exc

            if args.get(argument) == choice:
                raise ResolutionFailed(
                    f"{provider.title}: {argument!r}={choice!r} wurde erneut "
                    f"abgelehnt. {exc.simple_message}"
                ) from exc

            args[argument] = choice
            resolved.append(
                {
                    "argument": argument,
                    "gewaehlt": choice,
                    "gesucht": wanted,
                    "sicherheit": round(confidence, 2),
                    "auswahl_aus": len(suggestions),
                }
            )
        except SourceArgumentException as exc:
            raise ResolutionFailed(f"{provider.title}: {exc}") from exc

    raise ResolutionFailed(
        f"{provider.title}: Argumente liessen sich in {MAX_ROUNDS} Schritten "
        "nicht aufloesen."
    )


def filter_pickups(
    pickups: list[wcs.Pickup],
    *,
    von: dt.date | None = None,
    bis: dt.date | None = None,
    arten: list[str] | None = None,
) -> list[wcs.Pickup]:
    """Termine nach Zeitraum und Abfallart filtern."""
    out = pickups
    if von is not None:
        out = [p for p in out if p.date >= von]
    if bis is not None:
        out = [p for p in out if p.date <= bis]
    if arten:
        wanted = [normalize(a) for a in arten if a.strip()]
        if wanted:
            out = [
                p
                for p in out
                if any(w in normalize(p.waste_type) for w in wanted)
            ]
    return out
