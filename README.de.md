# abfall-mcp-server

*Deutsch · [English](README.md)*

[![CI](https://github.com/AlpayC/abfall-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/AlpayC/abfall-mcp-server/actions/workflows/ci.yml)
[![Lizenz: MIT](https://img.shields.io/badge/Lizenz-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Träger: 995](https://img.shields.io/badge/Entsorgungstr%C3%A4ger-995-green.svg)](data/providers.json)

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

Der Server läuft **aus einem Repository-Checkout**, nicht als installiertes
Paket: er braucht die Datenbasis unter `vendor/` und die Registry unter
`data/`, beide relativ zum Projektverzeichnis. Deshalb gibt es ihn auch nicht
auf PyPI — ein Wheel wäre installierbar und trotzdem funktionsunfähig.

```bash
git clone --recurse-submodules https://github.com/AlpayC/abfall-mcp-server.git
cd abfall-mcp-server
uv sync
uv run pytest
```

`data/providers.json` liegt im Repository, der Server startet also sofort.
Nach einem Submodule-Update baust du sie neu:

```bash
uv run python scripts/build_registry.py
```

## Einbinden

Öffentlich per Streamable HTTP:

```json
{
  "mcpServers": {
    "abfall": {
      "url": "https://abfall-mcp.alpaycelik.dev/mcp"
    }
  }
}
```

Der Status des Dienstes steht unter
[`https://abfall-mcp.alpaycelik.dev/health`](https://abfall-mcp.alpaycelik.dev/health).

Lokal per stdio — in `claude_desktop_config.json` bzw. `.mcp.json`:

```json
{
  "mcpServers": {
    "abfall": {
      "command": "uv",
      "args": ["--directory", "/pfad/zu/abfall-mcp-server", "run", "abfall-mcp-server"]
    }
  }
}
```

Als HTTP-Dienst:

```bash
uv run abfall-mcp-server --http --host 127.0.0.1 --port 8000
```

Beim HTTP-Betrieb sollte bedacht werden, dass jede Anfrage die Portale der
Träger und Nominatim belastet. Für mehr als den Eigenbedarf gehört ein Cache
davor und eine eigene Nominatim-Instanz dahinter
(`ABFALL_MCP_NOMINATIM_URL`).

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
über 21 Adressen quer durch Deutschland (Stand: Aug 2026):

| Ergebnis | Anteil |
|---|---|
| Termine direkt geliefert | 48 % |
| Rückfrage nach einer fehlenden Angabe | 14 % |
| Kein Träger lieferte Termine | 38 % |

Das ist die ehrliche Zahl, keine Schätzung — und der Grund, sie hier zu nennen:
„deckt alle deutschen Städte ab" stimmt für die *Trägerliste*, nicht für die
vollautomatische Auflösung aus einer blanken Adresse.

### Träger mit eigener ID-Auflösung

Einige Portale verlangen interne Kennungen, die aus einer Adresse nicht
herzuleiten sind. Für diese ist der Adressdialog in `lookup.py` nachgebaut:

| Träger | Kennung | Umfang |
|---|---|---|
| Abfall.IO / AbfallPlus | `f_id_kommune`, `f_id_strasse`, … | 41 Träger |
| Stadtreinigung Hamburg | `hnId` | Hamburg |
| Berliner Stadtreinigungsbetriebe | `schedule_id` | Berlin |

Bei Hamburg ist der Upstream-Wizard inzwischen veraltet — das Portal hat das
Formular auf eine JavaScript-Komponente umgestellt, deren Adress-Endpunkt
hier aus der Seite gelesen wird.

### Woran die restlichen Fälle scheitern

* **Weitere ID-Argumente** ohne Nachschlagepfad: `standort` in Dresden,
  `idHouseNumber` in Leipzig, `streetnr` in Stuttgart. Je ein Auflöser mehr,
  nach demselben Muster wie die drei oben.
* **Portale, die abweichende Schreibweisen führen** und keine Vorschlagsliste
  mitliefern (Erfurt, Kiel).
* **Ausfälle, Ratenbegrenzung und kaputte Antworten** auf Seiten der Träger
  (Saarbrücken liefert HTML statt ICS).

## Aufbau

| Datei | Aufgabe |
|---|---|
| `wcs.py` | Brücke zur vendorierten Bibliothek; registriert das Package gezielt, statt es auf den `sys.path` zu legen (das Elternverzeichnis enthält ein `calendar.py`, das die stdlib überschattet). |
| `registry.py` | Trägerliste und Ortssuche mit deutschem Stemming. |
| `geo.py` | Nominatim-Anbindung, Adressvarianten, Plausibilitätsprüfungen. |
| `resolve.py` | Adresse → Träger → aufgelöste Argumente → Termine. |
| `lookup.py` | Adressdialoge der Träger mit internen IDs (Abfall.IO, Hamburg, BSR). |
| `server.py` | MCP-Tools, stdio und HTTP. |

Die Registry wird nicht zur Laufzeit gebaut: `data/providers.json` entsteht
per Skript, damit der Serverstart nicht 150 Module importieren muss. Nach einem
Submodule-Update lohnt ein erneuter Lauf.

## Datenquellen und Nutzung

Die Termine stammen von den Portalen der jeweiligen Entsorgungsträger, die
Adressauflösung von [Nominatim](https://nominatim.openstreetmap.org/)
(OpenStreetMap). Für Nominatim gilt eine Nutzungsrichtlinie — höchstens eine
Anfrage pro Sekunde; der Server hält sie ein und legt Ergebnisse in
`~/.cache/abfall-mcp-server/` ab.

Bei Terminen, an denen etwas hängt (Sperrmüll, Schadstoffmobil), lohnt der
Blick auf die Portaladresse, die jede Antwort mitliefert.

## Mitarbeiten

Der nützlichste Beitrag ist ein Hinweis darauf, dass ein Träger nicht
funktioniert — dafür gibt es eine
[Issue-Vorlage](.github/ISSUE_TEMPLATE/provider.yml) mit den richtigen Fragen.
Wie man einen Träger-Auflöser ergänzt, steht in
[CONTRIBUTING.md](CONTRIBUTING.md); Sicherheitsmeldungen gehören vertraulich
gemeldet, siehe [SECURITY.md](SECURITY.md). Änderungen stehen im
[CHANGELOG](CHANGELOG.md), Hinweise für Coding-Agents in
[AGENTS.md](AGENTS.md).

Diese Dateien sind auf Englisch, damit auch Beitragende außerhalb des
deutschsprachigen Raums mitarbeiten können. Der Code selbst bleibt bei
deutschen Bezeichnern — `Traeger`, `Abfuhrtermine`, `Rueckfrage` —, weil die
Domäne deutsch ist und es für diese Begriffe keine saubere Entsprechung gibt.

Ein Grundsatz zieht sich durch das ganze Projekt und gilt auch für Beiträge:
**im Zweifel nachfragen, nicht raten.** Ein falsch geratener Ort liefert
klaglos den Kalender der Nachbargemeinde — ein falsches Ergebnis, das wie ein
richtiges aussieht.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Das Submodule
`vendor/hacs_waste_collection_schedule` steht unter eigener MIT-Lizenz,
Copyright (c) 2020 Steffen Zimmermann — dieses Repository referenziert es nur,
es liefert den Code nicht mit. Die Nennungen Dritter stehen in
[NOTICE](NOTICE).
