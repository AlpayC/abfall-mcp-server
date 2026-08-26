# Mitarbeiten

Danke für dein Interesse. Der häufigste und nützlichste Beitrag ist ein
Hinweis darauf, dass ein Träger nicht funktioniert — dazu gleich mehr.

## Einrichten

```bash
git clone --recurse-submodules https://github.com/AlpayC/mcp-abfall.git
cd mcp-abfall
uv sync
uv run python scripts/build_registry.py
uv run pytest
```

Ohne `--recurse-submodules` fehlt die Datenbasis unter `vendor/`; dann hilft
`git submodule update --init --depth 1`.

## Vor jedem Pull Request

```bash
uv run ruff check src scripts tests
uv run pytest
```

Wenn du am Submodule oder am Registry-Builder etwas änderst, gehört die
neu gebaute `data/providers.json` mit in denselben Commit. Die CI prüft das:
sie baut die Registry nach und schlägt fehl, wenn das Ergebnis abweicht.

## Der Grundsatz dieses Projekts

**Im Zweifel nachfragen, nicht raten.**

Ein falsch geratener Ort oder eine falsch geratene Straße liefert klaglos den
Abfuhrkalender der Nachbargemeinde. Das ist ein falsches Ergebnis, das wie ein
richtiges aussieht — der teuerste Fehler, den dieser Server machen kann, weil
niemand ihn bemerkt. Deshalb:

- Eine Zuordnung wird nur ungefragt übernommen, wenn sie sicher genug ist
  (`resolve.CONFIDENCE_THRESHOLD`, `server.MIN_AUTO_FETCH`).
- Ist sie es nicht, geht die Auswahlliste an den Aufrufer zurück
  (`status: "rueckfrage"`).
- Eine leere Antwort eines Portals ist ein Verdachtsfall, kein Ergebnis.

Wer diese Schwellen senken will, sollte einen Testfall mitliefern, der zeigt,
dass dabei nichts Falsches durchrutscht.

## Tests

Die Tests laufen ohne Netz. Was in `tests/` steht, sind überwiegend
Regressionen: jeder Fall dort ist ein Fehler, der einmal echten Schaden
angerichtet hat — die Suche nach „Berlin" fand die Stadtreinigung Gießen, eine
Emsdettener Adresse lieferte den Kalender von Meschede. Wenn du einen Fehler
behebst, gehört der Fall dazu, mit einem Satz dazu, was schiefging.

`scripts/smoke.py` geht dagegen an die echten Portale. Das ist kein Test,
sondern eine Messung, und sie gehört nicht in die CI: fremde Server sind kein
Prüfgegenstand, und jeder Lauf belastet sie. Bitte sparsam einsetzen.

## Einen Träger ergänzen oder reparieren

Die Datenbasis kommt aus
[hacs_waste_collection_schedule](https://github.com/mampfes/hacs_waste_collection_schedule).
Deshalb zuerst die Frage, wohin der Beitrag gehört:

- **Der Träger fehlt ganz oder sein Portal hat sich geändert** → das gehört
  stromaufwärts in das Upstream-Projekt. Davon profitieren alle, die es
  nutzen, und wir bekommen es beim nächsten Submodule-Update automatisch.
- **Der Träger ist vorhanden, aber die Adressauflösung greift nicht** → das
  gehört hierher. Typisch: er verlangt eine interne Kennung
  (`standort`, `idHouseNumber`, `streetnr`), die aus einer Adresse nicht
  herzuleiten ist.

Für den zweiten Fall gibt es das Muster in `src/mcp_abfall/lookup.py`: dort
steht je Träger ein Auflöser, der dessen Adressdialog nachbaut. Alle haben
dieselbe Form —

```python
def resolve_beispiel(default_args, address, picker, *, min_confidence, timeout):
    ...
    return {"interne_id": wert}
```

`address` enthält `city`, `district`, `street` und `house_number`. Die Auswahl
trifft nicht der Auflöser selbst, sondern `picker` (das ist
`resolve.pick_suggestion`) — so gilt überall dieselbe Schwelle. Ist nichts
eindeutig, wirft `_choose` ein `LookupNeedsChoice`, und die Liste geht an den
Nutzer. Eintragen in `RESOLVERS`, fertig.

Als Vorlage taugen die Wizards des Upstreams unter
`vendor/hacs_waste_collection_schedule/custom_components/waste_collection_schedule/waste_collection_schedule/wizard/`.
Sie sind interaktiv gedacht, zeigen aber den Weg durch das Portal. Verlass dich
nicht blind darauf: der Hamburger Wizard war beim Bau bereits veraltet, das
Portal hatte umgestellt.

## Stil

- Deutschsprachige Kommentare und Bezeichner in der Fachlogik, weil die Domäne
  deutsch ist — `Traeger`, `Abfuhrtermine`, `Rueckfrage`.
- Kommentare erklären das *Warum*, besonders bei allem, was nach einer
  seltsamen Sonderbehandlung aussieht. Die meisten davon sind Narben.
- `ruff` entscheidet über Formalien.
