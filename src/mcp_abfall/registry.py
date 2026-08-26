"""Registry aller deutschen Entsorgungstraeger.

Ein *Provider* ist genau ein Entsorgungstraeger (Landkreis, Stadt, AWB) mit
den Argumenten, die ihn im zugehoerigen WCS-Source-Modul identifizieren.
Ein Source-Modul faechert sich dabei oft in viele Provider auf: ``abfall_io``
allein bedient 41, ``app_abfallplus_de`` 145.

Die Registry wird per ``scripts/build_registry.py`` nach ``data/providers.json``
gebaut und zur Laufzeit nur noch gelesen, damit der Serverstart nicht 147
Module importieren muss.
"""

from __future__ import annotations

import functools
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "providers.json"


@dataclass
class ArgSpec:
    """Ein Konstruktor-Argument eines Source-Moduls."""

    name: str
    required: bool
    label: str | None = None  # deutschsprachiges Label laut PARAM_TRANSLATIONS
    default: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Provider:
    """Ein Entsorgungstraeger."""

    id: str
    source: str
    title: str
    country: str = "de"
    url: str | None = None
    default_args: dict = field(default_factory=dict)
    arg_specs: list[ArgSpec] = field(default_factory=list)
    #: Argumente, die der Nutzer/Resolver noch liefern muss.
    open_args: list[str] = field(default_factory=list)
    #: Vollstaendige, sofort abfragbare Beispielkonfigurationen (v.a. ICS).
    examples: list[dict] = field(default_factory=list)
    doc: str | None = None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["arg_specs"] = [a.as_dict() for a in self.arg_specs]
        return {k: v for k, v in d.items() if v not in (None, [], {})}

    @classmethod
    def from_dict(cls, d: dict) -> Provider:
        d = dict(d)
        d["arg_specs"] = [ArgSpec(**a) for a in d.get("arg_specs", [])]
        return cls(**d)

    def summary(self) -> dict:
        """Kompakte Darstellung fuer Tool-Antworten."""
        out = {"id": self.id, "traeger": self.title, "source": self.source}
        if self.url:
            out["web"] = self.url
        if self.open_args:
            out["benoetigt"] = self.open_args
        if self.examples:
            out["beispiel_orte"] = [e["name"] for e in self.examples[:8]]
        return out


# --------------------------------------------------------------------------
# Normalisierung & Suche
# --------------------------------------------------------------------------

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

#: Woerter, die in fast jedem Traegernamen vorkommen und daher nichts
#: unterscheiden - sie wuerden die Suche sonst voellig verrauschen.
STOPWORDS = frozenset(
    # Betriebsformen und Rechtsformen
    "abfall abfallwirtschaft abfallwirtschaftsbetrieb abfallentsorgung "
    "abfallbetrieb abfallzweckverband entsorgung entsorgungsbetrieb "
    "entsorgungsbetriebe wirtschaftsbetrieb wirtschaftsbetriebe "
    "umweltbetrieb umweltbetriebe eigenbetrieb zweckverband verband "
    "gmbh mbh kg ag ohg gbr co kgaa aoer ar "
    # Verwaltungsebenen
    "stadt stadtreinigung gemeinde markt kreis landkreis kreisstadt "
    "stadtverwaltung verbandsgemeinde samtgemeinde amt bezirk region "
    "staedteregion "
    # Fuellwoerter und Produktnamen
    "der die das und von im am an fuer "
    "app kalender abfallkalender muellkalender abfuhrkalender "
    # Strassenbestandteile - sie stehen in ICS-Beispielen und sagen
    # ueber den Ort nichts aus
    "strasse str strassen weg platz allee ring gasse damm ufer chaussee".split()
)


def normalize(text: str) -> str:
    """Kleinschreibung, Umlaute aufgeloest, nur Buchstaben/Ziffern/Leerzeichen."""
    text = text.lower().translate(_UMLAUTS)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def tokens(text: str) -> set[str]:
    """Bedeutungstragende Tokens eines Traeger- oder Ortsnamens."""
    return {t for t in normalize(text).split() if len(t) > 2 and t not in STOPWORDS}


def _tokens_with_stopwords(text: str) -> set[str]:
    return {t for t in normalize(text).split() if len(t) > 2}


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def _token_score(qt: str, candidates: set[str]) -> float:
    """Wie gut ein einzelnes Suchtoken auf eine Tokenmenge passt.

    Deutsche Traegernamen flektieren den Ortsnamen gern ("Bremen" ->
    "Bremer Stadtreinigung", "Nuernberg" -> "Nuernberger Land"), deshalb
    zaehlt neben dem exakten Treffer auch ein hinreichend langer
    gemeinsamer Wortstamm.
    """
    if qt in candidates:
        return 1.0
    best = 0.0
    for cand in candidates:
        shorter, longer = min(len(qt), len(cand)), max(len(qt), len(cand))
        if shorter < 4:
            continue
        # Das kuerzere Wort muss den Grossteil des laengeren ausmachen, sonst
        # matcht der Strassenname "Ludwig-Ruppel-Str." auf "Ludwigsburg" und
        # "Aach" auf "Aachen" - zwei verschiedene Orte.
        if shorter / longer < 0.7:
            continue
        if cand.startswith(qt) or qt.startswith(cand):
            best = max(best, 0.9)
            continue
        common = _common_prefix_len(qt, cand)
        if common >= 5 and common >= 0.7 * shorter:
            best = max(best, 0.75)
    return best


def _match(q: set[str], text: str) -> float:
    """Passung einer Suchtokenmenge auf einen Namen.

    Blend aus bestem Einzeltreffer und Mittelwert: Traegernamen lassen
    Zusaetze der Nutzereingabe regelmaessig weg ("Frankfurt am Main" ->
    "FES Frankfurter Entsorgungs- und Service GmbH"), ein reiner Mittelwert
    wuerde solche Treffer unter den Tisch fallen lassen. Der Mittelwert-
    Anteil haelt gleichzeitig mehrwortige Anfragen praezise.
    """
    cand = tokens(text) or _tokens_with_stopwords(text)
    if not cand:
        return 0.0
    per_token = [_token_score(qt, cand) for qt in q]
    return 0.7 * max(per_token) + 0.3 * (sum(per_token) / len(per_token))


#: Wie stark ein Beispieltreffer mindestens noch zaehlt, wenn die Anfrage nur
#: einen kleinen Teil des Namens abdeckt.
_COVERAGE_FLOOR = 0.35


def _coverage(q: set[str], text: str) -> float:
    """Wie viel des Beispielnamens die Anfrage ueberhaupt abdeckt.

    Ein Treffer auf einem Bruchteil eines langen Namens ist schwaechere
    Evidenz als einer auf dem ganzen Namen: "Bad Kreuznach OT Bad
    Muenster-Ebernburg" enthaelt "Muenster", und ohne Daempfung schlug der
    AWB Bad Kreuznach damit die Abfallwirtschaftsbetriebe Muenster.
    """
    cand = tokens(text) or _tokens_with_stopwords(text)
    if not cand:
        return 1.0
    matched = sum(1 for c in cand if _token_score(c, q) > 0)
    return _COVERAGE_FLOOR + (1 - _COVERAGE_FLOOR) * (matched / len(cand))


def _match_example(q: set[str], name: str) -> float:
    """Bewertet einen Beispielort.

    Beispiele nennen oft mehrere Verwaltungsebenen auf einmal ("Landkreis
    Prignitz, Gemeinde Karstaedt, Bluethen"). Jede Ebene wird einzeln
    bewertet, damit die Suche nach "Karstaedt" einen vollen Treffer bekommt
    statt nur ein Drittel - und ein Ortsname, der bloss als Wortbestandteil
    eines laengeren Namens vorkommt, trotzdem gedaempft bleibt.
    """
    best = 0.0
    for part in (p.strip() for p in name.split(",")):
        if part:
            best = max(best, _match(q, part) * _coverage(q, part))
    return best


def score(query: str, provider: Provider) -> float:
    """Wie gut passt ``query`` (Ortsname o.ae.) auf diesen Traeger?

    Bewertet wird gegen Titel und Beispielorte. Beispielorte wiegen leicht
    schwerer - dort stehen die tatsaechlich bedienten Gemeinden, waehrend der
    Titel oft nur den Landkreis oder den Betreibernamen nennt.
    """
    q = tokens(query) or _tokens_with_stopwords(query)
    if not q:
        return 0.0

    title_norm = normalize(provider.title)
    if normalize(query) == title_norm:
        return 1.0

    best = _match(q, provider.title) * 0.9
    for ex in provider.examples:
        best = max(best, _match_example(q, ex["name"]))
        if best >= 1.0:
            return 1.0

    # Teilstring-Treffer fangen Faelle wie "Koeln" in "Koeln-Muelheim" ab.
    if best < 0.55:
        nq = normalize(query)
        if len(nq) > 3 and nq in title_norm:
            best = 0.55
    return best


# --------------------------------------------------------------------------
# Laden
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def load(path: Path | None = None) -> list[Provider]:
    """Laedt die gebaute Registry."""
    p = path or DATA_FILE
    if not p.is_file():
        raise FileNotFoundError(
            f"Registry fehlt: {p}. Bitte 'uv run python scripts/build_registry.py' "
            "ausfuehren."
        )
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [Provider.from_dict(d) for d in raw["providers"]]


@functools.lru_cache(maxsize=1)
def by_id() -> dict[str, Provider]:
    return {p.id: p for p in load()}


def get(provider_id: str) -> Provider | None:
    return by_id().get(provider_id)


def search(query: str, limit: int = 10, min_score: float = 0.3) -> list[tuple[Provider, float]]:
    """Volltextsuche ueber Traegernamen und deren Beispielorte."""
    hits = []
    for p in load():
        s = score(query, p)
        if s >= min_score:
            hits.append((p, s))
    hits.sort(key=lambda t: (-t[1], t[0].title))
    return hits[:limit]


def save(providers: list[Provider], path: Path | None = None) -> Path:
    p = path or DATA_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "count": len(providers),
        "providers": [pr.as_dict() for pr in providers],
    }
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False),
        encoding="utf-8",
    )
    return p
