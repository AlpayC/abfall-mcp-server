# mcp-abfall

MCP-Server für die Abfall- und Umweltkalender deutscher Städte und Landkreise.
Fragt Abfuhrtermine (Restmüll, Biotonne, Papier, Gelber Sack, Sperrmüll,
Schadstoffmobil …) zu einer Adresse ab.

```
Adresse ──▶ Nominatim ──▶ Gemeinde + Landkreis ──▶ Trägersuche (995 Träger)
                                                          │
                          Abfuhrtermine ◀── Portal ◀── Argumente auflösen
```

## Warum das nicht trivial ist

Abfallwirtschaft ist in Deutschland kommunal organisiert. Es gibt **keine
bundesweite Schnittstelle** — rund 400 öffentlich-rechtliche Entsorgungsträger
betreiben je eigene Portale, hinter denen eine Handvoll Softwareplattformen
steckt (Abfall.IO/AbfallPlus, AbfallNavi, Jumomind, AWIDO, C-Trace, Müllmax,
dazu viele direkte ICS-Exporte).

Dieser Server nutzt als Datenbasis
[`mampfes/hacs_waste_collection_schedule`](https://github.com/mampfes/hacs_waste_collection_schedule)
(MIT) — ein aktiv gepflegtes Projekt mit über 950 Quellmodulen. Dessen inneres
Package ist Home-Assistant-unabhängig und wird hier als Git-Submodule
eingebunden und angesteuert.

Die eigentliche Arbeit dieses Projekts liegt darin, aus einer *Adresse* den
zuständigen Träger **und dessen interne Parameter** zu ermitteln. In Home
Assistant klickt ein Mensch das einmalig zusammen; ein MCP-Server muss es selbst
können.

## Installation

```bash
git clone <repo> && cd mcp-abfall
git submodule update --init --depth 1
uv sync
uv run python scripts/build_registry.py   # erzeugt data/providers.json
uv run pytest
```

## Einbinden

Lokal per stdio — in `claude_desktop_config.json` bzw. `.mcp.json`:

```json
{
  "mcpServers": {
    "abfall": {
      "command": "uv",
      "args": ["--directory", "/pfad/zu/mcp-abfall", "run", "mcp-abfall"]
    }
  }
}
```

Als HTTP-Dienst:

```bash
uv run mcp-abfall --http --host 127.0.0.1 --port 8000
```

Beim HTTP-Betrieb sollte bedacht werden, dass jede Anfrage die Portale der
Träger und Nominatim belastet. Für mehr als den Eigenbedarf gehört ein Cache
davor und eine eigene Nominatim-Instanz dahinter
(`MCP_ABFALL_NOMINATIM_URL`).

## Tools

| Tool | Zweck |
|---|---|
| `abfuhrtermine` | Adresse rein, Termine raus. Der übliche Einstieg. |
| `finde_traeger` | Träger nach Orts- oder Betriebsnamen suchen, ohne Geocoding. |
| `traeger_details` | Welche Argumente erwartet ein Träger? |
| `abfuhrtermine_fuer_traeger` | Gezielte Abfrage, u.a. für Antworten auf Rückfragen. |
| `abdeckung` | Wie viele Träger und Datenquellen sind erfasst. |

Ergänzend die Ressource `abfall://traeger` mit der vollständigen Trägerliste.

### Rückfragen statt Raten

Kann eine Angabe nicht zweifelsfrei bestimmt werden, liefert der Server
`status: "rueckfrage"` samt konkreter Auswahlliste statt zu raten. Das ist
Absicht: ein falsch geratener Ort liefert klaglos den Kalender der
Nachbargemeinde — ein falsches Ergebnis, das wie ein richtiges aussieht.

## Abdeckung, gemessen

`scripts/build_registry.py` erfasst **995 Entsorgungsträger** aus 150
Quellmodulen.

`scripts/smoke.py` fragt echte Adressen gegen die echten Portale ab. Der Lauf
über 18 Adressen quer durch Deutschland (Stand: Aug 2026):

| Ergebnis | Anteil |
|---|---|
| Termine direkt geliefert | 28 % |
| Rückfrage nach einer fehlenden Angabe | 44 % |
| Kein Träger lieferte Termine | 28 % |

Das ist die ehrliche Zahl, keine Schätzung — und der Grund, sie hier zu nennen:
„deckt alle deutschen Städte ab" stimmt für die *Trägerliste*, nicht für die
vollautomatische Auflösung aus einer blanken Adresse.

### Woran die restlichen Fälle scheitern

* **Technische ID-Argumente.** Manche Träger verlangen interne Kennungen
  (`hnId` in Hamburg, `standort` in Dresden, `idHouseNumber` in Leipzig), für
  die es keinen Nachschlagepfad im Klartext gibt. Für Abfall.IO — mit 41
  Trägern der mit Abstand größte Fall — ist der Auswahldialog in
  `lookup.py` nachgebaut; die übrigen sind Einzelfälle und je Modul zu ergänzen.
* **Portale, die abweichende Schreibweisen führen** und keine Vorschlagsliste
  mitliefern.
* **Ausfälle und Ratenbegrenzung** auf Seiten der Träger.

## Aufbau

| Datei | Aufgabe |
|---|---|
| `wcs.py` | Brücke zur vendorierten Bibliothek; registriert das Package gezielt, statt es auf den `sys.path` zu legen (das Elternverzeichnis enthält ein `calendar.py`, das die stdlib überschattet). |
| `registry.py` | Trägerliste und Ortssuche mit deutschem Stemming. |
| `geo.py` | Nominatim-Anbindung, Adressvarianten, Plausibilitätsprüfungen. |
| `resolve.py` | Adresse → Träger → aufgelöste Argumente → Termine. |
| `lookup.py` | Auswahldialog für Abfall.IO (numerische Standort-IDs). |
| `server.py` | MCP-Tools, stdio und HTTP. |

Die Registry wird nicht zur Laufzeit gebaut: `data/providers.json` entsteht
per Skript, damit der Serverstart nicht 150 Module importieren muss. Nach einem
Submodule-Update lohnt ein erneuter Lauf.

## Datenquellen und Nutzung

Die Termine stammen von den Portalen der jeweiligen Entsorgungsträger, die
Adressauflösung von [Nominatim](https://nominatim.openstreetmap.org/)
(OpenStreetMap). Für Nominatim gilt eine Nutzungsrichtlinie — höchstens eine
Anfrage pro Sekunde; der Server hält sie ein und legt Ergebnisse in
`~/.cache/mcp-abfall/` ab.

Bei Terminen, an denen etwas hängt (Sperrmüll, Schadstoffmobil), lohnt der
Blick auf die Portaladresse, die jede Antwort mitliefert.

## Lizenz

MIT. Das Submodule `vendor/hacs_waste_collection_schedule` steht unter eigener
MIT-Lizenz, Copyright (c) 2020 Steffen Zimmermann.
