# Sicherheit

## Unterstützte Versionen

Gepflegt wird jeweils die neueste veröffentlichte Version.

| Version | Unterstützt |
|---|---|
| 0.1.x | ja |

## Eine Schwachstelle melden

Bitte **kein öffentliches Issue** dafür anlegen. Nutze stattdessen die private
Meldung über GitHub:

> Reiter **Security** → **Report a vulnerability**

Hilfreich sind: was passiert, wie es sich reproduzieren lässt, und welche
Auswirkung du siehst. Eine Rückmeldung kommt, sobald ich dazu komme — das ist
ein Freizeitprojekt, kein Produkt mit Bereitschaftsdienst.

## Was dieser Server tut

Für die Einschätzung von Meldungen ist der Zuschnitt wichtig:

- Der Server **ruft fremde Portale ab** — die der Entsorgungsträger — und
  [Nominatim](https://nominatim.openstreetmap.org/) für die Adressauflösung.
  Deren Antworten sind nicht vertrauenswürdig und werden geparst.
- Er **verarbeitet Adressen**. Das sind personenbezogene Daten. Sie gehen an
  Nominatim und an das jeweilige Portal, weil es ohne sie keine Abfuhrtermine
  gibt. Aufgeloeste Adressen liegen zwischengespeichert unter
  `~/.cache/mcp-abfall/` bzw. dem in `MCP_ABFALL_CACHE_DIR` gesetzten Pfad.
- Er **hält keine Zugangsdaten** und braucht keine.
- Die Ausführung von Quellmodulen aus dem Submodule ist bewusst: es ist die
  Datenbasis. Wer dem Submodule nicht traut, sollte das Projekt nicht
  einsetzen.

## HTTP-Betrieb

`--http` bindet standardmäßig auf `127.0.0.1` und hat **keine
Authentifizierung**. Wer den Server über die eigene Maschine hinaus
erreichbar macht, muss selbst für Zugriffsschutz sorgen — und dabei bedenken,
dass jede Anfrage die Portale der Träger und Nominatim belastet.
