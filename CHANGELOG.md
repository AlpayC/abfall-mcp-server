# Changelog

Alle nennenswerten Änderungen an diesem Projekt. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

## [0.1.0] – 2026-08-26

Erste Veröffentlichung.

### Hinzugefügt

- MCP-Server mit fünf Tools: `abfuhrtermine` (Adresse → Termine),
  `finde_traeger`, `traeger_details`, `abfuhrtermine_fuer_traeger`,
  `abdeckung`; dazu die Ressource `abfall://traeger`.
- Transporte stdio (Standard) und Streamable HTTP (`--http`).
- Registry mit **995 Entsorgungsträgern** aus 150 Quellmodulen, gebaut aus
  [hacs_waste_collection_schedule](https://github.com/mampfes/hacs_waste_collection_schedule).
- Ortssuche mit deutschem Stemming: „Bremen" findet die „Bremer
  Stadtreinigung", „Nürnberg" die „Nürnberger Land".
- Adressauflösung über Nominatim mit Vergröberungskette, PLZ- und
  Ortsvalidierung.
- Generische Argumentauflösung über die Vorschlagslisten, die die Quellmodule
  in ihren Exceptions mitführen — deckt rund 320 Träger ohne eigenen Code ab.
- Eigene Adressdialoge für Träger mit internen Kennungen: Abfall.IO
  (41 Träger), Stadtreinigung Hamburg (`hnId`), Berliner
  Stadtreinigungsbetriebe (`schedule_id`).
- Abgleich abgekürzter Straßennamen („Bahnhofstr." ↔ „Bahnhofstraße") und
  Hausnummernbereiche inklusive Straßenseiten-Parität („5" liegt in „1-9",
  nicht in „2-8").
- `scripts/smoke.py` misst die Abdeckung gegen die echten Portale, statt sie
  zu behaupten.

### Verhalten

- Ist eine Angabe nicht zweifelsfrei bestimmbar, liefert der Server
  `status: "rueckfrage"` mit konkreter Auswahlliste, statt zu raten. Ein
  falsch geratener Ort liefert klaglos den Kalender der Nachbargemeinde —
  ein falsches Ergebnis, das wie ein richtiges aussieht.
- Eine leere Terminliste wird als `status: "leer"` gemeldet, nicht als
  „keine Abfuhr": mehrere Portale antworten auf falsche Argumente nicht mit
  einem Fehler, sondern mit einer leeren Liste.
- Ein Träger wird nur ungefragt abgefragt, wenn er hinreichend sicher zur
  Adresse passt (`MIN_AUTO_FETCH`).

[Unveröffentlicht]: https://github.com/AlpayC/mcp-abfall/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AlpayC/mcp-abfall/releases/tag/v0.1.0
