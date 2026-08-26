"""Baut data/providers.json aus der vendorierten waste_collection_schedule.

Quellen, die zusammengefuehrt werden:

1. ``EXTRA_INFO`` je Source-Modul - die Liste der Entsorgungstraeger, die ein
   Modul bedient (``abfall_io`` -> 41 Traeger, ``app_abfallplus_de`` -> 145).
2. ``TEST_CASES`` je Modul - deren Schluessel sind reale Orts-/Traegernamen
   und deren Werte vollstaendige, funktionierende Argumentsaetze. Damit wird
   die Ortssuche ueberhaupt erst brauchbar.
3. ``doc/ics/*.md`` - Gemeinden, die ueber die generische ICS-Source laufen;
   die YAML-Beispiele dort sind sofort abfragbare Konfigurationen.

Aufruf:  uv run python scripts/build_registry.py [--country de]
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import yaml

from mcp_abfall import wcs
from mcp_abfall.registry import ArgSpec, Provider, normalize, save

REPO_ROOT = wcs.WCS_PKG.parents[2]
DOC_ROOT = REPO_ROOT / "doc"
README = REPO_ROOT / "README.md"

#: Laendername im README -> ISO-Code. Nur was wir wirklich brauchen.
_README_COUNTRIES = {"germany": "de", "austria": "at", "switzerland": "ch"}

_SUMMARY = re.compile(r"^<summary>(?P<name>[^<]+)</summary>\s*$", re.MULTILINE)
_DOC_LINK = re.compile(r"^-\s*\[(?P<title>[^\]]+)\]\((?P<path>/doc/(?:source|ics)/(?P<mod>[^)]+?)\.md)\)")


def readme_modules(country: str) -> dict[str, set[str]]:
    """Modulnamen je Land laut README-Sektionen (``<summary>Germany</summary>``).

    Das ist die verlaesslichste Laenderzuordnung: mehrere Module setzen weder
    ``COUNTRY`` noch tragen sie ein Laendersuffix (``stadtreinigung_hamburg``),
    stehen im README aber sauber unter ihrem Land. Zurueckgegeben werden zwei
    Mengen: Module unter ``doc/source`` und Dokumentseiten unter ``doc/ics``.
    """
    out: dict[str, set[str]] = {"source": set(), "ics": set()}
    if not README.is_file():
        return out

    text = README.read_text(encoding="utf-8", errors="replace")
    marks = [(m.start(), m.group("name").strip().lower()) for m in _SUMMARY.finditer(text)]
    for i, (start, name) in enumerate(marks):
        if _README_COUNTRIES.get(name) != country:
            continue
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        for line in text[start:end].splitlines():
            m = _DOC_LINK.match(line.strip())
            if m:
                kind = "ics" if "/doc/ics/" in m.group("path") else "source"
                out[kind].add(m.group("mod"))
    return out


def _country_of(name: str, meta: wcs.SourceMeta, readme_de: set[str]) -> str:
    """Land eines Source-Moduls.

    Reihenfolge: README-Sektion, dann die ``COUNTRY``-Konstante, dann das
    Namenssuffix (``jumomind_de``) - denn nicht jedes Modul setzt ``COUNTRY``.
    """
    if name in readme_de:
        return "de"
    if meta.country:
        return meta.country.lower()
    suffix = name.rsplit("_", 1)[-1]
    if len(suffix) == 2 and suffix.isalpha():
        return suffix.lower()
    return ""


def _arg_specs(name: str, meta: wcs.SourceMeta) -> list[ArgSpec]:
    """Konstruktor-Signatur der Source als Argumentliste."""
    try:
        sig = inspect.signature(wcs.import_source(name).Source.__init__)
    except (AttributeError, ValueError, TypeError):
        return []
    labels = meta.param_translations.get("de", {}) or {}
    specs: list[ArgSpec] = []
    for pname, param in sig.parameters.items():
        if pname in ("self", "args", "kwargs"):
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None
        specs.append(
            ArgSpec(
                name=pname,
                required=not has_default,
                label=labels.get(pname),
                default=str(default) if default not in (None, "") else None,
            )
        )
    return specs


def _slug(text: str, maxlen: int = 40) -> str:
    s = normalize(text).replace(" ", "-")[:maxlen].strip("-")
    return s or "x"


def _provider_id(source: str, default_args: dict, title: str) -> str:
    """Stabile, menschenlesbare ID mit Hash-Suffix gegen Kollisionen."""
    payload = json.dumps(default_args, sort_keys=True, default=str)
    digest = hashlib.sha1(f"{source}|{payload}|{title}".encode()).hexdigest()[:6]
    return f"{source}.{_slug(title)}.{digest}"


def _open_args(specs: list[ArgSpec], default_args: dict) -> list[str]:
    """Pflichtargumente, die durch die Traeger-Vorbelegung noch nicht gesetzt sind."""
    return [s.name for s in specs if s.required and s.name not in default_args]


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


# --------------------------------------------------------------------------
# 1 + 2: Source-Module
# --------------------------------------------------------------------------


def _covers(default_args: dict, case_args: dict) -> bool:
    """Passt ein Testfall zur Vorbelegung eines Traegers?"""
    return all(str(case_args.get(k)) == str(v) for k, v in default_args.items())


def assign_test_cases(meta: wcs.SourceMeta, providers: list[Provider]) -> None:
    """Haengt TEST_CASES an genau den Traeger, den sie eindeutig treffen.

    Die Schluessel der TEST_CASES sind reale Orts- und Gemeindenamen und damit
    das wertvollste Suchmaterial ueberhaupt - ein Traeger heisst "Landkreis
    Steinfurt", gesucht wird aber nach "Emsdetten". Die Zuordnung ueber die
    Vorbelegung allein genuegt jedoch nicht: ``app_abfallplus_de`` gibt allen
    145 Staedten dieselbe ``app_id`` mit, wodurch der Testfall "Braunschweig"
    faelschlich auch unter "Berlin" landete. Deshalb wird ein Testfall nur
    uebernommen, wenn er innerhalb des Moduls **eindeutig** einem Traeger
    zuzuordnen ist.
    """
    if not meta.test_cases or not providers:
        return
    sole = providers[0] if len(providers) == 1 else None

    for label, args in meta.test_cases.items():
        if not isinstance(args, dict):
            continue
        example = {"name": str(label), "args": _jsonable(args)}

        if sole is not None:
            sole.examples.append(example)
            continue

        matches = [p for p in providers if p.default_args and _covers(p.default_args, args)]
        if len(matches) == 1:
            matches[0].examples.append(example)


def collect_module_providers(country: str, readme_source: set[str]) -> list[Provider]:
    providers: list[Provider] = []
    skipped: list[tuple[str, str]] = []

    for name in wcs.list_source_names():
        try:
            meta = wcs.read_meta(name)
        except Exception as exc:  # defektes Upstream-Modul soll den Build nicht kippen
            skipped.append((name, f"{type(exc).__name__}: {exc}"))
            continue
        if _country_of(name, meta, readme_source) != country:
            continue
        if name == "ics":
            continue  # kommt ueber doc/ics/ mit echten Konfigurationen

        specs = _arg_specs(name, meta)
        doc = (meta.description or "").strip() or None
        of_module: list[Provider] = []

        if meta.extra_info:
            for entry in meta.extra_info:
                title = str(entry.get("title") or meta.title).strip()
                dargs = _jsonable(entry.get("default_params") or {})
                of_module.append(
                    Provider(
                        id=_provider_id(name, dargs, title),
                        source=name,
                        title=title,
                        country=country,
                        url=entry.get("url") or meta.url,
                        default_args=dargs,
                        arg_specs=specs,
                        open_args=_open_args(specs, dargs),
                        doc=doc,
                    )
                )
        else:
            # Modul bedient genau einen Traeger (z.B. eine einzelne Stadt).
            of_module.append(
                Provider(
                    id=_provider_id(name, {}, meta.title),
                    source=name,
                    title=meta.title,
                    country=country,
                    url=meta.url,
                    default_args={},
                    arg_specs=specs,
                    open_args=_open_args(specs, {}),
                    doc=doc,
                )
            )

        assign_test_cases(meta, of_module)
        providers.extend(of_module)

    if skipped:
        print(f"  uebersprungen ({len(skipped)}):", file=sys.stderr)
        for n, why in skipped:
            print(f"    {n}: {why}", file=sys.stderr)
    return providers


# --------------------------------------------------------------------------
# 3: doc/ics/*.md
# --------------------------------------------------------------------------

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_EXAMPLE = re.compile(
    r"^###\s+(?P<name>.+?)\s*$\s*```yaml\s*$(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)


def _extract_ics_args(block) -> dict | None:
    """Zieht ``args`` aus einem configuration.yaml-Beispielblock."""
    if not isinstance(block, dict):
        return None
    sources = (block.get("waste_collection_schedule") or {}).get("sources")
    if not isinstance(sources, list) or not sources:
        return None
    first = sources[0]
    if not isinstance(first, dict):
        return None
    args = first.get("args")
    if not isinstance(args, dict) or not args:
        return None
    return _jsonable(args)


def _parse_ics_doc(path: Path) -> Provider | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _H1.search(text)
    title = m.group(1).strip() if m else path.stem
    if title.lower().startswith("ics"):
        return None

    examples: list[dict] = []
    for match in _EXAMPLE.finditer(text):
        try:
            block = yaml.safe_load(match.group("body"))
        except yaml.YAMLError:
            continue
        args = _extract_ics_args(block)
        if args:
            examples.append({"name": match.group("name").strip(), "args": args})

    if not examples:
        return None

    url = None
    link = re.search(r"<(https?://[^>]+)>", text)
    if link:
        url = link.group(1)

    return Provider(
        id=_provider_id("ics", {"doc": path.stem}, title),
        source="ics",
        title=title,
        country="de",
        url=url,
        default_args={},
        arg_specs=[],
        open_args=[],
        examples=examples,
        doc=f"Generische ICS-Quelle, konfiguriert laut doc/ics/{path.name}.",
    )


def collect_ics_providers(allowed: set[str] | None = None) -> list[Provider]:
    """ICS-Dokumentseiten einlesen; ``allowed`` beschraenkt auf ein Land."""
    ics_dir = DOC_ROOT / "ics"
    if not ics_dir.is_dir():
        print(f"  Hinweis: {ics_dir} fehlt, ICS wird uebersprungen.", file=sys.stderr)
        return []
    out = []
    for path in sorted(ics_dir.glob("*.md")):
        if allowed is not None and path.stem not in allowed:
            continue
        try:
            p = _parse_ics_doc(path)
        except Exception as exc:
            print(f"    {path.name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if p:
            out.append(p)
    return out


# --------------------------------------------------------------------------


def dedupe(providers: list[Provider]) -> list[Provider]:
    """Gleiche ID = gleicher Traeger; Beispiele werden zusammengefuehrt."""
    merged: dict[str, Provider] = {}
    for p in providers:
        prev = merged.get(p.id)
        if prev is None:
            merged[p.id] = p
            continue
        seen = {e["name"] for e in prev.examples}
        prev.examples.extend(e for e in p.examples if e["name"] not in seen)
    return sorted(merged.values(), key=lambda p: (p.title.lower(), p.source))


def main() -> int:
    ap = argparse.ArgumentParser(description="Baut data/providers.json.")
    ap.add_argument("--country", default="de", help="ISO-Laendercode (Default: de)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    readme = readme_modules(args.country)
    print(
        f"README-Sektion '{args.country}': {len(readme['source'])} Source-Module, "
        f"{len(readme['ics'])} ICS-Seiten"
    )

    print(f"Sammle Source-Module fuer Land '{args.country}' ...")
    mods = collect_module_providers(args.country, readme["source"])
    print(f"  {len(mods)} Traeger aus Source-Modulen")

    print("Sammle ICS-Konfigurationen aus doc/ics ...")
    ics = collect_ics_providers(readme["ics"] or None)
    print(f"  {len(ics)} Traeger aus ICS-Dokumentation")

    providers = dedupe(mods + ics)
    path = save(providers, args.out)

    with_examples = sum(1 for p in providers if p.examples)
    print(
        f"\n{len(providers)} Traeger geschrieben nach {path}\n"
        f"  davon mit Beispielorten: {with_examples}\n"
        f"  Quell-Module: {len({p.source for p in providers})}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
