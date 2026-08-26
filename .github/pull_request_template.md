## Worum geht es

<!-- Kurz: was ändert sich und warum. -->

## Prüfliste

- [ ] `uv run ruff check src scripts tests` läuft durch
- [ ] `uv run pytest` läuft durch
- [ ] Bei Änderungen am Submodule oder am Registry-Builder: `data/providers.json`
      neu gebaut und mitcommittet
- [ ] Bei einem behobenen Fehler: ein Testfall, der ihn festnagelt

## Für einen neuen Träger-Auflöser

- [ ] Die Auswahl trifft `picker`, nicht der Auflöser selbst — damit überall
      dieselbe Sicherheitsschwelle gilt
- [ ] Ist nichts eindeutig, geht die Liste über `LookupNeedsChoice` zurück,
      statt dass geraten wird
- [ ] An einer echten Adresse geprüft (bitte im PR nennen, welcher Ort — ohne
      vollständige Wohnanschrift)
