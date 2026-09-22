# jev_grading_demo: Design-Spec

Stand: 2026-09-22. Status: vom Auftraggeber (Jan Eggers) in vier Abschnitten freigegeben, siehe Abschnitt 2.

## 1. Ziel und Rahmen

Eine Demo-Webseite, auf der man ein PDF per Drag&Drop hochlädt. Der Textinhalt wird von
Jev (TypeSafe "System One", Modell `typesafe/jev-1.13` über OpenRouter) inhaltlich beurteilt.
Die Fragen stehen in `config.yaml`, lassen sich aber in der Browser-Session per Formular
verändern. Ergebnisse erscheinen als Farbfelder (noul, choice), Balkengrafiken (score,
Manifesto-Anteile, Kennzahlen) und als JSON-Download.

Zwei Bewertungsmodi werden nebeneinander getestet: Gesamttext (ein Aufruf über den ganzen
Text) und Chunks (Text in Stücke geteilt, Ergebnisse token-gewichtet gemittelt).

Zielgruppe: Kolleginnen und Kollegen bei WDR, die einen Link und ein gemeinsames Passwort
bekommen. Deployment als Container auf dem Weihnachtswunderserver unter
`https://woistderbus.interaktive-projekte.de/jev_grading_demo/`.

Vorlage für Muster und Code: das Referenzprojekt `~/Code/jev_grading_test` (Leiter-Umrechnung,
Retry-Logik, Manifesto-Fragenbauer). Es wird nicht importiert, sondern als Vorbild gelesen.

## 2. Entscheidungen aus der Designphase

| Frage | Entscheidung |
| --- | --- |
| Zugang | Gemeinsames Passwort in der App, aus `APP_PASSWORD` in der Umgebung. Kein offener Endpunkt. |
| Default-Schema | Manifesto-Block (nur Hauptkategorien) mit Kennzahlen rile, planeco, markeco, welfare, intpeace, plus Score-Leitern, eine Choice-Frage und Nouls. Alle drei Jev-Antworttypen sind sichtbar. |
| Bearbeitung in der Session | Formular pro Frage: Typ, Instruction, Kriterien, Aktiv-Schalter, hinzufügen, löschen. Manifesto-Katalog selbst nicht editierbar. |
| Überlänge im Gesamttext-Modus | Abschneiden auf das Budget, deutliche Warnung mit dem bewerteten Anteil. |
| Framework | Streamlit, ein Prozess. |
| Jev-Zugang | OpenRouter `POST https://openrouter.ai/api/alpha/decisions`, nativer TypeSafe-Body. |
| Token-Schätzung | Heuristik Zeichen / 3,5 (kalibriert an einer Messung: 25.291 Zeichen deutscher Text = 7.107 Jev-Token). Kein tiktoken, weil Jevs Tokenizer ohnehin unbekannt ist und die API bei Überlänge sauber mit HTTP 400 antwortet. |

## 3. Verifizierte Fakten zur API (Probe am 2026-09-22)

- `chat/completions` lehnt Jev ab: "is a decisions model ... Use the /api/alpha/decisions endpoint instead."
- `POST /api/alpha/decisions` mit `{"model", "state", "questions"}` liefert dieselbe Antwortform
  wie die native TypeSafe-API: `answers`, `usage` (mit zusätzlichem `cost` in USD), `model`, `id`, `provider`.
  `/api/v1/systemone` funktioniert ebenfalls, ist aber undokumentiert; wir nutzen den Pfad, den die Fehlermeldung nennt.
- `state` darf String oder Objekt sein. Wir senden `{"text_type": ..., "text": ...}`.
- Antwortformen:
  - noul: `{"type": "noul", "noul": 0.93}`
  - choice: `{"type": "choice", "choice": "<Label>", "probabilities": {<Label>: p}, "confidence": c}`
  - score: `{"type": "score", "score": 2.97, "legend": {"0": "...", ...}, "probabilities": {"0": p, ...}, "confidence": c}`;
    `score` ist der Erwartungswert über die Stufenindizes 0..n-1.
- choice verlangt `criteria` als Objekt (Label → Beschreibung); eine Liste wird mit HTTP 400 abgelehnt.
  score verlangt `criteria` als Liste (geordnete Leiter).
- Limit: bis etwa 27.500 Input-Token geht der Aufruf durch, darüber HTTP 400 mit
  `{"detail": {"error_type": "max_tokens_exceeded"}}`. Kein stilles Abschneiden. OpenRouter meldet
  `context_length` 32.000.
- Preis: 0,042 USD je 1 Mio. Input-Token, Output kostenlos. Antwortzeiten 0,4 bis 1,5 s.

## 4. Architektur

Ein Streamlit-Prozess. Alles, was rechnet, liegt im Paket `jevdemo/` ohne Streamlit-Import und
ist einzeln testbar. `app.py` und `jevdemo/ui/` sind nur Verdrahtung und Darstellung.

```
jev_grading_demo/
  app.py                       Streamlit: Passwort-Gate, Layout, Session-State, Verdrahtung
  jevdemo/
    __init__.py
    config.py                  config.yaml laden, validieren, serialisieren, in Jev-Fragen übersetzen
    manifesto.py               mp_v5.json → 57 Hauptkategorien, Choice-Frage, Anteile, Kennzahlen
    pdf_text.py                PDF-Bytes → Seitentexte (PyMuPDF), Silbentrennung, Normalisierung
    chunking.py                Seiten → Einheiten (Chunks oder gekürzter Gesamttext), Token-Schätzung
    jev_client.py              OpenRouter-Client: Aufruf, Retry, Fehlerklassen, Kosten
    scoring.py                 Fragen packen, Aufrufe parallel ausführen, Aggregation
    results.py                 Ergebnisobjekt zusammenbauen, JSON
    ui/
      editor.py                Formular pro Frage
      views.py                 Farbfelder, Balken, Tabellen, Metazeile
  config.yaml                  Default-Fragen
  manifesto/mp_v5.json         Manifesto-Katalog (77 Einträge, wird zu 57 Hauptkategorien geklappt)
  manifesto/codebook_*.pdf     Quelle der Kennzahl-Formeln
  tests/                       pytest, ohne Netz; ein markierter Live-Rauchtest
  .streamlit/config.toml       Upload-Limit, keine Telemetrie
  pyproject.toml, uv.lock, Dockerfile, compose.yaml, .env.example, .gitignore, README.md
  docs/superpowers/specs/      diese Spec
```

Abhängigkeiten: streamlit (≥ 1.57), pymupdf, pyyaml, plotly, pandas. Python 3.12. Paketverwaltung uv.

### 4.1 Datenfluss eines Laufs

1. Upload → `pdf_text.extract_pages(bytes)` liefert Seiten. Gecacht über `st.cache_data` mit dem
   SHA-256 der Datei als Schlüssel, damit Streamlit-Reruns nichts neu extrahieren.
2. Der Nutzer wählt Modus (Gesamttext, Chunks, Beide) und Chunk-Größe.
   `chunking` erzeugt Einheiten: Gesamttext-Modus eine Einheit (bei Überlänge gekürzt, mit Anteil),
   Chunk-Modus n Einheiten mit Seitenbezug.
3. `config.to_questions()` übersetzt die aktiven Fragen in Jev-Fragen; der Manifesto-Block wird
   zu einer Choice-Frage über die gewählten Domänen.
4. `scoring.run()` packt pro Einheit die Fragen greedy in Gruppen unter dem Token-Budget und führt
   alle Aufrufe parallel aus (Thread-Pool, 6 Worker), mit Fortschritts-Callback. Einzelfehler werden
   gesammelt, der Lauf geht weiter.
5. `scoring.aggregate()` mittelt pro Frage token-gewichtet über die erfolgreichen Einheiten.
   `manifesto.kennzahlen()` rechnet aus den Anteilen die Kennzahlen.
6. `results.build()` erzeugt das Ergebnisobjekt (Meta, verwendete Config, Läufe je Modus mit
   Aggregat und Einheiten-Details). UI zeigt es an und bietet JSON und TXT zum Download.

Modus "Beide" führt erst Gesamttext, dann Chunks aus; beide Läufe landen im selben Ergebnisobjekt
und werden nebeneinander angezeigt.

## 5. Modul-Schnittstellen

Jedes Modul: was es tut, wie man es benutzt, wovon es abhängt.

### 5.1 `config.py`

Datenklassen:

```python
@dataclass
class Frage:
    name: str                       # Slug: [a-z0-9_]+, eindeutig
    type: str                       # "noul" | "choice" | "score" | "manifesto"
    instructions: str
    aktiv: bool = True
    criteria: list[str] | dict[str, str] | None = None   # score: Liste; choice: Dict
    skala: tuple[float, float] | None = None             # nur score
    domains: list[str] | None = None                     # nur manifesto, Domain-Codes "1".."7"
    kennzahlen: list[str] | None = None                  # nur manifesto

@dataclass
class Config:
    model: str
    text_typ: str
    chunk_tokens: int
    budget_tokens: int
    fragen: list[Frage]             # Reihenfolge = Anzeigereihenfolge
```

Funktionen:

- `load(path) -> Config`: YAML lesen, in Datenklassen wandeln. Wirft `ConfigError` bei Strukturfehlern.
- `validate(config) -> list[str]`: Liste menschenlesbarer Fehler, leer wenn gültig. Regeln:
  - `name` Slug und eindeutig; `instructions` nicht leer; `type` einer der vier.
  - score: `criteria` Liste mit ≥ 2 Stufen, `skala` zwei Zahlen mit min < max.
  - choice: `criteria` Dict mit ≥ 2 Einträgen, Labels nicht leer, Labels eindeutig.
  - noul: keine `criteria`, keine `skala`.
  - manifesto: höchstens eine Frage dieses Typs; `domains` Teilmenge von "1".."7", nicht leer;
    `kennzahlen` Teilmenge der bekannten Kennzahlen.
  - `chunk_tokens` 300..3000 (gleicher Bereich wie der Slider), `budget_tokens` 1000..28000.
- `to_questions(config, katalog) -> dict[str, dict]`: nur aktive Fragen; noul/choice/score
  1:1 ins Jev-Format (`type`, `instructions`, `criteria`); manifesto über `manifesto.build_question()`.
- `to_dict(config)`, `from_dict(d)`, `to_yaml(config) -> str`: für Editor-State, Download und das Ergebnis-JSON.

Hängt ab von: pyyaml, `manifesto`.

### 5.2 `manifesto.py`

- `load_catalog(path) -> list[Kategorie]`: liest `mp_v5.json`. Einträge mit `parent_code` werden auf
  den Elternteil zusammengeklappt: `code = parent_code`, `title = parent_title`, `domain` vom Kind,
  `description` = Verkettung der Kinder als "Kindtitel: Kindbeschreibung", getrennt durch Zeilenumbruch.
  Einträge ohne `parent_code` bleiben wie sie sind. Ergebnis: 57 Kategorien inklusive `000`, sortiert nach Code.
- `label(kat) -> str`: `"<code> <title>"`, z. B. `104 Military: Positive`. `code_of(label) -> str`: erstes Wort.
- `build_question(instructions, domains) -> dict`: Choice-Frage mit `criteria = {label: description}`
  über alle Kategorien der gewählten Domänen plus immer `000`.
- `anteile(probabilities: dict[str, float]) -> dict[str, float]`: Label-Wahrscheinlichkeiten → Prozent je Code.
- `domaenen(anteile) -> dict[str, float]`: Summe je Domain-Code "0".."7".
- `kennzahlen(anteile, welche) -> dict[str, float]`: Formeln aus dem Codebook (Abschnitt 3.6),
  auf Basis der Anteile in Prozent; fehlende Codes zählen 0:

```
rile     = (104+201+203+305+401+402+407+414+505+601+603+605+606)
         - (103+105+106+107+202+403+404+406+412+413+504+506+701)
planeco  = 403+404+412
markeco  = 401+414
welfare  = 503+504
intpeace = 102+105+106
```

Wertebereiche: rile -100..+100, die übrigen 0..100.

Hinweis für UI und README: Im Gesamttext-Modus sind die "Anteile" die Verteilung einer einzigen
Entscheidung über den ganzen Text, im Chunk-Modus der token-gewichtete Mittelwert vieler
Entscheidungen. Letzteres ist methodisch näher am Manifesto-Verfahren (Kodierung kleiner
Texteinheiten, dann Anteile). Das steht als Tooltip an den Kennzahlen.

Hängt ab von: nichts außer stdlib.

### 5.3 `pdf_text.py`

- `extract_pages(data: bytes) -> list[Seite]`, `Seite(nummer: int, text: str)`, Seiten ab 1.
  PyMuPDF `page.get_text("blocks")`, Blöcke werden zu Absätzen (durch Leerzeile getrennt).
  Innerhalb eines Blocks: Zeilen zusammenfügen; `-\n` gefolgt von Kleinbuchstabe wird zu nichts
  (Silbentrennung), sonst wird `\n` zu Leerzeichen. Mehrfache Leerzeichen zusammenziehen.
- Wirft `KeinText`, wenn alle Seiten zusammen weniger als 50 Zeichen ergeben (Scan ohne Textebene).
- Wirft `PdfFehler`, wenn PyMuPDF die Datei nicht öffnen kann.

Hängt ab von: pymupdf.

### 5.4 `chunking.py`

- `estimate_tokens(text) -> int` = `ceil(len(text) / 3.5)`.
- `Einheit(index: int, text: str, seite_von: int, seite_bis: int, tokens: int)`.
- `chunk_pages(pages, chunk_tokens) -> list[Einheit]`: Absätze aller Seiten in Reihenfolge greedy
  packen, bis `chunk_tokens` erreicht ist. Ein Absatz über `chunk_tokens` wird an Satzgrenzen
  (`[.!?]` gefolgt von Leerraum) geteilt und die Sätze gepackt. Ein letzter Chunk unter 25 % von
  `chunk_tokens` wird an den vorigen angehängt. Seitenbezug: erste und letzte Seite der enthaltenen Absätze.
- `whole_text(pages, max_tokens) -> tuple[Einheit, float]`: ganzer Text als eine Einheit; wenn über
  `max_tokens`, an der letzten Satzgrenze vor der Grenze abschneiden. Zweiter Wert: bewerteter Anteil
  (Zeichen gekürzt / Zeichen gesamt), 1.0 wenn nichts gekürzt.
- `shrink(einheit, faktor) -> Einheit`: um `faktor` (z. B. 0.15) kürzen, an Satzgrenze. Für den
  Fallback bei `max_tokens_exceeded`.

Hängt ab von: nichts außer stdlib.

### 5.5 `jev_client.py`

- `JevClient(api_key, model, endpoint="https://openrouter.ai/api/alpha/decisions", timeout=120)`.
- `decide(state, questions) -> Antwort`: POST mit `{"model", "state", "questions"}`, Header
  `Authorization: Bearer`, `Content-Type: application/json`, `HTTP-Referer` und `X-Title`
  (OpenRouter-Konvention, optional). Rückgabe: dict `answers`, `usage` (`input_tokens`, `output_tokens`,
  `cost`), `model`, `id`, `sekunden`.
- Retry bei HTTP 429, 500, 502, 503, 529 mit Backoff `2**versuch` Sekunden, maximal 4 Wiederholungen.
- Fehlerklassen: `ZuLang` (HTTP 400 mit `max_tokens_exceeded` im Body), `JevFehler(status, detail)` für alles andere.
- `cost_usd(usage) -> float`: `usage["cost"]` wenn vorhanden, sonst `input_tokens / 1e6 * 0.042`.
- Nur `urllib` aus der Standardbibliothek, wie im Referenzprojekt. Tests mocken `urllib.request.urlopen`.

Hängt ab von: stdlib.

### 5.6 `scoring.py`

- `question_tokens(question) -> int`: `estimate_tokens(json.dumps(question))`.
- `pack_questions(unit_tokens, questions, budget) -> list[dict[str, dict]]`: Fragen greedy in Gruppen,
  so dass `unit_tokens + sum(question_tokens) + 200 <= budget`. Passt eine Frage allein nicht,
  wird sie trotzdem als eigene Gruppe geschickt (die API entscheidet). Im Chunk-Modus ergibt das
  fast immer eine Gruppe pro Chunk; im Gesamttext-Modus steht der Manifesto-Block allein.
- `text_budget(questions, budget) -> int`: `budget - max(question_tokens) - 200`. Damit wird der
  Gesamttext vor dem Lauf gekürzt.
- `run(units, questions, client, kuerzbar: bool, workers=6, progress=None) -> Lauf`:
  - baut alle (Einheit, Gruppe)-Aufrufe, führt sie im `ThreadPoolExecutor` aus, ruft `progress(erledigt, gesamt)`.
  - `ZuLang` bei `kuerzbar=True` (Gesamttext, genau eine Einheit): Einheit um 15 % kürzen, Aufruf
    wiederholen, bis zu 3-mal; Anteil wird nachgeführt. Bei `kuerzbar=False`: Fehler der Einheit.
  - Andere Fehler: in `lauf.fehler` sammeln mit Einheit, Fragen-Gruppe, Meldung.
  - `Lauf`: `modus`, `einheiten: list[EinheitErgebnis]` (Einheit + `antworten: dict[name, answer]` +
    `fehler: str | None`), `anteil_bewertet`, `aufrufe`, `input_tokens`, `output_tokens`, `kosten_usd`,
    `sekunden`, `fehler: list`.
- `aggregate(lauf, config, katalog) -> dict[name, dict]`: token-gewichtetes Mittel über Einheiten mit
  vollständiger Antwort auf die jeweilige Frage. Gewicht = `einheit.tokens`.
  - noul: `{"type": "noul", "noul": mean, "min", "max", "n"}`.
  - choice: `probabilities` = gewichtetes Mittel je Option, `choice` = Argmax, `confidence` = Mittel,
    `argmax_anteile` = Anteil der Einheiten je Argmax.
  - score: `probabilities` je Stufenindex = gewichtetes Mittel, `stufe` = Erwartungswert
    `sum(i * p_i)`, `wert` = `skala[0] + stufe * (skala[1] - skala[0]) / (n - 1)`, `confidence` = Mittel.
  - manifesto (technisch choice, im Aggregat `"type": "manifesto"`): zusätzlich `anteile` (Prozent je Code), `domaenen`, `top`
    (Liste `[code, title, prozent]` absteigend), `kennzahlen`.
  - Fehlende Einheiten (Fehler) werden ausgelassen; `n` zählt die eingegangenen.
- `schaetzung(units, questions, budget) -> dict`: vor dem Lauf, für die UI: Zahl der Aufrufe,
  geschätzte Input-Token, geschätzte Kosten, grobe Dauer (`aufrufe / 6 * 0.8 s`).

Hängt ab von: `chunking`, `jev_client`, `manifesto`, `config`.

### 5.7 `results.py`

- `build(meta, config, laeufe: dict[str, Lauf], aggregate: dict[str, dict]) -> dict` und
  `to_json(result) -> str` (UTF-8, `ensure_ascii=False`, eingerückt).

JSON-Form:

```json
{
  "meta": {
    "erstellt": "2026-09-22T14:03:11+02:00",
    "app_version": "0.1.0",
    "modell": "typesafe/jev-1.13-20260917",
    "datei": "programm.pdf", "sha256": "…",
    "seiten": 48, "zeichen": 131044, "token_geschaetzt": 37441
  },
  "config": { "...": "Config wie verwendet, via config.to_dict" },
  "laeufe": {
    "gesamttext": {
      "modus": "gesamttext", "einheiten": 1, "anteil_bewertet": 0.69,
      "aufrufe": 2, "input_tokens": 41210, "output_tokens": 310, "kosten_usd": 0.00173, "sekunden": 2.4,
      "fehler": [],
      "aggregat": {
        "manifesto": { "type": "manifesto", "anteile": {"104": 12.3}, "domaenen": {"1": 20.1},
                       "top": [["104", "Military: Positive", 12.3]], "kennzahlen": {"rile": -8.2},
                       "confidence": 0.71, "n": 1 },
        "konkretheit": { "type": "score", "wert": 3.4, "stufe": 2.4, "probabilities": {"0": 0.0}, "confidence": 0.8, "n": 1 },
        "textsorte":   { "type": "choice", "choice": "Wahlprogramm", "probabilities": {}, "confidence": 0.97, "argmax_anteile": {}, "n": 1 },
        "regionalbezug": { "type": "noul", "noul": 0.88, "min": 0.88, "max": 0.88, "n": 1 }
      },
      "einheiten_detail": [
        { "index": 0, "seite_von": 1, "seite_bis": 48, "tokens": 25800, "zeichen": 90300,
          "antworten": { "manifesto": {"choice": "…", "probabilities": {}, "confidence": 0.7}, "konkretheit": {} },
          "fehler": null }
      ]
    },
    "chunks": { "modus": "chunks", "einheiten": 47, "anteil_bewertet": 1.0, "...": "gleiche Form" }
  }
}
```

`antworten` enthält die Jev-Rohantworten pro Frage (bei manifesto ohne die 57 Beschreibungen, nur
`choice`, `probabilities`, `confidence`). Damit ist jeder Aggregatwert aus dem JSON nachrechenbar.

### 5.8 `ui/editor.py` und `ui/views.py`

- `render_editor(config: Config, katalog) -> Config`: zeichnet das Formular in der Seitenleiste,
  liest die Widgets, gibt die aktuelle Config zurück. Editor-State lebt in `st.session_state["config"]`.
- `render_results(result: dict, katalog)`: Metazeile, dann je Modus eine Spalte mit den Blöcken in
  Config-Reihenfolge.
- Farben und Balken folgen dem dataviz-Skill (vor der Implementierung lesen): eine kategoriale
  Palette für Choice-Optionen und Domänen, eine divergierende Skala rot–neutral–grün für noul und rile,
  eine sequenzielle für Score-Stufen.

## 6. Default-`config.yaml`

```yaml
model: typesafe/jev-1.13
text_typ: Deutschsprachiges politisches Dokument, zum Beispiel ein Wahl- oder Parteiprogramm
chunk_tokens: 800
budget_tokens: 26000

fragen:
  manifesto:
    type: manifesto
    instructions: >-
      Which category best describes the main political position or goal expressed in the text?
      The category descriptions come from the Manifesto Project coding scheme, written for party
      manifestos. Read 'the manifesto country' as the country the text is about and 'the manifesto
      party' as the author of the text.
    domains: ["1", "2", "3", "4", "5", "6", "7"]
    kennzahlen: [rile, planeco, markeco, welfare, intpeace]

  konkretheit:
    type: score
    skala: [1, 5]
    instructions: >-
      Wie konkret sind die politischen Forderungen und Vorhaben des Textes? Bewerte nicht das
      Thema und nicht die Position, sondern den Grad der Konkretisierung.
    criteria:
      - Reine Absichtserklärungen und Werte, keine benennbaren Maßnahmen
      - Allgemeine Ziele, Maßnahmen nur angedeutet
      - Benannte Maßnahmen ohne Zahlen, Fristen oder Zuständigkeiten
      - Maßnahmen mit einzelnen Zahlen oder Fristen
      - Maßnahmen mit Zahlen, Fristen, Zuständigkeiten und Finanzierung

  tonalitaet:
    type: score
    skala: [0, 1]
    instructions: >-
      Wie polarisierend ist die Sprache des Textes? Bewerte den Ton, nicht die Position.
    criteria:
      - Sachlich und abwägend, Gegenpositionen werden fair dargestellt
      - Überwiegend sachlich, vereinzelt wertende Zuspitzung
      - Deutlich wertend, Gegenpositionen werden abgewertet
      - Kampfrhetorik, Feindbilder und Übertreibung prägen den Text

  textsorte:
    type: choice
    instructions: Um welche Textsorte handelt es sich?
    criteria:
      Wahlprogramm: Programm einer Partei oder Liste zu einer Wahl, mit Forderungen über mehrere Politikfelder
      Koalitionsvertrag: Vereinbarung mehrerer Parteien über ein gemeinsames Regierungsprogramm
      Rede: Manuskript oder Mitschrift einer Rede oder Ansprache
      Pressemitteilung: Kurze Mitteilung an Medien zu einem Anlass oder einer Position
      Sonstiges: Keine der genannten Textsorten

  regionalbezug:
    type: noul
    instructions: Bezieht sich der Text erkennbar auf ein bestimmtes Bundesland, eine Region oder eine Kommune?

  finanzierung:
    type: noul
    instructions: Nennt der Text konkrete Angaben dazu, wie seine Vorhaben finanziert werden sollen?
```

`text_typ` wird als `state.text_type` mitgeschickt, der Text als `state.text`.

## 7. UI

### 7.1 Passwort-Gate

Erster Screen: ein Passwortfeld. Vergleich mit `APP_PASSWORD` per `hmac.compare_digest`. Erfolg
landet in `st.session_state["authed"]`. Fehlt `APP_PASSWORD` oder `OPENROUTER_API_KEY` in der
Umgebung, zeigt die App nur eine Fehlerseite mit dem Namen der fehlenden Variable.

### 7.2 Seitenleiste: Config-Editor

- Kopf: Modell (nur Anzeige), `text_typ` (Textfeld).
- Je Frage ein `st.expander` mit Titel `name (type)`. Inhalt:
  - Aktiv-Schalter.
  - Typ-Auswahl (noul, choice, score). Typwechsel setzt Startwerte: score → `skala` [1, 5] und drei
    Stufen "Stufe 1" bis "Stufe 3"; choice → zwei Optionen "Option A", "Option B" ohne Beschreibung;
    noul → keine Kriterien.
  - Instruction als Textfeld.
  - score: Textfeld mit einer Stufe pro Zeile, dazu Skala min und max.
  - choice: `st.data_editor` mit zwei Spalten Option und Beschreibung, Zeilen hinzufügen und löschen.
  - noul: nichts weiter.
  - Löschen-Button.
- Manifesto-Block: Aktiv-Schalter, Instruction, Domänen-Mehrfachauswahl (Code und Name), Kennzahlen-
  Mehrfachauswahl. Kein Typwechsel, kein Katalog-Editing. Hinweis auf die Zahl der Kategorien.
- Unten: "Frage hinzufügen" (Name und Typ), "Zurücksetzen auf config.yaml", "Config als YAML herunterladen".
- Validierungsfehler als Liste unter dem Editor. Solange Fehler bestehen, ist "Bewerten" gesperrt.
- Die Datei `config.yaml` wird nie beschrieben.

### 7.3 Hauptbereich

1. Upload-Zone: `st.file_uploader`, nur `.pdf`, 30 MB (Streamlit-Config `server.maxUploadSize = 30`).
2. Textinfo: Seiten, Zeichen, Token geschätzt, Chunk-Zahl beim aktuellen Slider-Wert, aufklappbare
   Textvorschau (erste 3.000 Zeichen). Warnung bei `KeinText`, Fehler bei `PdfFehler`.
3. Steuerung: Modus-Radio (Gesamttext, Chunks, Beide), Slider Chunk-Größe 300..3000 Token in 100er-
   Schritten, Vorschau der Schätzung (Aufrufe, Token, Kosten in USD, Dauer), Button "Bewerten".
   Im Gesamttext-Modus bei Überlänge vorab die Warnung "Es werden nur X % des Textes bewertet."
4. Während des Laufs: `st.progress` mit "n von m Aufrufen". Danach: Fehlerliste, falls vorhanden.
5. Ergebnisse, bei "Beide" zwei Spalten. Reihenfolge = Config-Reihenfolge:
   - Manifesto: horizontale Balken der Top-10-Kategorien in Prozent; Domänen-Balken; Kennzahlen als
     Kacheln mit Wert; rile als divergierender Balken -100..+100, die anderen 0..100.
   - noul: Farbfeld (Farbe nach Wert), Wert mit zwei Nachkommastellen, Instruction als Beschriftung.
   - choice: Farbfeld in der Optionsfarbe mit gewählter Option und Confidence; darunter Balken der Top-5.
   - score: Balken je Leiterstufe mit Stufentext als Achsenbeschriftung; Überschrift mit Erwartungswert
     auf der Skala und Confidence.
   - Im Chunk-Modus zusätzlich Expander "Je Chunk": Tabelle mit Index, Seiten, Token, Top-Kategorie,
     alle noul-Werte, alle Score-Werte, Choice-Wahl; Fehlerspalte.
6. Metazeile über den Ergebnissen: Modell, Modus, Einheiten, bewerteter Anteil, Aufrufe, Input-Token,
   Kosten, Sekunden.
7. Download: "Ergebnis als JSON" und "Extrahierter Text als TXT" über `st.download_button`.

Session-State hält: Config, Datei-Hash, Seiten, letztes Ergebnis. Ein neuer Upload verwirft das Ergebnis.

## 8. Fehlerbehandlung

| Situation | Verhalten |
| --- | --- |
| PDF nicht lesbar | Fehlermeldung, kein Lauf. |
| PDF ohne Textebene | Warnung "Scan ohne Textebene, OCR wird nicht unterstützt", kein Lauf. |
| Fehlender Key oder Passwort | Fehlerseite beim Start. |
| Ungültige Config | Fehlerliste im Editor, Start gesperrt. |
| HTTP 429, 5xx, 529 | Retry mit Backoff, maximal 4 Wiederholungen, dann Fehler der Einheit. |
| `max_tokens_exceeded`, Gesamttext | Text um 15 % kürzen, erneut senden, maximal 3-mal; Anteil nachführen. |
| `max_tokens_exceeded`, Chunk | Fehler der Einheit (sollte bei `chunk_tokens` ≤ 3000 nie eintreten). |
| Sonstiger API-Fehler | Fehler der Einheit; Lauf läuft weiter; Aggregat nur aus erfolgreichen Einheiten; Zahl der Ausfälle in der Metazeile. |
| Alle Einheiten fehlgeschlagen | Fehlermeldung mit erster Ursache, kein Ergebnisblock. |

## 9. Sicherheit

- Passwort-Gate vor allem anderen; kein Weg zum Upload ohne Session-Flag.
- API-Key nur serverseitig, nie im Ergebnis-JSON, nie in Logs.
- Upload nur PDF, 30 MB Limit; Extraktion in Bytes im Speicher, nichts wird auf Platte geschrieben.
- Streamlit-Telemetrie aus (`browser.gatherUsageStats = false`), headless.
- Container läuft als Non-Root, kein Host-Port, erreichbar nur über das Docker-Netz von Caddy.

## 10. Tests

pytest, ohne Netz, TDD je Modul (Test zuerst). Verzeichnis `tests/`.

- `test_config.py`: Default lädt und ist gültig; score ohne `criteria` fällt durch; choice mit Liste
  fällt durch; noul mit `criteria` fällt durch; doppelter Manifesto-Block fällt durch; ungültiger Name
  fällt durch; `to_yaml` → `load` ist eine Identität; `to_questions` lässt inaktive Fragen weg.
- `test_manifesto.py`: genau 57 Codes inklusive `000`; keine `.`-Codes mehr; jeder Code aus den
  Kennzahl-Formeln existiert im Katalog; `label`/`code_of` Hin- und Rückweg; `build_question` mit
  Domänenfilter enthält `000` immer; Kennzahlen auf synthetischen Anteilen (z. B. nur 104 = 100 → rile 100).
- `test_pdf_text.py`: PDF zur Laufzeit mit PyMuPDF erzeugen (zwei Seiten, ein getrenntes Wort
  "Wirt-\nschaft"), Extraktion liefert zwei Seiten und "Wirtschaft"; leeres PDF wirft `KeinText`;
  Müll-Bytes werfen `PdfFehler`.
- `test_chunking.py`: `estimate_tokens`; Packen bis Zielgröße; überlanger Absatz an Satzgrenzen
  geteilt; Seitenbezug; Mini-Restchunk wird angehängt; `whole_text` kürzt an Satzgrenze und liefert
  den Anteil; `shrink` kürzt um den Faktor.
- `test_jev_client.py` (urlopen gemockt): Body-Form; Header; Retry bei 429 dann Erfolg; `ZuLang` bei
  400 mit `max_tokens_exceeded`; `JevFehler` bei 400 ohne; `cost_usd` nimmt `usage.cost` vor der Rechnung.
- `test_scoring.py`: `pack_questions` hält das Budget und trennt den großen Block; `text_budget`;
  `run` mit Fake-Client zählt Aufrufe und sammelt Fehler; `ZuLang`-Fallback kürzt und wiederholt;
  Aggregation für noul, choice, score mit Handrechnung bei zwei Einheiten unterschiedlicher Länge;
  fehlgeschlagene Einheit fließt nicht ins Mittel, `n` stimmt.
- `test_results.py`: JSON enthält Meta, Config und beide Läufe; `to_json` ist UTF-8 mit Umlauten.
- `test_live.py`: markiert `@pytest.mark.live`, übersprungen ohne `OPENROUTER_API_KEY`; ein Aufruf
  mit drei Fragetypen gegen die echte API, prüft nur die Antwortform.

UI wird nicht automatisiert getestet; Abnahme per Browser (rodney-Skill) auf einem Beispiel-PDF.

## 11. Deployment

### 11.1 Container

- `pyproject.toml` mit uv, `uv.lock` eingecheckt.
- Dockerfile: `python:3.12-slim`, uv aus dem offiziellen Image kopiert, `uv sync --frozen --no-dev`,
  Non-Root-User, `EXPOSE 8501`, Start:
  `streamlit run app.py --server.port 8501 --server.baseUrlPath jev_grading_demo --server.headless true`.
- `.streamlit/config.toml`: `server.maxUploadSize = 30`, `browser.gatherUsageStats = false`.
- `compose.yaml`: Service `jev_grading_demo`, `env_file: .env`, Netz `weihnachtswunder-gps-tracker_default`
  (external), `restart: unless-stopped`, kein `ports`, Healthcheck per Python-Einzeiler gegen
  `http://localhost:8501/jev_grading_demo/_stcore/health`.
- `.env.example` mit `OPENROUTER_API_KEY=` und `APP_PASSWORD=`.

### 11.2 Server (Weihnachtswunderserver, 34.159.146.213)

Reihenfolge, jeder sudo-Block einzeln freigegeben:

1. Projekt per rsync nach `/home/jeggers/projects/jev_grading_demo/` (ohne `.env`; `.env` wird auf
   dem Server angelegt).
2. `sudo docker compose build` und `sudo docker compose up -d`; Healthcheck abwarten.
3. Erst wenn der Container gesund ist: Caddy-Route. Backup der produktiven Caddyfile in
   `/home/wdr-docker-ssh/projects/weihnachtswunder-gps-tracker/deploy/Caddyfile`, dann vor dem
   Catch-all einfügen:
   ```
   @jev path /jev_grading_demo /jev_grading_demo/*
   handle @jev {
       reverse_proxy jev_grading_demo:8501
   }
   ```
   `caddy validate`, dann `caddy reload` im Caddy-Container. Kein Pfad-Strip: Streamlit erwartet
   den vollen Pfad wegen `baseUrlPath`.
4. Browser-Test unter `https://woistderbus.interaktive-projekte.de/jev_grading_demo/`, inklusive WebSocket
   (die Seite muss interaktiv bleiben, nicht nur laden).
5. Eintrag in `/var/opt/README.md` (Projekt, Pfad, Port, Route, Ansprechpartner).

Lokal: `git init` ist erfolgt, `.env` ist ignoriert. Kein Remote nötig; Deployment per rsync.

## 12. Außerhalb des Umfangs

- OCR für gescannte PDFs.
- Mehrere Dateien gleichzeitig, Vergleich zweier Dokumente.
- Persistente Speicherung von Läufen auf dem Server.
- Nutzerverwaltung über das gemeinsame Passwort hinaus, Rate-Limits.
- Andere Modelle als Jev.
- Bearbeitung des Manifesto-Katalogs im UI.

## 13. Risiken und Unsicherheiten

- Der OpenRouter-Pfad heißt `alpha`; er kann sich ändern. Endpunkt ist eine Konstante im Client
  und per `JEV_ENDPOINT` in der Umgebung überschreibbar.
- Token-Schätzung ist eine Heuristik; bei Texten mit vielen Zahlen oder Fremdsprachen kann sie
  um 20 bis 30 % danebenliegen. Der `ZuLang`-Fallback fängt das ab, kostet aber einen weiteren Aufruf.
- Streamlit hinter dem Caddy-Subpath ist ein dokumentiertes Muster, hier aber noch nicht erprobt.
  Schätzung: 85 % läuft ohne Sonderbehandlung; Rest wären Header-Anpassungen für WebSockets.
- Der Manifesto-Block kostet je Aufruf etwa 6.600 Token an Beschreibungen (gemessen an der
  JSON-Länge der 57 kollabierten Kategorien, Heuristik 3,5 Zeichen je Token). Bei 100 Chunks sind das
  rund 1 Mio. Token, also etwa 0,04 USD und 15 bis 25 Sekunden mit 6 Workern. Akzeptabel für eine
  Demo, aber der Slider geht deshalb nicht unter 300 Token.
- Score-Aggregation als Mittel der Verteilungen ist mathematisch identisch mit dem Mittel der
  Erwartungswerte (bei gleichen Gewichten), Confidence-Mittel ist dagegen nur eine Näherung.
