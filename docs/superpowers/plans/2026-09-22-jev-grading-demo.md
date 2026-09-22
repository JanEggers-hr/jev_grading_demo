# jev_grading_demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eine passwortgeschützte Streamlit-Demo, die ein hochgeladenes PDF mit Jev (über OpenRouter) nach konfigurierbaren Fragen bewertet, im Gesamttext- und im Chunk-Modus, mit Farbfeldern, Balken und JSON-Download, deployt als Container hinter Caddy.

**Architecture:** Ein Streamlit-Prozess. Alle Logik liegt im Paket `jevdemo/` ohne Streamlit-Import (Config, Manifesto-Katalog, PDF-Text, Chunking, Jev-Client, Scoring, Ergebnis) und ist mit pytest ohne Netz getestet. `app.py` und `jevdemo/ui/` verdrahten und zeichnen nur. Jeder Lauf: PDF → Seiten → Einheiten → Fragen in Token-Gruppen gepackt → parallele Jev-Aufrufe → token-gewichtete Aggregation → Ergebnisobjekt.

**Tech Stack:** Python 3.12, uv, Streamlit ≥ 1.57, PyMuPDF ≥ 1.25, PyYAML, Plotly, pandas, pytest. OpenRouter `POST /api/alpha/decisions`, Modell `typesafe/jev-1.13`. Docker (python:3.12-slim), compose, Caddy-Subpath.

**Spec:** `docs/superpowers/specs/2026-09-22-jev-grading-demo-design.md`

## Global Constraints

- Python `>=3.12`; Paketverwaltung uv; `uv.lock` eingecheckt.
- Abhängigkeiten nur: `streamlit>=1.57`, `pymupdf>=1.25`, `pyyaml>=6.0`, `plotly>=5.24`, `pandas>=2.2`; dev: `pytest>=8.3`.
- `jevdemo/` importiert nirgends `streamlit`; nur `app.py` und `jevdemo/ui/` dürfen das.
- Jev-Client nur mit `urllib` (Standardbibliothek), Endpunkt `https://openrouter.ai/api/alpha/decisions`, überschreibbar per `JEV_ENDPOINT`.
- Token-Schätzung: `ceil(len(text) / 3.5)`. Kein tiktoken.
- Budget je Aufruf `budget_tokens` (Default 26000, erlaubt 1000..28000), Reserve 200 Token; `chunk_tokens` Default 800, erlaubt 300..3000.
- Retry bei HTTP 429, 500, 502, 503, 529 mit Backoff `2**versuch` s, maximal 4 Wiederholungen. `max_tokens_exceeded` → `ZuLang`; im Gesamttext-Modus um 15 % kürzen, maximal 3-mal.
- Aggregation token-gewichtet (Gewicht = `einheit.tokens`), nur über Einheiten mit Antwort.
- Kennzahl-Formeln exakt wie in Spec 5.2 (Codebook MPDS2026a, Abschnitt 3.6).
- Umgebungsvariablen: `OPENROUTER_API_KEY`, `APP_PASSWORD`; `.env` ist gitignored, `.env.example` eingecheckt.
- Bezeichner, Docstrings, Commit-Messages und UI-Texte auf Deutsch (wie das Referenzprojekt); Jev-Instructions für den Manifesto-Block auf Englisch (Katalogsprache).
- Farben: dataviz-Referenzpalette (Light): kategorial `#2a78d6 #eb6834 #1baf7a #eda100 #e87ba4 #008300 #4a3aa7 #e34948`; divergierend rot `#e34948` ↔ blau `#2a78d6` mit Mitte `#f0efec`; sequenziell blau `#2a78d6`; Text `#0b0b0b` / `#ffffff`.
- Commits klein und häufig, Attribution-Zeile `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` am Ende jeder Commit-Message. Git-Identität ist lokal nicht gesetzt: jeden Commit mit `git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit ...` ausführen.
- Jeder sudo-Block auf dem Server braucht vorher explizite Freigabe von Jan (CLAUDE.md).

---

## Dateistruktur

| Datei | Verantwortung |
| --- | --- |
| `pyproject.toml`, `uv.lock` | Projekt, Abhängigkeiten, pytest-Konfiguration |
| `config.yaml` | Default-Fragen (Spec 6) |
| `jevdemo/env.py` | `.env` in `os.environ` laden (nur fehlende Schlüssel) |
| `jevdemo/manifesto.py` | Katalog laden und zusammenklappen, Choice-Frage, Anteile, Domänen, Top, Kennzahlen |
| `jevdemo/config.py` | Datenklassen `Frage`, `Config`; `load`, `loads`, `from_dict`, `to_dict`, `to_yaml`, `validate`, `aktive`, `to_questions` |
| `jevdemo/pdf_text.py` | `Seite`, `extract_pages`, Fehler `PdfFehler`, `KeinText` |
| `jevdemo/chunking.py` | `Einheit`, `estimate_tokens`, `chunk_pages`, `whole_text`, `shrink` |
| `jevdemo/jev_client.py` | `JevClient.decide`, `JevFehler`, `ZuLang`, `cost_usd` |
| `jevdemo/scoring.py` | `question_tokens`, `pack_questions`, `text_budget`, `schaetzung`, `run`, `aggregate`, `Lauf`, `EinheitErgebnis` |
| `jevdemo/results.py` | `meta`, `build`, `to_json` |
| `jevdemo/ui/views.py` | Farb-Helfer, Kacheln, Plotly-Balken, Chunk-Tabelle, Metazeile |
| `jevdemo/ui/editor.py` | Formular pro Frage in der Seitenleiste |
| `app.py` | Gate, Upload, Steuerung, Lauf, Download |
| `tests/…` | ein Testmodul je Modul |
| `.streamlit/config.toml`, `Dockerfile`, `compose.yaml`, `.env.example`, `README.md` | Betrieb |

---

### Task 1: Projektgerüst

**Files:**
- Create: `pyproject.toml`, `jevdemo/__init__.py`, `jevdemo/ui/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `.streamlit/config.toml`, `.env.example`
- Test: `tests/test_geruest.py`

**Interfaces:**
- Produces: importierbares Paket `jevdemo`, `uv run pytest` läuft, Marker `live` ist registriert und standardmäßig abgewählt.

- [ ] **Step 1: pyproject.toml schreiben**

```toml
[project]
name = "jev-grading-demo"
version = "0.1.0"
description = "Demo: PDF hochladen, Text mit Jev (TypeSafe System One) bewerten"
requires-python = ">=3.12"
dependencies = [
    "streamlit>=1.57",
    "pymupdf>=1.25",
    "pyyaml>=6.0",
    "plotly>=5.24",
    "pandas>=2.2",
]

[dependency-groups]
dev = ["pytest>=8.3"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-m 'not live'"
markers = ["live: ruft die echte OpenRouter-API auf, braucht OPENROUTER_API_KEY"]
```

- [ ] **Step 2: Leere Paketdateien und Streamlit-Config anlegen**

`jevdemo/__init__.py`:
```python
"""Logik der Jev-Grading-Demo. Kein Streamlit-Import in diesem Paket."""
```

`jevdemo/ui/__init__.py`:
```python
"""Streamlit-Darstellung. Nur hier und in app.py wird streamlit importiert."""
```

`tests/__init__.py`: leer.

`tests/conftest.py`:
```python
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT
```

`.streamlit/config.toml`:
```toml
[server]
maxUploadSize = 30
headless = true

[browser]
gatherUsageStats = false
```

`.env.example`:
```
OPENROUTER_API_KEY=
APP_PASSWORD=
```

- [ ] **Step 3: Rauchtest schreiben**

`tests/test_geruest.py`:
```python
import importlib


def test_paket_importierbar():
    assert importlib.import_module("jevdemo").__doc__


def test_manifesto_json_vorhanden(root):
    assert (root / "manifesto" / "mp_v5.json").is_file()
```

- [ ] **Step 4: Abhängigkeiten auflösen und Tests laufen lassen**

Run: `cd /Users/janeggers/Code/WDR/jev_grading_demo && uv sync && uv run pytest -q`
Expected: `2 passed`, Datei `uv.lock` existiert, `.venv/` existiert (ist gitignored).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock jevdemo tests .streamlit .env.example
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Projektgerüst: uv, pytest, Streamlit-Config

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Manifesto-Katalog und Kennzahlen

**Files:**
- Create: `jevdemo/manifesto.py`
- Test: `tests/test_manifesto.py`

**Interfaces:**
- Consumes: `manifesto/mp_v5.json` (77 Einträge; `parent_code` ist `null` bei Hauptkategorien).
- Produces:
  - `Kategorie(code: str, title: str, domain_code: str, domain: str, description: str)` (frozen dataclass)
  - `DOMAENEN: dict[str, str]` (Code "0".."7" → Name), `KENNZAHLEN: dict[str, tuple[list[str], list[str]]]` (Name → (Plus-Codes, Minus-Codes))
  - `load_catalog(path=KATALOG_PFAD) -> list[Kategorie]` (57 Einträge, nach Code sortiert)
  - `label(kat) -> str`, `code_of(label_) -> str`
  - `build_question(instructions: str, domains: list[str], katalog: list[Kategorie]) -> dict`
  - `anteile(probabilities: dict[str, float]) -> dict[str, float]` (Label → Prozent je Code)
  - `domaenen(anteile_: dict[str, float], katalog) -> dict[str, float]`
  - `top(anteile_, katalog, n=10) -> list[tuple[str, str, float]]`
  - `kennzahlen(anteile_, welche: list[str]) -> dict[str, float]`

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_manifesto.py`:
```python
from jevdemo import manifesto as m


def test_katalog_hat_57_hauptkategorien():
    kat = m.load_catalog()
    codes = [k.code for k in kat]
    assert len(codes) == 57
    assert len(set(codes)) == 57
    assert "000" in codes
    assert all("." not in c for c in codes)
    assert codes == sorted(codes)


def test_eltern_beschreibung_verkettet_kinder():
    kat = {k.code: k for k in m.load_catalog()}
    assert kat["601"].title == "National Way of Life: Positive"
    assert kat["601"].domain_code == "6"
    assert "Immigration: Negative" in kat["601"].description
    assert kat["104"].title == "Military: Positive"


def test_kennzahl_codes_existieren_im_katalog():
    codes = {k.code for k in m.load_catalog()}
    for plus, minus in m.KENNZAHLEN.values():
        assert set(plus) <= codes
        assert set(minus) <= codes


def test_label_und_code():
    k = m.Kategorie("104", "Military: Positive", "1", "External Relations", "x")
    assert m.label(k) == "104 Military: Positive"
    assert m.code_of(m.label(k)) == "104"


def test_build_question_filtert_domaenen_und_behaelt_000():
    kat = m.load_catalog()
    q = m.build_question("Which category?", ["1"], kat)
    codes = {m.code_of(lbl) for lbl in q["criteria"]}
    assert q["type"] == "choice"
    assert q["instructions"] == "Which category?"
    assert "000" in codes
    assert "104" in codes
    assert "401" not in codes
    assert q["criteria"]["104 Military: Positive"].startswith("Favourable")


def test_anteile_domaenen_top():
    kat = m.load_catalog()
    ant = m.anteile({"104 Military: Positive": 0.75, "401 Free Market Economy": 0.25})
    assert ant == {"104": 75.0, "401": 25.0}
    dom = m.domaenen(ant, kat)
    assert dom["1"] == 75.0
    assert dom["4"] == 25.0
    assert dom["0"] == 0.0
    assert m.top(ant, kat, n=1) == [("104", "Military: Positive", 75.0)]


def test_kennzahlen_auf_synthetischen_anteilen():
    assert m.kennzahlen({"104": 100.0}, ["rile", "intpeace"]) == {"rile": 100.0, "intpeace": 0.0}
    ant = {"105": 40.0, "504": 10.0, "401": 50.0}
    kz = m.kennzahlen(ant, ["rile", "planeco", "markeco", "welfare", "intpeace"])
    assert kz == {"rile": 0.0, "planeco": 0.0, "markeco": 50.0, "welfare": 10.0, "intpeace": 40.0}
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_manifesto.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'jevdemo.manifesto'`

- [ ] **Step 3: Implementierung**

`jevdemo/manifesto.py`:
```python
"""Manifesto-Katalog (mp_v5.json) als Jev-Choice-Frage, Anteile und Kennzahlen.

Unterkategorien (z. B. 601.1, 601.2) werden auf ihre Eltern (601) zusammengeklappt,
weil die Kennzahl-Formeln des Codebooks nur dreistellige Hauptkategorien kennen.
"""

import json
from dataclasses import dataclass
from pathlib import Path

KATALOG_PFAD = Path(__file__).resolve().parent.parent / "manifesto" / "mp_v5.json"

DOMAENEN = {
    "0": "No category",
    "1": "External Relations",
    "2": "Freedom and Democracy",
    "3": "Political System",
    "4": "Economy",
    "5": "Welfare and Quality of Life",
    "6": "Fabric of Society",
    "7": "Social Groups",
}

# Codebook MPDS2026a, Abschnitt 3.6 "Programmatic dimensions". Alles in Prozent-Anteilen.
RILE_RECHTS = ["104", "201", "203", "305", "401", "402", "407", "414", "505", "601", "603", "605", "606"]
RILE_LINKS = ["103", "105", "106", "107", "202", "403", "404", "406", "412", "413", "504", "506", "701"]
KENNZAHLEN: dict[str, tuple[list[str], list[str]]] = {
    "rile": (RILE_RECHTS, RILE_LINKS),
    "planeco": (["403", "404", "412"], []),
    "markeco": (["401", "414"], []),
    "welfare": (["503", "504"], []),
    "intpeace": (["102", "105", "106"], []),
}


@dataclass(frozen=True)
class Kategorie:
    code: str
    title: str
    domain_code: str
    domain: str
    description: str


def load_catalog(path: Path = KATALOG_PFAD) -> list[Kategorie]:
    """Katalog laden, Unterkategorien auf ihre Eltern zusammenklappen, nach Code sortieren."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    haupt: dict[str, Kategorie] = {}
    kinder: dict[str, list[dict]] = {}
    for row in rows:
        if row["parent_code"]:
            kinder.setdefault(row["parent_code"], []).append(row)
        else:
            haupt[row["code"]] = Kategorie(
                row["code"], row["title"], row["domain_code"], row["domain"], row["description"]
            )
    for parent, rows_ in kinder.items():
        erstes = rows_[0]
        beschreibung = "\n".join(f"{r['title']}: {r['description']}" for r in rows_)
        haupt[parent] = Kategorie(
            parent, erstes["parent_title"], erstes["domain_code"], erstes["domain"], beschreibung
        )
    return sorted(haupt.values(), key=lambda k: k.code)


def label(kat: Kategorie) -> str:
    """Optionsname, den Jev sieht, z. B. '104 Military: Positive'."""
    return f"{kat.code} {kat.title}"


def code_of(label_: str) -> str:
    return label_.split(" ", 1)[0]


def build_question(instructions: str, domains: list[str], katalog: list[Kategorie]) -> dict:
    """Choice-Frage über die Kategorien der gewählten Domänen; '000' ist immer dabei."""
    gewaehlt = [k for k in katalog if k.domain_code in domains or k.code == "000"]
    return {
        "type": "choice",
        "instructions": instructions,
        "criteria": {label(k): k.description for k in gewaehlt},
    }


def anteile(probabilities: dict[str, float]) -> dict[str, float]:
    """Label-Wahrscheinlichkeiten -> Prozent je Code."""
    return {code_of(lbl): round(p * 100, 2) for lbl, p in probabilities.items()}


def domaenen(anteile_: dict[str, float], katalog: list[Kategorie]) -> dict[str, float]:
    domain_of = {k.code: k.domain_code for k in katalog}
    summen = {code: 0.0 for code in DOMAENEN}
    for code, prozent in anteile_.items():
        summen[domain_of.get(code, "0")] += prozent
    return {code: round(v, 2) for code, v in summen.items()}


def top(anteile_: dict[str, float], katalog: list[Kategorie], n: int = 10) -> list[tuple[str, str, float]]:
    title_of = {k.code: k.title for k in katalog}
    geordnet = sorted(anteile_.items(), key=lambda kv: -kv[1])[:n]
    return [(code, title_of.get(code, code), prozent) for code, prozent in geordnet]


def kennzahlen(anteile_: dict[str, float], welche: list[str]) -> dict[str, float]:
    out = {}
    for name in welche:
        plus, minus = KENNZAHLEN[name]
        wert = sum(anteile_.get(c, 0.0) for c in plus) - sum(anteile_.get(c, 0.0) for c in minus)
        out[name] = round(wert, 2)
    return out
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_manifesto.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add jevdemo/manifesto.py tests/test_manifesto.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Manifesto-Katalog: Hauptkategorien, Choice-Frage, Kennzahlen

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Config laden, validieren, übersetzen; Default-config.yaml

**Files:**
- Create: `jevdemo/config.py`, `config.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `manifesto.build_question`, `manifesto.KENNZAHLEN`, `manifesto.Kategorie`.
- Produces:
  - `Frage(name, type, instructions="", aktiv=True, criteria=None, skala=None, domains=None, kennzahlen=None)` (dataclass, veränderlich)
  - `Config(model="typesafe/jev-1.13", text_typ="", chunk_tokens=800, budget_tokens=26000, fragen=[])`
  - `ConfigError(Exception)`
  - `load(path=CONFIG_PFAD) -> Config`, `loads(text) -> Config`, `from_dict(d) -> Config`, `to_dict(config) -> dict`, `to_yaml(config) -> str`
  - `validate(config) -> list[str]` (leer = gültig)
  - `aktive(config) -> list[Frage]`
  - `to_questions(config, katalog) -> dict[str, dict]` (nur aktive Fragen, Jev-Format)
  - `TYPEN = ("noul", "choice", "score", "manifesto")`

- [ ] **Step 1: Default-config.yaml schreiben** (Inhalt exakt aus Spec Abschnitt 6)

`config.yaml`:
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

- [ ] **Step 2: Failing Tests schreiben**

`tests/test_config.py`:
```python
import pytest

from jevdemo import config as cfg
from jevdemo import manifesto


@pytest.fixture(scope="module")
def katalog():
    return manifesto.load_catalog()


def test_default_laedt_und_ist_gueltig():
    config = cfg.load()
    assert cfg.validate(config) == []
    assert config.model == "typesafe/jev-1.13"
    assert config.chunk_tokens == 800
    assert [f.name for f in config.fragen][:2] == ["manifesto", "konkretheit"]
    assert config.fragen[1].skala == [1, 5]
    assert len(config.fragen[1].criteria) == 5


def test_yaml_roundtrip():
    config = cfg.load()
    text = cfg.to_yaml(config)
    assert "Wahlprogramm" in text and "ä" in text
    assert cfg.to_dict(cfg.loads(text)) == cfg.to_dict(config)


def _frage(**kw) -> cfg.Frage:
    basis = dict(name="f", type="noul", instructions="Frage?")
    basis.update(kw)
    return cfg.Frage(**basis)


def _config(*fragen) -> cfg.Config:
    return cfg.Config(text_typ="t", fragen=list(fragen))


def test_score_ohne_criteria_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="score", skala=[1, 5])))
    assert any("score braucht criteria" in f for f in fehler)


def test_score_mit_falscher_skala_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="score", criteria=["a", "b"], skala=[5, 1])))
    assert any("skala" in f for f in fehler)


def test_choice_mit_liste_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="choice", criteria=["a", "b"])))
    assert any("choice braucht criteria als Mapping" in f for f in fehler)


def test_noul_mit_criteria_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="noul", criteria=["a"])))
    assert any("noul hat weder" in f for f in fehler)


def test_doppelter_manifesto_block_faellt_durch():
    m = dict(type="manifesto", domains=["1"], kennzahlen=["rile"])
    fehler = cfg.validate(_config(_frage(name="a", **m), _frage(name="b", **m)))
    assert any("höchstens eine Frage vom Typ manifesto" in f for f in fehler)


def test_ungueltiger_name_und_doppelter_name():
    fehler = cfg.validate(_config(_frage(name="Böse Frage"), _frage(name="x"), _frage(name="x")))
    assert any("Name darf nur" in f for f in fehler)
    assert any("doppelt" in f for f in fehler)


def test_unbekannter_typ_und_leere_instruction():
    fehler = cfg.validate(_config(_frage(type="essay"), _frage(name="g", instructions="  ")))
    assert any("unbekannter Typ" in f for f in fehler)
    assert any("instructions fehlt" in f for f in fehler)


def test_grenzen_fuer_tokens():
    config = _config(_frage())
    config.chunk_tokens = 100
    config.budget_tokens = 50000
    fehler = cfg.validate(config)
    assert any("chunk_tokens" in f for f in fehler)
    assert any("budget_tokens" in f for f in fehler)


def test_to_questions_laesst_inaktive_weg_und_baut_manifesto(katalog):
    config = _config(
        _frage(name="ja", type="noul"),
        _frage(name="aus", type="noul", aktiv=False),
        _frage(name="stufe", type="score", criteria=["a", "b"], skala=[0, 1]),
        _frage(name="wahl", type="choice", criteria={"A": "a", "B": "b"}),
        _frage(name="manifesto", type="manifesto", domains=["1"], kennzahlen=["rile"]),
    )
    fragen = cfg.to_questions(config, katalog)
    assert list(fragen) == ["ja", "stufe", "wahl", "manifesto"]
    assert fragen["ja"] == {"type": "noul", "instructions": "Frage?"}
    assert fragen["stufe"] == {"type": "score", "instructions": "Frage?", "criteria": ["a", "b"]}
    assert fragen["wahl"]["criteria"] == {"A": "a", "B": "b"}
    assert fragen["manifesto"]["type"] == "choice"
    assert "000 No meaningful category applies" in fragen["manifesto"]["criteria"]


def test_from_dict_ohne_fragen_wirft():
    with pytest.raises(cfg.ConfigError):
        cfg.from_dict({"model": "x"})
    with pytest.raises(cfg.ConfigError):
        cfg.loads("fragen:\n  a: [1, 2]\n")
```

- [ ] **Step 3: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_config.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'jevdemo.config'`

- [ ] **Step 4: Implementierung**

`jevdemo/config.py`:
```python
"""config.yaml: laden, validieren, serialisieren, in Jev-Fragen übersetzen.

Vier Fragetypen: die drei Jev-Typen (noul, choice, score) und der Sondertyp
manifesto, der seinen Katalog aus manifesto/mp_v5.json zieht.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from jevdemo import manifesto

CONFIG_PFAD = Path(__file__).resolve().parent.parent / "config.yaml"
TYPEN = ("noul", "choice", "score", "manifesto")
SLUG = re.compile(r"^[a-z0-9_]+$")
FELDER = {"type", "instructions", "aktiv", "criteria", "skala", "domains", "kennzahlen"}


class ConfigError(Exception):
    """Strukturfehler beim Laden; Inhaltsfehler meldet validate()."""


@dataclass
class Frage:
    name: str
    type: str
    instructions: str = ""
    aktiv: bool = True
    criteria: list[str] | dict[str, str] | None = None
    skala: list[float] | None = None
    domains: list[str] | None = None
    kennzahlen: list[str] | None = None


@dataclass
class Config:
    model: str = "typesafe/jev-1.13"
    text_typ: str = ""
    chunk_tokens: int = 800
    budget_tokens: int = 26000
    fragen: list[Frage] = field(default_factory=list)


def from_dict(d: dict) -> Config:
    if not isinstance(d, dict) or not isinstance(d.get("fragen"), dict):
        raise ConfigError("config braucht einen Abschnitt 'fragen' (Mapping Name -> Frage)")
    fragen = []
    for name, body in d["fragen"].items():
        if not isinstance(body, dict):
            raise ConfigError(f"Frage '{name}' muss ein Mapping sein")
        unbekannt = set(body) - FELDER
        if unbekannt:
            raise ConfigError(f"Frage '{name}': unbekannte Felder {sorted(unbekannt)}")
        fragen.append(
            Frage(
                name=str(name),
                type=str(body.get("type", "")),
                instructions=str(body.get("instructions", "")),
                aktiv=bool(body.get("aktiv", True)),
                criteria=body.get("criteria"),
                skala=body.get("skala"),
                domains=[str(x) for x in body["domains"]] if body.get("domains") is not None else None,
                kennzahlen=body.get("kennzahlen"),
            )
        )
    try:
        return Config(
            model=str(d.get("model", Config.model)),
            text_typ=str(d.get("text_typ", "")),
            chunk_tokens=int(d.get("chunk_tokens", Config.chunk_tokens)),
            budget_tokens=int(d.get("budget_tokens", Config.budget_tokens)),
            fragen=fragen,
        )
    except (TypeError, ValueError) as e:
        raise ConfigError(f"chunk_tokens/budget_tokens müssen ganze Zahlen sein: {e}") from e


def to_dict(config: Config) -> dict:
    fragen = {}
    for f in config.fragen:
        body: dict = {"type": f.type, "instructions": f.instructions, "aktiv": f.aktiv}
        for feld in ("criteria", "skala", "domains", "kennzahlen"):
            if getattr(f, feld) is not None:
                body[feld] = getattr(f, feld)
        fragen[f.name] = body
    return {
        "model": config.model,
        "text_typ": config.text_typ,
        "chunk_tokens": config.chunk_tokens,
        "budget_tokens": config.budget_tokens,
        "fragen": fragen,
    }


def to_yaml(config: Config) -> str:
    return yaml.safe_dump(to_dict(config), allow_unicode=True, sort_keys=False, width=100)


def loads(text: str) -> Config:
    try:
        return from_dict(yaml.safe_load(text))
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML-Fehler: {e}") from e


def load(path: Path = CONFIG_PFAD) -> Config:
    return loads(Path(path).read_text(encoding="utf-8"))


def _zahl(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate(config: Config) -> list[str]:
    """Menschenlesbare Fehlerliste; leer bedeutet gültig."""
    fehler: list[str] = []
    if not 300 <= config.chunk_tokens <= 3000:
        fehler.append("chunk_tokens muss zwischen 300 und 3000 liegen")
    if not 1000 <= config.budget_tokens <= 28000:
        fehler.append("budget_tokens muss zwischen 1000 und 28000 liegen")
    if not config.fragen:
        fehler.append("mindestens eine Frage ist nötig")
    namen = [f.name for f in config.fragen]
    for name in sorted(set(namen)):
        if namen.count(name) > 1:
            fehler.append(f"Name '{name}' ist doppelt")
    if sum(f.type == "manifesto" for f in config.fragen) > 1:
        fehler.append("höchstens eine Frage vom Typ manifesto")
    for f in config.fragen:
        p = f"Frage '{f.name}': "
        if not SLUG.match(f.name):
            fehler.append(p + "Name darf nur a-z, 0-9 und _ enthalten")
        if f.type not in TYPEN:
            fehler.append(p + f"unbekannter Typ '{f.type}'")
            continue
        if not f.instructions.strip():
            fehler.append(p + "instructions fehlt")
        if f.type == "score":
            if not (isinstance(f.criteria, list) and len(f.criteria) >= 2
                    and all(isinstance(c, str) and c.strip() for c in f.criteria)):
                fehler.append(p + "score braucht criteria als Liste mit mindestens 2 Stufen")
            if not (isinstance(f.skala, list) and len(f.skala) == 2
                    and all(_zahl(x) for x in f.skala) and f.skala[0] < f.skala[1]):
                fehler.append(p + "score braucht skala [min, max] mit min < max")
        elif f.type == "choice":
            if not (isinstance(f.criteria, dict) and len(f.criteria) >= 2
                    and all(isinstance(k, str) and k.strip() for k in f.criteria)):
                fehler.append(p + "choice braucht criteria als Mapping Option -> Beschreibung mit mindestens 2 Optionen")
            if f.skala is not None:
                fehler.append(p + "choice hat keine skala")
        elif f.type == "noul":
            if f.criteria is not None or f.skala is not None:
                fehler.append(p + "noul hat weder criteria noch skala")
        elif f.type == "manifesto":
            if not f.domains or not set(f.domains) <= set("1234567"):
                fehler.append(p + "domains muss eine nichtleere Teilmenge von 1..7 sein")
            if f.kennzahlen is None or not set(f.kennzahlen) <= set(manifesto.KENNZAHLEN):
                fehler.append(p + f"kennzahlen muss Teilmenge von {sorted(manifesto.KENNZAHLEN)} sein")
    return fehler


def aktive(config: Config) -> list[Frage]:
    return [f for f in config.fragen if f.aktiv]


def to_questions(config: Config, katalog: list[manifesto.Kategorie]) -> dict[str, dict]:
    """Aktive Fragen im Jev-Format, Reihenfolge wie in der Config."""
    out: dict[str, dict] = {}
    for f in aktive(config):
        if f.type == "manifesto":
            out[f.name] = manifesto.build_question(f.instructions, f.domains or [], katalog)
        elif f.type == "noul":
            out[f.name] = {"type": "noul", "instructions": f.instructions}
        else:
            out[f.name] = {"type": f.type, "instructions": f.instructions, "criteria": f.criteria}
    return out
```

- [ ] **Step 5: Tests laufen lassen**

Run: `uv run pytest tests/test_config.py -q`
Expected: `12 passed`

- [ ] **Step 6: Commit**

```bash
git add jevdemo/config.py config.yaml tests/test_config.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Config: Datenklassen, Validierung, Jev-Fragen; Default-config.yaml

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: PDF-Textextraktion

**Files:**
- Create: `jevdemo/pdf_text.py`
- Test: `tests/test_pdf_text.py`

**Interfaces:**
- Consumes: PyMuPDF (`import pymupdf`; `pymupdf.open(stream=bytes, filetype="pdf")`, `page.get_text("blocks")` liefert Tupel `(x0, y0, x1, y1, text, block_no, block_type)`, `block_type == 0` ist Text).
- Produces:
  - `Seite(nummer: int, text: str)` (frozen dataclass; Absätze im Text durch `\n\n` getrennt)
  - `extract_pages(data: bytes) -> list[Seite]`
  - `PdfFehler(Exception)`, `KeinText(Exception)`, `MIN_ZEICHEN = 50`

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_pdf_text.py`:
```python
import pymupdf
import pytest

from jevdemo import pdf_text


def _pdf(*seiten: list[str]) -> bytes:
    """Ein PDF mit je einem Textblock pro Eintrag; Zeilen 130 pt auseinander -> eigene Blöcke."""
    doc = pymupdf.open()
    for bloecke in seiten:
        page = doc.new_page()
        for i, text in enumerate(bloecke):
            page.insert_text((72, 72 + 130 * i), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_zwei_seiten_absaetze_und_silbentrennung():
    data = _pdf(["Die Wirt-\nschaft wächst. Das ist Absatz eins.", "Zweiter Absatz auf Seite eins."],
                ["Seite zwei sagt hallo."])
    seiten = pdf_text.extract_pages(data)
    assert [s.nummer for s in seiten] == [1, 2]
    assert seiten[0].text == "Die Wirtschaft wächst. Das ist Absatz eins.\n\nZweiter Absatz auf Seite eins."
    assert seiten[1].text == "Seite zwei sagt hallo."


def test_bindestrich_vor_grossbuchstabe_bleibt():
    data = _pdf(["Nord-\nRhein bleibt getrennt."])
    assert pdf_text.extract_pages(data)[0].text == "Nord- Rhein bleibt getrennt."


def test_leeres_pdf_wirft_keintext():
    with pytest.raises(pdf_text.KeinText):
        pdf_text.extract_pages(_pdf([]))


def test_muell_wirft_pdffehler():
    with pytest.raises(pdf_text.PdfFehler):
        pdf_text.extract_pages(b"das ist kein pdf")
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_pdf_text.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'jevdemo.pdf_text'`

- [ ] **Step 3: Implementierung**

`jevdemo/pdf_text.py`:
```python
"""PDF-Bytes -> Seitentexte. Nur Textebene, kein OCR."""

import re
from dataclasses import dataclass

import pymupdf

MIN_ZEICHEN = 50

# "Wirt-\nschaft" -> "Wirtschaft", aber nur vor Kleinbuchstaben (sonst "Nord-\nRhein" -> "Nord- Rhein")
_TRENNUNG = re.compile(r"(\w)-\n(?=[a-zäöüß])")
_LEERRAUM = re.compile(r"[ \t\r\f\v]+")


class PdfFehler(Exception):
    """Datei nicht lesbar."""


class KeinText(Exception):
    """Keine Textebene (vermutlich Scan)."""


@dataclass(frozen=True)
class Seite:
    nummer: int
    text: str


def _block_text(roh: str) -> str:
    text = _TRENNUNG.sub(r"\1", roh)
    text = text.replace("\n", " ")
    return _LEERRAUM.sub(" ", text).strip()


def extract_pages(data: bytes) -> list[Seite]:
    """Je Seite die Textblöcke als Absätze (durch Leerzeile getrennt)."""
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # PyMuPDF wirft je nach Version verschiedene Klassen
        raise PdfFehler(f"PDF nicht lesbar: {e}") from e
    seiten: list[Seite] = []
    with doc:
        if doc.needs_pass:
            raise PdfFehler("PDF ist passwortgeschützt")
        for nummer, page in enumerate(doc, start=1):
            bloecke = [b[4] for b in page.get_text("blocks") if b[6] == 0]
            absaetze = [t for t in (_block_text(b) for b in bloecke) if t]
            seiten.append(Seite(nummer, "\n\n".join(absaetze)))
    if sum(len(s.text) for s in seiten) < MIN_ZEICHEN:
        raise KeinText("Das PDF enthält keine Textebene (Scan?). OCR wird nicht unterstützt.")
    return seiten
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_pdf_text.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add jevdemo/pdf_text.py tests/test_pdf_text.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "PDF-Text: Seiten als Absätze, Silbentrennung, Fehlerklassen

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Chunking, Gesamttext-Kürzung, Token-Schätzung

**Files:**
- Create: `jevdemo/chunking.py`
- Test: `tests/test_chunking.py`

**Interfaces:**
- Consumes: `pdf_text.Seite`.
- Produces:
  - `ZEICHEN_JE_TOKEN = 3.5`, `estimate_tokens(text: str) -> int`
  - `Einheit(index: int, text: str, seite_von: int, seite_bis: int, tokens: int)` (frozen dataclass)
  - `chunk_pages(pages: list[Seite], chunk_tokens: int) -> list[Einheit]`
  - `whole_text(pages: list[Seite], max_tokens: int) -> tuple[Einheit, float]` (Einheit, bewerteter Anteil 0..1)
  - `shrink(einheit: Einheit, faktor: float) -> Einheit`

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_chunking.py`:
```python
from jevdemo import chunking
from jevdemo.pdf_text import Seite

SATZ = "Satz eins ist hier. "


def test_estimate_tokens():
    assert chunking.estimate_tokens("") == 0
    assert chunking.estimate_tokens("a" * 35) == 10
    assert chunking.estimate_tokens("a" * 36) == 11


def test_packt_absaetze_bis_zielgroesse_mit_seitenbezug():
    pages = [Seite(1, "A" * 350 + "\n\n" + "B" * 350), Seite(2, "C" * 350)]
    chunks = chunking.chunk_pages(pages, chunk_tokens=200)
    assert len(chunks) == 2
    assert chunks[0].text == "A" * 350 + "\n\n" + "B" * 350
    assert (chunks[0].seite_von, chunks[0].seite_bis) == (1, 1)
    assert chunks[0].tokens == 201
    assert chunks[1].text == "C" * 350
    assert (chunks[1].seite_von, chunks[1].seite_bis) == (2, 2)
    assert [c.index for c in chunks] == [0, 1]


def test_mini_rest_wird_angehaengt():
    pages = [Seite(1, "A" * 700), Seite(2, "B" * 70)]
    chunks = chunking.chunk_pages(pages, chunk_tokens=200)
    assert len(chunks) == 1
    assert chunks[0].text == "A" * 700 + "\n\n" + "B" * 70
    assert (chunks[0].seite_von, chunks[0].seite_bis) == (1, 2)


def test_ueberlanger_absatz_wird_an_satzgrenzen_geteilt():
    pages = [Seite(1, (SATZ * 40).strip())]
    chunks = chunking.chunk_pages(pages, chunk_tokens=100)
    assert len(chunks) == 3
    assert all(c.tokens <= 100 for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)
    assert sum(c.text.count(".") for c in chunks) == 40


def test_whole_text_unter_limit():
    pages = [Seite(1, "A" * 350 + "\n\n" + "B" * 350), Seite(2, "C" * 350)]
    einheit, anteil = chunking.whole_text(pages, max_tokens=1000)
    assert einheit.text == "A" * 350 + "\n\n" + "B" * 350 + "\n\n" + "C" * 350
    assert anteil == 1.0
    assert (einheit.seite_von, einheit.seite_bis) == (1, 2)
    assert einheit.tokens == chunking.estimate_tokens(einheit.text)


def test_whole_text_kuerzt_an_satzgrenze():
    pages = [Seite(1, (SATZ * 40).strip())]
    einheit, anteil = chunking.whole_text(pages, max_tokens=50)
    assert einheit.text.endswith(".")
    assert einheit.tokens <= 50
    assert 0.15 < anteil < 0.25
    assert einheit.seite_bis == 1


def test_shrink_kuerzt_um_faktor_an_satzgrenze():
    text = (SATZ * 40).strip()
    einheit = chunking.Einheit(0, text, 1, 1, chunking.estimate_tokens(text))
    kleiner = chunking.shrink(einheit, 0.15)
    assert kleiner.text.endswith(".")
    assert 0.75 * len(text) < len(kleiner.text) < 0.86 * len(text)
    assert kleiner.tokens == chunking.estimate_tokens(kleiner.text)
    assert (kleiner.index, kleiner.seite_von, kleiner.seite_bis) == (0, 1, 1)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_chunking.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'jevdemo.chunking'`

- [ ] **Step 3: Implementierung**

`jevdemo/chunking.py`:
```python
"""Seiten -> Einheiten: Chunks fester Zielgröße oder ein (ggf. gekürzter) Gesamttext.

Token werden geschätzt (Zeichen / 3,5, kalibriert an Jev: 25.291 Zeichen deutscher
Text = 7.107 Token). Jevs Tokenizer ist unbekannt; die API meldet Überlänge sauber,
und scoring.run kürzt dann nach.
"""

import math
import re
from dataclasses import dataclass

from jevdemo.pdf_text import Seite

ZEICHEN_JE_TOKEN = 3.5
MINI_REST = 0.25  # letzter Chunk unter diesem Anteil der Zielgröße wird angehängt
_SATZENDE = re.compile(r"(?<=[.!?])\s+")
_SATZ_SCHLUSS = re.compile(r"[.!?](?=\s)")


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / ZEICHEN_JE_TOKEN)


@dataclass(frozen=True)
class Einheit:
    index: int
    text: str
    seite_von: int
    seite_bis: int
    tokens: int


def _absaetze(pages: list[Seite]) -> list[tuple[str, int]]:
    """(Absatz, Seitennummer) in Lesereihenfolge."""
    out = []
    for seite in pages:
        for absatz in seite.text.split("\n\n"):
            absatz = absatz.strip()
            if absatz:
                out.append((absatz, seite.nummer))
    return out


def _stuecke(absatz: str, chunk_tokens: int) -> list[str]:
    """Absatz, falls zu lang, in Satzgruppen bis chunk_tokens."""
    if estimate_tokens(absatz) <= chunk_tokens:
        return [absatz]
    stuecke: list[str] = []
    aktuell = ""
    for satz in (s for s in _SATZENDE.split(absatz) if s):
        kandidat = f"{aktuell} {satz}".strip()
        if aktuell and estimate_tokens(kandidat) > chunk_tokens:
            stuecke.append(aktuell)
            aktuell = satz
        else:
            aktuell = kandidat
    if aktuell:
        stuecke.append(aktuell)
    return stuecke


def _einheit(index: int, teile: list[tuple[str, int]]) -> Einheit:
    text = "\n\n".join(t for t, _ in teile)
    return Einheit(index, text, teile[0][1], teile[-1][1], estimate_tokens(text))


def chunk_pages(pages: list[Seite], chunk_tokens: int) -> list[Einheit]:
    """Absätze greedy bis chunk_tokens packen; überlange Absätze vorher an Satzgrenzen teilen."""
    teile = [(stueck, nr) for absatz, nr in _absaetze(pages) for stueck in _stuecke(absatz, chunk_tokens)]
    gruppen: list[list[tuple[str, int]]] = []
    aktuell: list[tuple[str, int]] = []
    laenge = 0
    for text, nr in teile:
        tokens = estimate_tokens(text)
        if aktuell and laenge + tokens > chunk_tokens:
            gruppen.append(aktuell)
            aktuell, laenge = [], 0
        aktuell.append((text, nr))
        laenge += tokens
    if aktuell:
        gruppen.append(aktuell)
    if len(gruppen) >= 2 and sum(estimate_tokens(t) for t, _ in gruppen[-1]) < MINI_REST * chunk_tokens:
        gruppen[-2].extend(gruppen.pop())
    return [_einheit(i, g) for i, g in enumerate(gruppen)]


def _an_satzgrenze(text: str, grenze: int) -> str:
    """text[:grenze], zurückgezogen auf das letzte Satzende, sofern das nicht die Hälfte kostet."""
    kopf = text[:grenze]
    treffer = list(_SATZ_SCHLUSS.finditer(kopf))
    if treffer and treffer[-1].end() > grenze * 0.5:
        return kopf[: treffer[-1].end()].strip()
    return kopf.strip()


def _seite_bei(pages: list[Seite], position: int) -> int:
    lauf = 0
    for seite in pages:
        if not seite.text.strip():
            continue
        lauf += len(seite.text) + 2  # "\n\n" zwischen den Seiten
        if lauf >= position:
            return seite.nummer
    return pages[-1].nummer


def whole_text(pages: list[Seite], max_tokens: int) -> tuple[Einheit, float]:
    """Ganzer Text als eine Einheit; bei Überlänge an Satzgrenze gekürzt. Zweiter Wert: bewerteter Anteil."""
    text = "\n\n".join(s.text for s in pages if s.text.strip())
    if estimate_tokens(text) <= max_tokens:
        return Einheit(0, text, pages[0].nummer, pages[-1].nummer, estimate_tokens(text)), 1.0
    gekuerzt = _an_satzgrenze(text, int(max_tokens * ZEICHEN_JE_TOKEN))
    einheit = Einheit(0, gekuerzt, pages[0].nummer, _seite_bei(pages, len(gekuerzt)), estimate_tokens(gekuerzt))
    return einheit, round(len(gekuerzt) / len(text), 3)


def shrink(einheit: Einheit, faktor: float) -> Einheit:
    """Um `faktor` (0.15 = 15 %) kürzen, an Satzgrenze. Seitenbezug bleibt (grob)."""
    text = _an_satzgrenze(einheit.text, int(len(einheit.text) * (1 - faktor)))
    return Einheit(einheit.index, text, einheit.seite_von, einheit.seite_bis, estimate_tokens(text))
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_chunking.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add jevdemo/chunking.py tests/test_chunking.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Chunking: Absätze packen, Gesamttext kürzen, Token schätzen

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Jev-Client über OpenRouter und .env-Loader

**Files:**
- Create: `jevdemo/env.py`, `jevdemo/jev_client.py`
- Test: `tests/test_env.py`, `tests/test_jev_client.py`

**Interfaces:**
- Produces:
  - `env.lade_env(pfad: Path, umgebung: MutableMapping = os.environ) -> None` (setzt nur fehlende Schlüssel; `export `-Präfix und Anführungszeichen werden entfernt; Zeilen mit `#` am Anfang sind Kommentare)
  - `jev_client.ENDPOINT`, `MODEL = "typesafe/jev-1.13"`, `PREIS_JE_M_INPUT = 0.042`, `RETRY_STATUS`
  - `JevFehler(status: int, detail: str)` mit Attributen `.status`, `.detail`; `ZuLang(JevFehler)`
  - `JevClient(api_key, model=MODEL, endpoint=None, timeout=120, retries=4, schlaf=time.sleep)`; `.decide(state, questions) -> dict` (Schlüssel `answers`, `usage`, `model`, `id`, `provider`, plus `sekunden`)
  - `cost_usd(usage: dict) -> float`

- [ ] **Step 1: Failing Tests für env schreiben**

`tests/test_env.py`:
```python
from jevdemo.env import lade_env


def test_lade_env_setzt_nur_fehlende_schluessel(tmp_path):
    datei = tmp_path / ".env"
    datei.write_text('A=1\nexport B="zwei"\n# Kommentar\nC=drei # kein Kommentar\n\nD=\'vier\'\n', encoding="utf-8")
    umgebung = {"B": "alt"}
    lade_env(datei, umgebung)
    assert umgebung == {"A": "1", "B": "alt", "C": "drei # kein Kommentar", "D": "vier"}


def test_lade_env_ohne_datei_tut_nichts(tmp_path):
    umgebung = {}
    lade_env(tmp_path / "fehlt", umgebung)
    assert umgebung == {}
```

- [ ] **Step 2: Failing Tests für den Client schreiben**

`tests/test_jev_client.py`:
```python
import io
import json
import urllib.error
import urllib.request

import pytest

from jevdemo.jev_client import JevClient, JevFehler, ZuLang, cost_usd

OK = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {"q": {"type": "noul", "noul": 0.8}},
    "usage": {"input_tokens": 284, "output_tokens": 22, "cost": 0.000011928},
    "id": "gen-dec-1", "provider": "TypeSafe",
}


class _Antwort:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "msg", {}, io.BytesIO(body.encode()))


def _folge(monkeypatch, ergebnisse: list):
    """urlopen-Ersatz, der die Ergebnisse der Reihe nach liefert oder wirft; gibt die Requests zurück."""
    aufrufe = []

    def urlopen(request, timeout=None):
        aufrufe.append(request)
        ergebnis = ergebnisse.pop(0)
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return _Antwort(ergebnis)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return aufrufe


def _client(**kw) -> tuple[JevClient, list]:
    schlaf = []
    return JevClient("k", schlaf=schlaf.append, **kw), schlaf


def test_body_header_und_antwort(monkeypatch):
    aufrufe = _folge(monkeypatch, [OK])
    client, _ = _client()
    antwort = client.decide({"text_type": "t", "text": "x"}, {"q": {"type": "noul", "instructions": "?"}})
    req = aufrufe[0]
    assert req.full_url == "https://openrouter.ai/api/alpha/decisions"
    assert json.loads(req.data) == {
        "model": "typesafe/jev-1.13",
        "state": {"text_type": "t", "text": "x"},
        "questions": {"q": {"type": "noul", "instructions": "?"}},
    }
    assert req.get_header("Authorization") == "Bearer k"
    assert req.get_header("Content-type") == "application/json"
    assert antwort["answers"]["q"]["noul"] == 0.8
    assert antwort["sekunden"] >= 0


def test_endpoint_aus_umgebung(monkeypatch):
    monkeypatch.setenv("JEV_ENDPOINT", "https://example.test/dec")
    client, _ = _client()
    assert client.endpoint == "https://example.test/dec"


def test_retry_bei_429_dann_erfolg(monkeypatch):
    aufrufe = _folge(monkeypatch, [_http_error(429, "zu viel"), OK])
    client, schlaf = _client()
    assert client.decide("s", {})["answers"]["q"]["noul"] == 0.8
    assert len(aufrufe) == 2
    assert schlaf == [1]


def test_retry_bei_netzfehler(monkeypatch):
    aufrufe = _folge(monkeypatch, [urllib.error.URLError("dns"), OK])
    client, schlaf = _client()
    client.decide("s", {})
    assert len(aufrufe) == 2 and schlaf == [1]


def test_zu_lang(monkeypatch):
    _folge(monkeypatch, [_http_error(400, '{"error":{"message":"HTTP 400: {\\"detail\\":{\\"error_type\\":\\"max_tokens_exceeded\\"}}"}}')])
    client, schlaf = _client()
    with pytest.raises(ZuLang) as e:
        client.decide("s", {})
    assert e.value.status == 400
    assert schlaf == []


def test_anderer_400_ist_jevfehler(monkeypatch):
    _folge(monkeypatch, [_http_error(400, "kaputt")])
    client, _ = _client()
    with pytest.raises(JevFehler) as e:
        client.decide("s", {})
    assert not isinstance(e.value, ZuLang)
    assert e.value.status == 400 and "kaputt" in str(e.value)


def test_500_erschoepft_wiederholungen(monkeypatch):
    aufrufe = _folge(monkeypatch, [_http_error(500, "a"), _http_error(500, "b")])
    client, schlaf = _client(retries=1)
    with pytest.raises(JevFehler) as e:
        client.decide("s", {})
    assert e.value.status == 500 and len(aufrufe) == 2 and schlaf == [1]


def test_cost_usd():
    assert cost_usd({"cost": 0.5, "input_tokens": 1}) == 0.5
    assert cost_usd({"input_tokens": 1_000_000}) == pytest.approx(0.042)
    assert cost_usd({}) == 0.0
```

- [ ] **Step 3: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_env.py tests/test_jev_client.py -q`
Expected: FAIL mit `ModuleNotFoundError` für `jevdemo.env` und `jevdemo.jev_client`

- [ ] **Step 4: Implementierung**

`jevdemo/env.py`:
```python
"""Schlüssel aus einer .env-Datei in die Umgebung laden, ohne vorhandene zu überschreiben."""

import os
from collections.abc import MutableMapping
from pathlib import Path


def lade_env(pfad: Path, umgebung: MutableMapping[str, str] = os.environ) -> None:
    pfad = Path(pfad)
    if not pfad.is_file():
        return
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip().removeprefix("export ").strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        name, wert = zeile.split("=", 1)
        name, wert = name.strip(), wert.strip()
        if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
            wert = wert[1:-1]
        umgebung.setdefault(name, wert)
```

`jevdemo/jev_client.py`:
```python
"""Jev (TypeSafe System One) über OpenRouter: POST /api/alpha/decisions.

Der Body ist das native TypeSafe-Format {model, state, questions}; die Antwort
ebenfalls, plus usage.cost in USD. chat/completions lehnt Jev ab (geprüft 2026-09-22).
Nur Standardbibliothek, wie im Referenzprojekt.
"""

import json
import os
import time
import urllib.error
import urllib.request

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
PREIS_JE_M_INPUT = 0.042  # USD je 1 Mio. Input-Token; Output kostenlos (Stand 2026-09)
RETRY_STATUS = {429, 500, 502, 503, 529}


class JevFehler(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail[:300]}")
        self.status = status
        self.detail = detail


class ZuLang(JevFehler):
    """HTTP 400 mit max_tokens_exceeded: der State passt nicht ins Kontextfenster."""


class JevClient:
    def __init__(self, api_key: str, model: str = MODEL, endpoint: str | None = None,
                 timeout: int = 120, retries: int = 4, schlaf=time.sleep):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or os.environ.get("JEV_ENDPOINT", ENDPOINT)
        self.timeout = timeout
        self.retries = retries
        self.schlaf = schlaf

    def decide(self, state, questions: dict) -> dict:
        """Ein Aufruf mit allen Fragen -> Antwort-dict (answers, usage, model, ...) plus 'sekunden'."""
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://interaktive-projekte.de/jev_grading_demo/",
            "X-Title": "jev_grading_demo",
        }
        for versuch in range(self.retries + 1):
            request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
            start = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as antwort:
                    daten = json.loads(antwort.read())
                    daten["sekunden"] = round(time.perf_counter() - start, 3)
                    return daten
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")
                if e.code in RETRY_STATUS and versuch < self.retries:
                    self.schlaf(2**versuch)
                    continue
                if e.code == 400 and "max_tokens_exceeded" in detail:
                    raise ZuLang(e.code, detail) from e
                raise JevFehler(e.code, detail) from e
            except (urllib.error.URLError, TimeoutError) as e:
                if versuch < self.retries:
                    self.schlaf(2**versuch)
                    continue
                raise JevFehler(0, str(e)) from e
        raise AssertionError("unreachable")


def cost_usd(usage: dict) -> float:
    if usage.get("cost") is not None:
        return float(usage["cost"])
    return usage.get("input_tokens", 0) / 1e6 * PREIS_JE_M_INPUT
```

- [ ] **Step 5: Tests laufen lassen**

Run: `uv run pytest tests/test_env.py tests/test_jev_client.py -q`
Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add jevdemo/env.py jevdemo/jev_client.py tests/test_env.py tests/test_jev_client.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Jev-Client über OpenRouter decisions-Endpunkt, Retry, ZuLang; .env-Loader

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Scoring, Teil 1: Fragen packen, Aufrufe ausführen

**Files:**
- Create: `jevdemo/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `chunking.Einheit`, `chunking.estimate_tokens`, `chunking.shrink`, `jev_client.JevFehler`, `jev_client.ZuLang`, `jev_client.cost_usd`, `jev_client.PREIS_JE_M_INPUT`, `config.Config`, `config.aktive`, `manifesto.*` (Teil 2).
- Produces:
  - `RESERVE = 200`, `WORKERS = 6`, `KUERZUNG = 0.15`, `MAX_KUERZUNGEN = 3`
  - `question_tokens(question: dict) -> int`
  - `pack_questions(unit_tokens: int, questions: dict[str, dict], budget: int) -> list[dict[str, dict]]`
  - `text_budget(questions: dict[str, dict], budget: int) -> int`
  - `schaetzung(units: list[Einheit], questions, budget) -> dict` mit `aufrufe`, `input_tokens`, `kosten_usd`, `sekunden`
  - `EinheitErgebnis(einheit: Einheit, antworten: dict[str, dict] = {}, fehler: list[str] = [])`
  - `Lauf(modus, einheiten: list[EinheitErgebnis], anteil_bewertet=1.0, aufrufe=0, input_tokens=0, output_tokens=0, kosten_usd=0.0, sekunden=0.0, modell=None, fehler=[])`
  - `run(units, questions, client, *, text_typ: str, budget: int, modus: str, kuerzbar=False, anteil=1.0, workers=WORKERS, progress=None) -> Lauf`; `progress(erledigt: int, gesamt: int)` wird im aufrufenden Thread gerufen.
  - `client` braucht nur `.decide(state, questions) -> dict` (Duck-Typing, damit Tests einen Fake nutzen).

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_scoring.py` (Teil 1; Teil 2 in Task 8 hängt Aggregations-Tests an dieselbe Datei):
```python
import threading

import pytest

from jevdemo import scoring
from jevdemo.chunking import Einheit, estimate_tokens
from jevdemo.jev_client import JevFehler, ZuLang

FRAGEN = {
    "ja": {"type": "noul", "instructions": "?"},
    "stufe": {"type": "score", "instructions": "?", "criteria": ["a", "b", "c"]},
}


def _antwort(q: dict) -> dict:
    if q["type"] == "noul":
        return {"type": "noul", "noul": 0.8}
    if q["type"] == "choice":
        optionen = list(q["criteria"])
        return {"type": "choice", "choice": optionen[0],
                "probabilities": {o: (1.0 if i == 0 else 0.0) for i, o in enumerate(optionen)}, "confidence": 0.9}
    stufen = len(q["criteria"])
    return {"type": "score", "score": 1.0, "legend": {},
            "probabilities": {str(i): (1.0 if i == 1 else 0.0) for i in range(stufen)}, "confidence": 0.9}


class FakeClient:
    """Liefert je Aufruf der Reihe nach: None (Erfolg) oder eine Exception zum Werfen."""

    def __init__(self, folge=None):
        self.folge = list(folge or [])
        self.aufrufe = []
        self.lock = threading.Lock()

    def decide(self, state, questions):
        with self.lock:
            self.aufrufe.append((state, dict(questions)))
            ausnahme = self.folge.pop(0) if self.folge else None
        if ausnahme:
            raise ausnahme
        return {"model": "typesafe/jev-1.13-test",
                "answers": {n: _antwort(q) for n, q in questions.items()},
                "usage": {"input_tokens": 100, "output_tokens": 5, "cost": 0.0000042}}


def _einheiten(*laengen: int) -> list[Einheit]:
    return [Einheit(i, "x" * n, 1, 1, estimate_tokens("x" * n)) for i, n in enumerate(laengen)]


def test_question_tokens():
    assert scoring.question_tokens({"type": "noul", "instructions": "?"}) == 11


def test_pack_questions_haelt_budget():
    gross = {"type": "choice", "instructions": "x" * 20000, "criteria": {"A": "a", "B": "b"}}
    fragen = {"q1": {"type": "noul", "instructions": "?"}, "q2": gross, "q3": {"type": "noul", "instructions": "?"}}
    assert [list(g) for g in scoring.pack_questions(100, fragen, 7000)] == [["q1", "q2", "q3"]]
    assert [list(g) for g in scoring.pack_questions(100, fragen, 6000)] == [["q1"], ["q2"], ["q3"]]
    assert scoring.pack_questions(100, {}, 6000) == []


def test_text_budget_zieht_groesste_frage_ab():
    gross = {"type": "choice", "instructions": "x" * 20000, "criteria": {"A": "a", "B": "b"}}
    fragen = {"klein": {"type": "noul", "instructions": "?"}, "gross": gross}
    budget = scoring.text_budget(fragen, 26000)
    assert budget == 26000 - scoring.question_tokens(gross) - 200
    assert 20000 < budget < 20100


def test_schaetzung():
    fragen_tokens = sum(scoring.question_tokens(q) for q in FRAGEN.values())  # 11 + 20
    s = scoring.schaetzung(_einheiten(350, 700), FRAGEN, 26000)
    assert s["aufrufe"] == 2
    assert s["input_tokens"] == (100 + fragen_tokens) + (200 + fragen_tokens)
    assert s["kosten_usd"] == pytest.approx(s["input_tokens"] / 1e6 * 0.042, abs=1e-5)
    assert s["sekunden"] == 0.3


def test_run_parallel_zaehlt_aufrufe_und_fortschritt():
    client = FakeClient()
    fortschritt = []
    lauf = scoring.run(_einheiten(350, 700, 1050), FRAGEN, client, text_typ="t", budget=26000,
                       modus="chunks", progress=lambda i, n: fortschritt.append((i, n)))
    assert lauf.modus == "chunks"
    assert lauf.aufrufe == 3 and len(client.aufrufe) == 3
    assert lauf.input_tokens == 300 and lauf.output_tokens == 15
    assert lauf.kosten_usd == pytest.approx(3 * 0.0000042)
    assert lauf.modell == "typesafe/jev-1.13-test"
    assert fortschritt == [(1, 3), (2, 3), (3, 3)]
    assert all(set(e.antworten) == {"ja", "stufe"} for e in lauf.einheiten)
    assert lauf.fehler == [] and lauf.anteil_bewertet == 1.0
    assert any(state == {"text_type": "t", "text": "x" * 350} for state, _ in client.aufrufe)
    assert lauf.sekunden >= 0


def test_run_sammelt_fehler_und_laeuft_weiter():
    client = FakeClient([None, JevFehler(500, "kaputt"), None])
    lauf = scoring.run(_einheiten(350, 350, 350), FRAGEN, client, text_typ="", budget=26000,
                       modus="chunks", workers=1)
    assert lauf.aufrufe == 2
    assert len(lauf.fehler) == 1 and "Einheit 1" in lauf.fehler[0] and "kaputt" in lauf.fehler[0]
    assert lauf.einheiten[1].antworten == {} and lauf.einheiten[1].fehler
    assert lauf.einheiten[0].antworten and lauf.einheiten[2].antworten
    assert client.aufrufe[1][0] == "x" * 350  # ohne text_typ geht der Text als String


def test_run_kuerzbar_kuerzt_bei_zulang_und_wiederholt():
    client = FakeClient([ZuLang(400, "max_tokens_exceeded"), None])
    einheit = Einheit(0, "x" * 3500, 1, 1, 1000)
    lauf = scoring.run([einheit], FRAGEN, client, text_typ="t", budget=26000, modus="gesamttext",
                       kuerzbar=True, anteil=0.5)
    assert len(client.aufrufe) == 2
    assert lauf.aufrufe == 1  # nur der erfolgreiche Aufruf wird verbucht
    assert lauf.anteil_bewertet == pytest.approx(0.5 * 0.85)
    assert len(lauf.einheiten[0].einheit.text) == 2975
    assert set(lauf.einheiten[0].antworten) == {"ja", "stufe"}
    assert lauf.fehler == []


def test_run_kuerzbar_gibt_nach_drei_kuerzungen_auf():
    client = FakeClient([ZuLang(400, "m")] * 4)
    lauf = scoring.run(_einheiten(3500), FRAGEN, client, text_typ="t", budget=26000, modus="gesamttext",
                       kuerzbar=True)
    assert len(client.aufrufe) == 4
    assert lauf.einheiten[0].antworten == {}
    assert "zu lang" in lauf.fehler[0]


def test_run_kuerzbar_mit_zwei_gruppen():
    client = FakeClient()
    lauf = scoring.run(_einheiten(350), FRAGEN, client, text_typ="t", budget=320, modus="gesamttext",
                       kuerzbar=True)
    assert len(client.aufrufe) == 2 and lauf.aufrufe == 2
    assert [list(q) for _, q in client.aufrufe] == [["ja"], ["stufe"]]
    assert set(lauf.einheiten[0].antworten) == {"ja", "stufe"}


def test_run_kuerzbar_verlangt_genau_eine_einheit():
    with pytest.raises(ValueError):
        scoring.run(_einheiten(10, 10), FRAGEN, FakeClient(), text_typ="", budget=1000, modus="x", kuerzbar=True)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_scoring.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'jevdemo.scoring'`

- [ ] **Step 3: Implementierung (ohne aggregate, das kommt in Task 8)**

`jevdemo/scoring.py`:
```python
"""Einheiten × Fragen -> Jev-Aufrufe (parallel) -> token-gewichtete Aggregation.

Fragen werden je Einheit greedy in Gruppen gepackt, so dass Einheit + Gruppe
unter dem Token-Budget bleiben. Im Chunk-Modus ist das fast immer eine Gruppe
je Chunk; im Gesamttext-Modus steht der große Manifesto-Block allein.
"""

import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from jevdemo import manifesto
from jevdemo.chunking import Einheit, estimate_tokens, shrink
from jevdemo.config import Config, aktive
from jevdemo.jev_client import PREIS_JE_M_INPUT, JevFehler, ZuLang, cost_usd

RESERVE = 200            # Token-Puffer je Aufruf für JSON-Rahmen und Schätzfehler
WORKERS = 6
SEKUNDEN_JE_AUFRUF = 0.8
KUERZUNG = 0.15
MAX_KUERZUNGEN = 3


def question_tokens(question: dict) -> int:
    return estimate_tokens(json.dumps(question, ensure_ascii=False))


def pack_questions(unit_tokens: int, questions: dict[str, dict], budget: int) -> list[dict[str, dict]]:
    """Fragen in Gruppen, so dass unit_tokens + RESERVE + Fragen <= budget. Eine zu große Frage geht allein."""
    gruppen: list[dict[str, dict]] = []
    aktuell: dict[str, dict] = {}
    laenge = unit_tokens + RESERVE
    for name, q in questions.items():
        tokens = question_tokens(q)
        if aktuell and laenge + tokens > budget:
            gruppen.append(aktuell)
            aktuell, laenge = {}, unit_tokens + RESERVE
        aktuell[name] = q
        laenge += tokens
    if aktuell:
        gruppen.append(aktuell)
    return gruppen


def text_budget(questions: dict[str, dict], budget: int) -> int:
    """So viele Token darf der Gesamttext haben, damit auch die größte Frage noch passt."""
    groesste = max((question_tokens(q) for q in questions.values()), default=0)
    return budget - groesste - RESERVE


@dataclass
class EinheitErgebnis:
    einheit: Einheit
    antworten: dict[str, dict] = field(default_factory=dict)
    fehler: list[str] = field(default_factory=list)


@dataclass
class Lauf:
    modus: str
    einheiten: list[EinheitErgebnis]
    anteil_bewertet: float = 1.0
    aufrufe: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    kosten_usd: float = 0.0
    sekunden: float = 0.0
    modell: str | None = None
    fehler: list[str] = field(default_factory=list)


def schaetzung(units: list[Einheit], questions: dict[str, dict], budget: int) -> dict:
    """Vor dem Lauf: Aufrufe, Input-Token, Kosten und grobe Dauer."""
    aufrufe = tokens = 0
    for u in units:
        for gruppe in pack_questions(u.tokens, questions, budget):
            aufrufe += 1
            tokens += u.tokens + sum(question_tokens(q) for q in gruppe.values())
    return {
        "aufrufe": aufrufe,
        "input_tokens": tokens,
        "kosten_usd": round(tokens / 1e6 * PREIS_JE_M_INPUT, 5),
        "sekunden": round(aufrufe / WORKERS * SEKUNDEN_JE_AUFRUF, 1),
    }


def _state(text_typ: str, text: str):
    return {"text_type": text_typ, "text": text} if text_typ else text


def _verbuche(lauf: Lauf, antwort: dict) -> None:
    nutzung = antwort.get("usage", {})
    lauf.aufrufe += 1
    lauf.input_tokens += nutzung.get("input_tokens", 0)
    lauf.output_tokens += nutzung.get("output_tokens", 0)
    lauf.kosten_usd += cost_usd(nutzung)
    lauf.modell = antwort.get("model", lauf.modell)


def run(units: list[Einheit], questions: dict[str, dict], client, *, text_typ: str, budget: int,
        modus: str, kuerzbar: bool = False, anteil: float = 1.0, workers: int = WORKERS,
        progress=None) -> Lauf:
    """Alle Aufrufe für einen Modus. Einzelfehler landen in lauf.fehler, der Lauf geht weiter."""
    start = time.perf_counter()
    lauf = Lauf(modus=modus, einheiten=[EinheitErgebnis(u) for u in units], anteil_bewertet=anteil)
    if kuerzbar:
        if len(units) != 1:
            raise ValueError("kuerzbar gilt nur für genau eine Einheit (Gesamttext)")
        _bewerte_kuerzbar(lauf, questions, client, text_typ, budget, progress)
    else:
        _bewerte_parallel(lauf, questions, client, text_typ, budget, workers, progress)
    lauf.sekunden = round(time.perf_counter() - start, 3)
    return lauf


def _bewerte_kuerzbar(lauf: Lauf, questions, client, text_typ, budget, progress) -> None:
    """Gesamttext: Gruppen nacheinander. Bei ZuLang kürzen und alle Gruppen neu, damit jede Antwort denselben Text meint."""
    erg = lauf.einheiten[0]
    anteil_start, laenge_start = lauf.anteil_bewertet, len(erg.einheit.text)
    for kuerzung in range(MAX_KUERZUNGEN + 1):
        gruppen = pack_questions(erg.einheit.tokens, questions, budget)
        antworten: dict[str, dict] = {}
        namen = ""
        try:
            for i, gruppe in enumerate(gruppen):
                namen = ", ".join(gruppe)
                antwort = client.decide(_state(text_typ, erg.einheit.text), gruppe)
                _verbuche(lauf, antwort)
                antworten.update(antwort["answers"])
                if progress:
                    progress(i + 1, len(gruppen))
        except ZuLang:
            if kuerzung == MAX_KUERZUNGEN:
                meldung = "Text ist auch nach dreimaligem Kürzen zu lang"
                erg.fehler.append(meldung)
                lauf.fehler.append(f"Einheit 0: {meldung}")
                return
            erg.einheit = shrink(erg.einheit, KUERZUNG)
            lauf.anteil_bewertet = round(anteil_start * len(erg.einheit.text) / laenge_start, 3)
            continue
        except JevFehler as e:
            erg.fehler.append(str(e))
            lauf.fehler.append(f"Einheit 0 ({namen}): {e}")
            erg.antworten = antworten
            return
        erg.antworten = antworten
        return


def _bewerte_parallel(lauf: Lauf, questions, client, text_typ, budget, workers, progress) -> None:
    """Chunks: alle (Einheit, Gruppe)-Aufrufe im Thread-Pool; Verbuchung im aufrufenden Thread."""
    jobs = [(erg, gruppe) for erg in lauf.einheiten
            for gruppe in pack_questions(erg.einheit.tokens, questions, budget)]
    erledigt = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(client.decide, _state(text_typ, erg.einheit.text), gruppe): (erg, gruppe)
                   for erg, gruppe in jobs}
        for future in as_completed(futures):
            erg, gruppe = futures[future]
            try:
                antwort = future.result()
                _verbuche(lauf, antwort)
                erg.antworten.update(antwort["answers"])
            except Exception as e:  # JevFehler, aber auch kaputtes JSON o. ä.
                erg.fehler.append(str(e))
                lauf.fehler.append(f"Einheit {erg.einheit.index} ({', '.join(gruppe)}): {e}")
            erledigt += 1
            if progress:
                progress(erledigt, len(jobs))
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_scoring.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add jevdemo/scoring.py tests/test_scoring.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Scoring: Fragen packen, parallele Aufrufe, Kürzen bei Überlänge

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Scoring, Teil 2: token-gewichtete Aggregation

**Files:**
- Modify: `jevdemo/scoring.py` (am Ende anhängen)
- Test: `tests/test_scoring.py` (am Ende anhängen)

**Interfaces:**
- Consumes: `config.Frage` (Felder `type`, `criteria`, `skala`, `kennzahlen`), `manifesto.anteile/domaenen/top/kennzahlen`.
- Produces: `aggregate(lauf: Lauf, config: Config, katalog: list[Kategorie]) -> dict[str, dict]` mit je Frage:
  - noul: `{"type": "noul", "noul", "min", "max", "n"}`
  - choice: `{"type": "choice", "choice", "probabilities", "confidence", "argmax_anteile", "n"}`
  - score: `{"type": "score", "wert", "stufe", "probabilities", "confidence", "n"}`
  - manifesto: wie choice mit `"type": "manifesto"` plus `anteile`, `domaenen`, `top`, `kennzahlen`
  - ohne Antwort: `{"type": <typ>, "n": 0}`

- [ ] **Step 1: Failing Tests anhängen**

An `tests/test_scoring.py` anhängen:
```python
from jevdemo import config as cfg
from jevdemo import manifesto
from jevdemo.scoring import EinheitErgebnis, Lauf


def _lauf_fuer_aggregation() -> Lauf:
    e1 = EinheitErgebnis(Einheit(0, "a", 1, 1, 100), antworten={
        "ja": {"type": "noul", "noul": 0.2},
        "wahl": {"type": "choice", "choice": "A", "probabilities": {"A": 0.8, "B": 0.2}, "confidence": 0.8},
        "stufe": {"type": "score", "score": 0.0, "probabilities": {"0": 1.0, "1": 0.0, "2": 0.0}, "confidence": 0.5},
        "manifesto": {"type": "choice", "choice": "104 Military: Positive",
                      "probabilities": {"104 Military: Positive": 1.0, "000 No meaningful category applies": 0.0},
                      "confidence": 0.9},
    })
    e2 = EinheitErgebnis(Einheit(1, "b", 1, 1, 300), antworten={
        "ja": {"type": "noul", "noul": 0.6},
        "wahl": {"type": "choice", "choice": "B", "probabilities": {"A": 0.2, "B": 0.8}, "confidence": 0.6},
        "stufe": {"type": "score", "score": 2.0, "probabilities": {"0": 0.0, "1": 0.0, "2": 1.0}, "confidence": 0.7},
        "manifesto": {"type": "choice", "choice": "104 Military: Positive",
                      "probabilities": {"104 Military: Positive": 1.0, "000 No meaningful category applies": 0.0},
                      "confidence": 0.7},
    })
    e3 = EinheitErgebnis(Einheit(2, "c", 2, 2, 500), fehler=["HTTP 500: kaputt"])  # keine Antworten
    return Lauf(modus="chunks", einheiten=[e1, e2, e3])


def _config_fuer_aggregation() -> cfg.Config:
    return cfg.Config(fragen=[
        cfg.Frage("ja", "noul", "?"),
        cfg.Frage("wahl", "choice", "?", criteria={"A": "a", "B": "b"}),
        cfg.Frage("stufe", "score", "?", criteria=["s1", "s2", "s3"], skala=[1, 5]),
        cfg.Frage("manifesto", "manifesto", "?", domains=["1"], kennzahlen=["rile", "intpeace"]),
        cfg.Frage("ohne", "noul", "?"),
        cfg.Frage("inaktiv", "noul", "?", aktiv=False),
    ])


def test_aggregate_gewichtet_nach_tokens():
    agg = scoring.aggregate(_lauf_fuer_aggregation(), _config_fuer_aggregation(), manifesto.load_catalog())
    assert set(agg) == {"ja", "wahl", "stufe", "manifesto", "ohne"}
    assert agg["ja"] == {"type": "noul", "noul": 0.5, "min": 0.2, "max": 0.6, "n": 2}
    assert agg["wahl"]["choice"] == "B"
    assert agg["wahl"]["probabilities"] == {"A": 0.35, "B": 0.65}
    assert agg["wahl"]["confidence"] == 0.65
    assert agg["wahl"]["argmax_anteile"] == {"A": 0.5, "B": 0.5}
    assert agg["wahl"]["n"] == 2
    assert agg["stufe"]["probabilities"] == {"0": 0.25, "1": 0.0, "2": 0.75}
    assert agg["stufe"]["stufe"] == 1.5
    assert agg["stufe"]["wert"] == 4.0
    assert agg["stufe"]["confidence"] == 0.65
    assert agg["ohne"] == {"type": "noul", "n": 0}


def test_aggregate_manifesto_anteile_und_kennzahlen():
    agg = scoring.aggregate(_lauf_fuer_aggregation(), _config_fuer_aggregation(), manifesto.load_catalog())
    m = agg["manifesto"]
    assert m["type"] == "manifesto"
    assert m["choice"] == "104 Military: Positive"
    assert m["anteile"] == {"104": 100.0, "000": 0.0}
    assert m["domaenen"]["1"] == 100.0 and m["domaenen"]["0"] == 0.0
    assert m["top"][0] == ("104", "Military: Positive", 100.0)
    assert m["kennzahlen"] == {"rile": 100.0, "intpeace": 0.0}
    assert m["confidence"] == 0.75
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_scoring.py -q`
Expected: 2 FAIL mit `AttributeError: module 'jevdemo.scoring' has no attribute 'aggregate'`

- [ ] **Step 3: Implementierung anhängen**

An `jevdemo/scoring.py` anhängen:
```python


def _gewichtet(gewichte: list[float], werte: list[float]) -> float:
    return sum(g * w for g, w in zip(gewichte, werte))


def aggregate(lauf: Lauf, config: Config, katalog: list[manifesto.Kategorie]) -> dict[str, dict]:
    """Je aktiver Frage ein Aggregat über alle Einheiten mit Antwort, gewichtet mit einheit.tokens."""
    out: dict[str, dict] = {}
    for frage in aktive(config):
        paare = [(e.einheit.tokens, e.antworten[frage.name]) for e in lauf.einheiten if frage.name in e.antworten]
        if not paare:
            out[frage.name] = {"type": frage.type, "n": 0}
            continue
        summe = sum(t for t, _ in paare) or 1
        gewichte = [t / summe for t, _ in paare]
        antworten = [a for _, a in paare]
        n = len(antworten)
        confidence = round(_gewichtet(gewichte, [a.get("confidence", 0.0) for a in antworten]), 4)

        if frage.type == "noul":
            werte = [a["noul"] for a in antworten]
            out[frage.name] = {"type": "noul", "noul": round(_gewichtet(gewichte, werte), 4),
                               "min": min(werte), "max": max(werte), "n": n}
        elif frage.type == "score":
            stufen = len(frage.criteria)
            probs = {str(i): round(_gewichtet(gewichte, [a["probabilities"].get(str(i), 0.0) for a in antworten]), 4)
                     for i in range(stufen)}
            stufe = sum(i * probs[str(i)] for i in range(stufen))
            unten, oben = frage.skala
            wert = unten + stufe * (oben - unten) / (stufen - 1)
            out[frage.name] = {"type": "score", "wert": round(wert, 2), "stufe": round(stufe, 3),
                               "probabilities": probs, "confidence": confidence, "n": n}
        else:  # choice und manifesto
            optionen = list(antworten[0]["probabilities"])
            probs = {o: round(_gewichtet(gewichte, [a["probabilities"].get(o, 0.0) for a in antworten]), 4)
                     for o in optionen}
            zaehler = Counter(a["choice"] for a in antworten)
            ergebnis = {"type": frage.type, "choice": max(probs, key=probs.get), "probabilities": probs,
                        "confidence": confidence,
                        "argmax_anteile": {o: round(c / n, 4) for o, c in zaehler.items()}, "n": n}
            if frage.type == "manifesto":
                ant = manifesto.anteile(probs)
                ergebnis.update({
                    "anteile": ant,
                    "domaenen": manifesto.domaenen(ant, katalog),
                    "top": manifesto.top(ant, katalog),
                    "kennzahlen": manifesto.kennzahlen(ant, frage.kennzahlen or []),
                })
            out[frage.name] = ergebnis
    return out
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest -q`
Expected: alle Tests grün (`54 passed` bis hierher: 2 + 7 + 12 + 4 + 7 + 10 + 10 + 2)

- [ ] **Step 5: Commit**

```bash
git add jevdemo/scoring.py tests/test_scoring.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Scoring: token-gewichtete Aggregation je Fragetyp, Manifesto-Kennzahlen

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Ergebnisobjekt, JSON, Live-Rauchtest

**Files:**
- Create: `jevdemo/results.py`
- Test: `tests/test_results.py`, `tests/test_live.py`

**Interfaces:**
- Consumes: `chunking.estimate_tokens`, `config.to_dict`, `pdf_text.Seite`, `scoring.Lauf`, `scoring.EinheitErgebnis`.
- Produces:
  - `APP_VERSION = "0.1.0"`
  - `meta(dateiname: str, data: bytes, pages: list[Seite], modell: str) -> dict`
  - `lauf_to_dict(lauf: Lauf, aggregat: dict) -> dict`
  - `build(meta_: dict, config: Config, laeufe: dict[str, tuple[Lauf, dict]]) -> dict`
  - `to_json(result: dict) -> str`

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_results.py`:
```python
import hashlib
import json

from jevdemo import config as cfg
from jevdemo import results
from jevdemo.chunking import Einheit, estimate_tokens
from jevdemo.pdf_text import Seite
from jevdemo.scoring import EinheitErgebnis, Lauf


def test_meta():
    pages = [Seite(1, "Prüfung eins."), Seite(2, "Zwei.")]
    m = results.meta("doc.pdf", b"abc", pages, "typesafe/jev-1.13")
    text = "Prüfung eins.\n\nZwei."
    assert m["datei"] == "doc.pdf"
    assert m["sha256"] == hashlib.sha256(b"abc").hexdigest()
    assert m["seiten"] == 2 and m["zeichen"] == len(text)
    assert m["token_geschaetzt"] == estimate_tokens(text)
    assert m["modell"] == "typesafe/jev-1.13" and m["app_version"] == results.APP_VERSION
    assert "T" in m["erstellt"]


def test_build_und_json():
    lauf = Lauf(modus="chunks", modell="typesafe/jev-1.13-x", aufrufe=1, input_tokens=10, output_tokens=2,
                kosten_usd=0.0000042, sekunden=0.512, fehler=[],
                einheiten=[EinheitErgebnis(Einheit(0, "Prüfung eins.", 1, 1, 4),
                                           antworten={"ja": {"type": "noul", "noul": 0.5}})])
    config = cfg.Config(text_typ="Prüfung", fragen=[cfg.Frage("ja", "noul", "?")])
    m = {"datei": "doc.pdf"}
    ergebnis = results.build(m, config, {"chunks": (lauf, {"ja": {"type": "noul", "noul": 0.5, "n": 1}})})
    assert set(ergebnis) == {"meta", "config", "laeufe"}
    assert ergebnis["meta"] is m
    assert ergebnis["config"]["text_typ"] == "Prüfung"
    d = ergebnis["laeufe"]["chunks"]
    assert d["modus"] == "chunks" and d["modell"] == "typesafe/jev-1.13-x"
    assert d["einheiten"] == 1 and d["anteil_bewertet"] == 1.0 and d["aufrufe"] == 1
    assert d["kosten_usd"] == 0.000004 and d["sekunden"] == 0.51
    assert d["aggregat"]["ja"]["noul"] == 0.5
    detail = d["einheiten_detail"][0]
    assert detail == {"index": 0, "seite_von": 1, "seite_bis": 1, "tokens": 4, "zeichen": 13,
                      "antworten": {"ja": {"type": "noul", "noul": 0.5}}, "fehler": None}
    text = results.to_json(ergebnis)
    assert "Prüfung" in text and "\\u00fc" not in text
    assert json.loads(text) == ergebnis
```

`tests/test_live.py`:
```python
"""Echter Aufruf gegen OpenRouter. Läuft nur mit `uv run --env-file .env pytest -m live`."""

import os

import pytest

from jevdemo.jev_client import JevClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="kein OPENROUTER_API_KEY in der Umgebung")
def test_drei_fragetypen_live():
    client = JevClient(os.environ["OPENROUTER_API_KEY"])
    antwort = client.decide(
        {"text_type": "Meinungsbeitrag",
         "text": "Diese Regierung versagt auf ganzer Linie. Wir brauchen endlich mehr Geld für die Bundeswehr."},
        {
            "polemisch": {"type": "noul", "instructions": "Ist der Text polemisch?"},
            "domain": {"type": "choice", "instructions": "Which policy domain is the text about?",
                       "criteria": {"Military": "defence and armed forces", "Welfare": "social policy"}},
            "meinung": {"type": "score", "instructions": "Wie meinungsstark ist der Text?",
                        "criteria": ["neutral", "wertend", "polemisch"]},
        },
    )
    a = antwort["answers"]
    assert 0 <= a["polemisch"]["noul"] <= 1
    assert a["domain"]["choice"] in ("Military", "Welfare")
    assert set(a["domain"]["probabilities"]) == {"Military", "Welfare"}
    assert 0 <= a["meinung"]["score"] <= 2
    assert set(a["meinung"]["probabilities"]) == {"0", "1", "2"}
    assert antwort["usage"]["input_tokens"] > 0
    assert antwort["model"].startswith("typesafe/jev-1.13")
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_results.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'jevdemo.results'`

- [ ] **Step 3: Implementierung**

`jevdemo/results.py`:
```python
"""Ergebnisobjekt für Anzeige und JSON-Download. Rohantworten je Einheit bleiben drin,
damit jeder Aggregatwert aus dem JSON nachrechenbar ist."""

import hashlib
import json
from datetime import datetime

from jevdemo.chunking import estimate_tokens
from jevdemo.config import Config, to_dict
from jevdemo.pdf_text import Seite
from jevdemo.scoring import Lauf

APP_VERSION = "0.1.0"


def meta(dateiname: str, data: bytes, pages: list[Seite], modell: str) -> dict:
    text = "\n\n".join(s.text for s in pages)
    return {
        "erstellt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "modell": modell,
        "datei": dateiname,
        "sha256": hashlib.sha256(data).hexdigest(),
        "seiten": len(pages),
        "zeichen": len(text),
        "token_geschaetzt": estimate_tokens(text),
    }


def lauf_to_dict(lauf: Lauf, aggregat: dict) -> dict:
    return {
        "modus": lauf.modus,
        "modell": lauf.modell,
        "einheiten": len(lauf.einheiten),
        "anteil_bewertet": lauf.anteil_bewertet,
        "aufrufe": lauf.aufrufe,
        "input_tokens": lauf.input_tokens,
        "output_tokens": lauf.output_tokens,
        "kosten_usd": round(lauf.kosten_usd, 6),
        "sekunden": round(lauf.sekunden, 2),
        "fehler": list(lauf.fehler),
        "aggregat": aggregat,
        "einheiten_detail": [
            {
                "index": e.einheit.index,
                "seite_von": e.einheit.seite_von,
                "seite_bis": e.einheit.seite_bis,
                "tokens": e.einheit.tokens,
                "zeichen": len(e.einheit.text),
                "antworten": e.antworten,
                "fehler": e.fehler or None,
            }
            for e in lauf.einheiten
        ],
    }


def build(meta_: dict, config: Config, laeufe: dict[str, tuple[Lauf, dict]]) -> dict:
    return {
        "meta": meta_,
        "config": to_dict(config),
        "laeufe": {name: lauf_to_dict(lauf, aggregat) for name, (lauf, aggregat) in laeufe.items()},
    }


def to_json(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: Tests laufen lassen, dann den Live-Test**

Run: `uv run pytest -q`
Expected: alle grün, Live-Test wird nicht gesammelt (addopts `-m 'not live'`).

Run: `uv run --env-file .env pytest -m live -q`
Expected: `1 passed` (kostet unter 0,0001 USD). Schlägt er mit HTTP 401 fehl, stimmt der Key in `.env` nicht; mit 404 hat OpenRouter den `alpha`-Pfad verschoben, dann `JEV_ENDPOINT` prüfen.

- [ ] **Step 5: Commit**

```bash
git add jevdemo/results.py tests/test_results.py tests/test_live.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Ergebnisobjekt mit Meta, Config, Läufen; Live-Rauchtest gegen OpenRouter

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Darstellung: Farb-Helfer, Kacheln, Balken, Chunk-Tabelle

**Files:**
- Create: `jevdemo/ui/views.py`
- Test: `tests/test_views.py` (nur die reinen Helfer; das Zeichnen wird in Task 13 im Browser geprüft)

**Interfaces:**
- Consumes: Ergebnis-Dict aus `results.build`, `config.Config`/`config.aktive`, `manifesto.DOMAENEN`.
- Produces:
  - Konstanten `KATEGORIAL` (8 Hex), `SONSTIGE`, `BLAU`, `ROT`, `MITTE`, `TEXT_DUNKEL`, `TEXT_HELL`, `KENNZAHL_HILFE`
  - `mische(a: str, b: str, t: float) -> str`, `noul_farbe(wert: float) -> str`, `textfarbe(hintergrund: str) -> str`, `optionsfarbe(index: int) -> str`, `kurz(text: str, n: int = 48) -> str`
  - `kachel(titel, text, farbe, untertitel="")`, `balken(labels, werte, farben, x_titel, hoehe=None) -> go.Figure`, `rile_balken(wert) -> go.Figure`
  - `render_meta(ergebnis: dict)`, `render_results(ergebnis: dict, config: Config)`

- [ ] **Step 1: Failing Tests schreiben**

`tests/test_views.py`:
```python
from jevdemo.ui import views


def test_mische_und_noul_farbe():
    assert views.mische("#000000", "#ffffff", 0.5) == "#808080"
    assert views.noul_farbe(0.0) == views.ROT
    assert views.noul_farbe(0.5) == views.MITTE
    assert views.noul_farbe(1.0) == views.BLAU
    assert views.noul_farbe(-3) == views.ROT
    assert views.noul_farbe(7) == views.BLAU
    assert views.noul_farbe(0.25) not in (views.ROT, views.MITTE)


def test_textfarbe_nach_luminanz():
    assert views.textfarbe("#2a78d6") == views.TEXT_HELL
    assert views.textfarbe("#e34948") == views.TEXT_HELL
    assert views.textfarbe("#f0efec") == views.TEXT_DUNKEL
    assert views.textfarbe("#eda100") == views.TEXT_DUNKEL


def test_optionsfarbe_und_kurz():
    assert views.optionsfarbe(0) == "#2a78d6"
    assert views.optionsfarbe(7) == "#e34948"
    assert views.optionsfarbe(8) == views.SONSTIGE
    assert views.kurz("kurz") == "kurz"
    assert views.kurz("a" * 60, 10) == "a" * 9 + "…"


def test_balken_figur():
    fig = views.balken(["a", "b"], [10.0, 20.0], views.BLAU, "x")
    assert list(fig.data[0].x) == [10.0, 20.0]
    assert fig.data[0].orientation == "h"
    fig = views.rile_balken(-12.0)
    assert fig.data[0].marker.color == views.ROT
    assert fig.layout.xaxis.range == (-100, 100)
```

- [ ] **Step 2: Tests laufen lassen, Fehlschlag prüfen**

Run: `uv run pytest tests/test_views.py -q`
Expected: FAIL mit `ModuleNotFoundError: No module named 'jevdemo.ui.views'`

- [ ] **Step 3: Implementierung**

`jevdemo/ui/views.py`:
```python
"""Darstellung der Ergebnisse: Kacheln für noul/choice, Balken für score und Manifesto.

Farben aus der dataviz-Referenzpalette (Light). Kategoriale Slots in fester Reihenfolge,
eine Farbe je Entität (Option, Domäne); Magnitude in einem Blau; Polarität rot↔blau mit
neutraler Mitte. Text auf Kacheln nach Luminanz dunkel oder hell.
"""

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from jevdemo import config as cfg
from jevdemo import manifesto

KATEGORIAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SONSTIGE = "#9a9892"
BLAU, ROT, MITTE = "#2a78d6", "#e34948", "#f0efec"
TEXT_DUNKEL, TEXT_HELL = "#0b0b0b", "#ffffff"
MODUS_TITEL = {"gesamttext": "Gesamttext", "chunks": "Chunks (Mittelwert)"}
KENNZAHL_HILFE = {
    "rile": "Rechts-links-Position nach Laver/Budge: Summe rechter minus Summe linker Kategorien, in Prozentpunkten. "
            "Im Gesamttext-Modus ist das die Verteilung einer einzigen Entscheidung, im Chunk-Modus der "
            "token-gewichtete Mittelwert vieler Entscheidungen (näher am Manifesto-Verfahren).",
    "planeco": "Planwirtschaft: 403 Marktregulierung + 404 Wirtschaftsplanung + 412 gelenkte Wirtschaft.",
    "markeco": "Marktwirtschaft: 401 freier Markt + 414 wirtschaftliche Orthodoxie.",
    "welfare": "Wohlfahrt: 503 Gleichheit + 504 Ausbau des Sozialstaats.",
    "intpeace": "Internationaler Frieden: 102 besondere Beziehungen negativ + 105 Militär negativ + 106 Frieden.",
}


def _rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def mische(a: str, b: str, t: float) -> str:
    """Linear zwischen zwei Hex-Farben, t = 0 → a, t = 1 → b."""
    return _hex(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b)))


def noul_farbe(wert: float) -> str:
    """0 → rot (nein), 0.5 → neutral, 1 → blau (ja)."""
    wert = max(0.0, min(1.0, wert))
    if wert <= 0.5:
        return mische(ROT, MITTE, wert * 2)
    return mische(MITTE, BLAU, (wert - 0.5) * 2)


def textfarbe(hintergrund: str) -> str:
    """Dunkler Text auf hellen Flächen, heller auf dunklen (relative Luminanz nach sRGB)."""

    def lin(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in _rgb(hintergrund))
    return TEXT_DUNKEL if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 else TEXT_HELL


def optionsfarbe(index: int) -> str:
    return KATEGORIAL[index] if 0 <= index < len(KATEGORIAL) else SONSTIGE


def kurz(text: str, n: int = 48) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def kachel(titel: str, text: str, farbe: str, untertitel: str = "") -> None:
    ink = textfarbe(farbe)
    unten = f'<div style="font-size:0.85rem;opacity:0.85">{html.escape(untertitel)}</div>' if untertitel else ""
    st.markdown(
        f'<div style="background:{farbe};color:{ink};padding:14px 18px;border-radius:8px;margin:4px 0 12px 0">'
        f'<div style="font-size:0.85rem;opacity:0.85">{html.escape(titel)}</div>'
        f'<div style="font-size:1.5rem;font-weight:600">{html.escape(text)}</div>{unten}</div>',
        unsafe_allow_html=True,
    )


def balken(labels: list[str], werte: list[float], farben, x_titel: str, hoehe: int | None = None) -> go.Figure:
    """Horizontale Balken, dünn, mit Wert außen; eine Farbe (str) oder eine Liste je Balken."""
    fig = go.Figure(go.Bar(
        x=werte, y=labels, orientation="h",
        marker=dict(color=farben, line=dict(width=0)),
        text=[f"{v:.1f}" for v in werte], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        height=hoehe or max(160, 26 * len(labels) + 70),
        margin=dict(l=10, r=40, t=10, b=30),
        yaxis=dict(autorange="reversed", tickfont=dict(size=12)),
        xaxis=dict(title=x_titel, showgrid=True, gridcolor="#eeeeee", zeroline=False),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False, bargap=0.25,
    )
    return fig


def rile_balken(wert: float) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[wert], y=["rile"], orientation="h",
        marker=dict(color=BLAU if wert >= 0 else ROT, line=dict(width=0)),
        hovertemplate="rile: %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        height=110, margin=dict(l=10, r=10, t=10, b=30),
        xaxis=dict(range=[-100, 100], zeroline=True, zerolinecolor="#888888", title="links  ←  rile  →  rechts"),
        yaxis=dict(showticklabels=False), plot_bgcolor="white", paper_bgcolor="white", bargap=0.4,
    )
    return fig


def render_meta(ergebnis: dict) -> None:
    teile = []
    for name, lauf in ergebnis["laeufe"].items():
        text = (f"{MODUS_TITEL.get(name, name)}: {lauf['einheiten']} Einheiten, "
                f"{lauf['anteil_bewertet']:.0%} des Textes, {lauf['aufrufe']} Aufrufe, "
                f"{lauf['input_tokens']:,} Token, {lauf['kosten_usd']:.4f} USD, {lauf['sekunden']:.1f} s")
        if lauf["fehler"]:
            text += f", {len(lauf['fehler'])} Fehler"
        teile.append(text.replace(",", "."))
    modell = next((l["modell"] for l in ergebnis["laeufe"].values() if l.get("modell")), ergebnis["meta"]["modell"])
    st.caption(f"Modell {modell} · " + " · ".join(teile))


def _noul_block(frage: cfg.Frage, agg: dict) -> None:
    kachel(frage.instructions, f"{agg['noul']:.2f}", noul_farbe(agg["noul"]), f"0 = nein, 1 = ja · n = {agg['n']}")


def _choice_block(frage: cfg.Frage, agg: dict, key: str) -> None:
    optionen = list(frage.criteria)
    farbe = optionsfarbe(optionen.index(agg["choice"])) if agg["choice"] in optionen else SONSTIGE
    kachel(frage.instructions, agg["choice"], farbe, f"Confidence {agg['confidence']:.2f} · n = {agg['n']}")
    top5 = sorted(agg["probabilities"].items(), key=lambda kv: -kv[1])[:5]
    farben = [optionsfarbe(optionen.index(o)) if o in optionen else SONSTIGE for o, _ in top5]
    fig = balken([kurz(o) for o, _ in top5], [p * 100 for _, p in top5], farben, "Wahrscheinlichkeit in %")
    st.plotly_chart(fig, width="stretch", key=key)


def _score_block(frage: cfg.Frage, agg: dict, key: str) -> None:
    unten, oben = frage.skala
    st.markdown(f"**{frage.instructions}**  \n"
                f"{agg['wert']:.2f} auf der Skala {unten} bis {oben} · Confidence {agg['confidence']:.2f} · n = {agg['n']}")
    labels = [f"{i}: {kurz(s, 60)}" for i, s in enumerate(frage.criteria)]
    werte = [agg["probabilities"].get(str(i), 0.0) * 100 for i in range(len(frage.criteria))]
    st.plotly_chart(balken(labels, werte, BLAU, "Wahrscheinlichkeit je Stufe in %"), width="stretch", key=key)


def _manifesto_block(frage: cfg.Frage, agg: dict, key: str) -> None:
    st.markdown(f"**Manifesto-Kategorien** · Confidence {agg['confidence']:.2f} · n = {agg['n']}")
    top = agg["top"][:10]
    fig = balken([f"{code} {kurz(title, 40)}" for code, title, _ in top], [p for *_, p in top], BLAU, "Anteil in %")
    st.plotly_chart(fig, width="stretch", key=f"{key}_top")
    dom = [(code, manifesto.DOMAENEN[code], p) for code, p in agg["domaenen"].items() if code != "0" or p > 0]
    fig = balken([f"{c} {n}" for c, n, _ in dom], [p for *_, p in dom],
                 [optionsfarbe(int(c)) for c, *_ in dom], "Anteil je Domäne in %")
    st.plotly_chart(fig, width="stretch", key=f"{key}_dom")
    kennzahlen = agg.get("kennzahlen", {})
    if kennzahlen:
        spalten = st.columns(len(kennzahlen))
        for spalte, (name, wert) in zip(spalten, kennzahlen.items()):
            spalte.metric(name, f"{wert:.1f}", help=KENNZAHL_HILFE.get(name, ""))
        if "rile" in kennzahlen:
            st.plotly_chart(rile_balken(kennzahlen["rile"]), width="stretch", key=f"{key}_rile")


def _chunk_tabelle(lauf: dict, config: cfg.Config) -> None:
    zeilen = []
    for d in lauf["einheiten_detail"]:
        zeile: dict = {"Chunk": d["index"], "Seiten": f"{d['seite_von']}–{d['seite_bis']}", "Token": d["tokens"]}
        for frage in cfg.aktive(config):
            a = d["antworten"].get(frage.name)
            if a is None:
                zeile[frage.name] = None
            elif frage.type == "noul":
                zeile[frage.name] = round(a["noul"], 2)
            elif frage.type == "score":
                unten, oben = frage.skala
                zeile[frage.name] = round(unten + a["score"] * (oben - unten) / (len(frage.criteria) - 1), 2)
            else:
                zeile[frage.name] = a["choice"]
        zeile["Fehler"] = "; ".join(d["fehler"]) if d["fehler"] else ""
        zeilen.append(zeile)
    with st.expander(f"Je Chunk ({len(zeilen)})"):
        st.dataframe(pd.DataFrame(zeilen), width="stretch", hide_index=True)


def render_results(ergebnis: dict, config: cfg.Config) -> None:
    laeufe = ergebnis["laeufe"]
    spalten = st.columns(len(laeufe))
    for spalte, (name, lauf) in zip(spalten, laeufe.items()):
        with spalte:
            st.subheader(MODUS_TITEL.get(name, name))
            if lauf["fehler"]:
                with st.expander(f"{len(lauf['fehler'])} Fehler"):
                    st.text("\n".join(lauf["fehler"]))
            for frage in cfg.aktive(config):
                agg = lauf["aggregat"].get(frage.name)
                key = f"{name}_{frage.name}"
                if not agg or agg.get("n", 0) == 0:
                    st.warning(f"{frage.name}: keine Antwort")
                elif frage.type == "noul":
                    _noul_block(frage, agg)
                elif frage.type == "choice":
                    _choice_block(frage, agg, key)
                elif frage.type == "score":
                    _score_block(frage, agg, key)
                else:
                    _manifesto_block(frage, agg, key)
            if name == "chunks":
                _chunk_tabelle(lauf, config)
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_views.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add jevdemo/ui/views.py tests/test_views.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Darstellung: Farb-Helfer, Kacheln, Balken, Manifesto-Block, Chunk-Tabelle

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Formular-Editor in der Seitenleiste

**Files:**
- Create: `jevdemo/ui/editor.py`

**Interfaces:**
- Consumes: `config.Config`, `config.Frage`, `config.load`, `config.to_yaml`, `manifesto.DOMAENEN`, `manifesto.KENNZAHLEN`, `st.session_state["config"]` (die Config, die `app.py` dort ablegt).
- Produces: `render_editor(config: Config, katalog) -> Config`. Verändert die übergebene Config in place (Widgets schreiben in die Frage-Objekte) und gibt sie zurück. Widget-Keys beginnen mit `q__` (je Frage) oder `cfg__`/`neu__`; Callbacks `_typ_geaendert`, `_loeschen`, `_hinzufuegen`, `_reset` arbeiten auf `st.session_state["config"]`.

Kein Unit-Test: Streamlit-Widgets brauchen den Streamlit-Runner. Die Prüfung ist Schritt 2 (Import) plus der Browser-Test in Task 13.

- [ ] **Step 1: Implementierung**

`jevdemo/ui/editor.py`:
```python
"""Formular pro Frage in der Seitenleiste. Die Config lebt in st.session_state["config"];
config.yaml auf der Platte wird nie beschrieben."""

import pandas as pd
import streamlit as st

from jevdemo import config as cfg
from jevdemo import manifesto

PREFIX = "q__"
TYPEN = ["noul", "choice", "score"]
DOMAENEN_OPTIONEN = [f"{code} {name}" for code, name in manifesto.DOMAENEN.items() if code != "0"]


def _key(name: str, feld: str) -> str:
    return f"{PREFIX}{name}__{feld}"


def _startwerte(typ: str) -> dict:
    """criteria/skala beim Anlegen oder Typwechsel."""
    if typ == "score":
        return {"criteria": ["Stufe 1", "Stufe 2", "Stufe 3"], "skala": [1, 5]}
    if typ == "choice":
        return {"criteria": {"Option A": "", "Option B": ""}, "skala": None}
    return {"criteria": None, "skala": None}


def _widget_keys_loeschen(name: str | None = None) -> None:
    praefixe = (f"{PREFIX}{name}__",) if name else (PREFIX, "cfg__")
    for key in list(st.session_state):
        if key.startswith(praefixe):
            del st.session_state[key]


def _frage(name: str) -> cfg.Frage:
    return next(f for f in st.session_state["config"].fragen if f.name == name)


def _typ_geaendert(name: str) -> None:
    frage = _frage(name)
    frage.type = st.session_state[_key(name, "type")]
    for feld, wert in _startwerte(frage.type).items():
        setattr(frage, feld, wert)
    for feld in ("criteria", "skala_min", "skala_max"):
        st.session_state.pop(_key(name, feld), None)


def _loeschen(name: str) -> None:
    config = st.session_state["config"]
    config.fragen = [f for f in config.fragen if f.name != name]
    _widget_keys_loeschen(name)


def _hinzufuegen() -> None:
    name = st.session_state.get("neu__name", "").strip()
    typ = st.session_state.get("neu__type", "noul")
    config = st.session_state["config"]
    if not cfg.SLUG.match(name):
        st.session_state["neu__fehler"] = "Name darf nur a-z, 0-9 und _ enthalten"
        return
    if any(f.name == name for f in config.fragen):
        st.session_state["neu__fehler"] = f"'{name}' gibt es schon"
        return
    config.fragen.append(cfg.Frage(name=name, type=typ, instructions="", **_startwerte(typ)))
    st.session_state["neu__name"] = ""
    st.session_state.pop("neu__fehler", None)


def _reset() -> None:
    st.session_state["config"] = cfg.load()
    _widget_keys_loeschen()


def _zahl(x: float) -> float | int:
    return int(x) if float(x).is_integer() else float(x)


def _frage_block(frage: cfg.Frage) -> None:
    name = frage.name
    frage.aktiv = st.toggle("Aktiv", value=frage.aktiv, key=_key(name, "aktiv"))
    st.selectbox("Typ", TYPEN, index=TYPEN.index(frage.type), key=_key(name, "type"),
                 on_change=_typ_geaendert, args=(name,))
    frage.instructions = st.text_area("Instruction", value=frage.instructions, key=_key(name, "instructions"), height=100)
    if frage.type == "score":
        stufen = st.text_area("Stufen, eine je Zeile, von niedrig nach hoch",
                              value="\n".join(frage.criteria or []), key=_key(name, "criteria"), height=160)
        frage.criteria = [z.strip() for z in stufen.splitlines() if z.strip()]
        skala = frage.skala or [1, 5]
        links, rechts = st.columns(2)
        unten = links.number_input("Skala min", value=float(skala[0]), key=_key(name, "skala_min"))
        oben = rechts.number_input("Skala max", value=float(skala[1]), key=_key(name, "skala_max"))
        frage.skala = [_zahl(unten), _zahl(oben)]
    elif frage.type == "choice":
        criteria = frage.criteria if isinstance(frage.criteria, dict) else {}
        df = pd.DataFrame({"Option": list(criteria), "Beschreibung": list(criteria.values())}, dtype="string")
        bearbeitet = st.data_editor(df, num_rows="dynamic", key=_key(name, "criteria"), width="stretch", hide_index=True)
        frage.criteria = {
            str(o).strip(): ("" if pd.isna(b) else str(b).strip())
            for o, b in zip(bearbeitet["Option"], bearbeitet["Beschreibung"])
            if not pd.isna(o) and str(o).strip()
        }
    st.button("Frage löschen", key=_key(name, "loeschen"), on_click=_loeschen, args=(name,))


def _manifesto_block(frage: cfg.Frage, katalog: list[manifesto.Kategorie]) -> None:
    name = frage.name
    frage.aktiv = st.toggle("Aktiv", value=frage.aktiv, key=_key(name, "aktiv"))
    frage.instructions = st.text_area("Instruction", value=frage.instructions, key=_key(name, "instructions"), height=140)
    vorauswahl = [o for o in DOMAENEN_OPTIONEN if o.split()[0] in (frage.domains or [])]
    auswahl = st.multiselect("Domänen", DOMAENEN_OPTIONEN, default=vorauswahl, key=_key(name, "domains"))
    frage.domains = [o.split()[0] for o in auswahl]
    frage.kennzahlen = st.multiselect("Kennzahlen", list(manifesto.KENNZAHLEN), default=frage.kennzahlen or [],
                                      key=_key(name, "kennzahlen"))
    anzahl = sum(1 for k in katalog if k.domain_code in frage.domains or k.code == "000")
    st.caption(f"{anzahl} Hauptkategorien gehen als Optionen an Jev. Der Katalog selbst ist nicht editierbar.")
    st.button("Frage löschen", key=_key(name, "loeschen"), on_click=_loeschen, args=(name,))


def render_editor(config: cfg.Config, katalog: list[manifesto.Kategorie]) -> cfg.Config:
    st.header("Fragen")
    st.caption(f"Modell: {config.model}")
    config.text_typ = st.text_area("Texttyp (Kontext, geht als text_type an Jev)", value=config.text_typ,
                                   key="cfg__text_typ", height=68)
    for frage in list(config.fragen):
        with st.expander(f"{frage.name} ({frage.type})", expanded=False):
            if frage.type == "manifesto":
                _manifesto_block(frage, katalog)
            else:
                _frage_block(frage)
    st.divider()
    st.subheader("Frage hinzufügen")
    st.text_input("Name (a-z, 0-9, _)", key="neu__name")
    st.selectbox("Typ", TYPEN, key="neu__type")
    st.button("Hinzufügen", on_click=_hinzufuegen)
    if st.session_state.get("neu__fehler"):
        st.error(st.session_state["neu__fehler"])
    st.divider()
    st.button("Zurücksetzen auf config.yaml", on_click=_reset)
    st.download_button("Config als YAML herunterladen", cfg.to_yaml(config), file_name="config.yaml", mime="text/yaml")
    return config
```

- [ ] **Step 2: Import prüfen und Gesamttests**

Run: `uv run python -c "import jevdemo.ui.editor as e; print(e.render_editor.__name__)"`
Expected: `render_editor`

Run: `uv run pytest -q`
Expected: alle grün (`60 passed`)

- [ ] **Step 3: Commit**

```bash
git add jevdemo/ui/editor.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Formular-Editor: Frage pro Block, hinzufügen, löschen, Reset, YAML-Download

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: app.py: Gate, Upload, Steuerung, Lauf, Download

**Files:**
- Create: `app.py`

**Interfaces:**
- Consumes: alles aus Task 2 bis 11: `config.load/validate/to_questions`, `manifesto.load_catalog`, `pdf_text.extract_pages/KeinText/PdfFehler`, `chunking.estimate_tokens/chunk_pages/whole_text`, `scoring.text_budget/schaetzung/run/aggregate`, `results.meta/build/to_json`, `env.lade_env`, `jev_client.JevClient`, `ui.editor.render_editor`, `ui.views.render_meta/render_results`.
- Produces: die lauffähige App. Session-State-Schlüssel: `authed`, `config`, `datei_sha`, `ergebnis`.

- [ ] **Step 1: Implementierung**

`app.py`:
```python
"""Jev Grading Demo: PDF hochladen, Fragen anpassen, mit Jev bewerten lassen."""

import hashlib
import hmac
import os
from pathlib import Path

import streamlit as st

from jevdemo import chunking, config as cfg, manifesto, pdf_text, results, scoring
from jevdemo.env import lade_env
from jevdemo.jev_client import JevClient
from jevdemo.ui.editor import render_editor
from jevdemo.ui.views import render_meta, render_results

ROOT = Path(__file__).resolve().parent
lade_env(ROOT / ".env")

st.set_page_config(page_title="Jev Grading Demo", page_icon="📄", layout="wide")


def _gate() -> None:
    """Passwort-Gate; hält die Seite an, bis das Passwort stimmt."""
    passwort = os.environ.get("APP_PASSWORD", "")
    fehlend = [n for n in ("APP_PASSWORD", "OPENROUTER_API_KEY") if not os.environ.get(n)]
    if fehlend:
        st.error(f"Umgebungsvariable fehlt: {', '.join(fehlend)}. Siehe .env.example.")
        st.stop()
    if st.session_state.get("authed"):
        return
    st.title("Jev Grading Demo")
    eingabe = st.text_input("Passwort", type="password")
    if eingabe and hmac.compare_digest(eingabe.encode(), passwort.encode()):
        st.session_state["authed"] = True
        st.rerun()
    if eingabe:
        st.error("Falsches Passwort")
    st.stop()


@st.cache_data(show_spinner="PDF wird gelesen …")
def _seiten(data: bytes) -> list[pdf_text.Seite]:
    return pdf_text.extract_pages(data)


@st.cache_resource
def _katalog() -> list[manifesto.Kategorie]:
    return manifesto.load_catalog()


def _punkt(zahl: int) -> str:
    return f"{zahl:,}".replace(",", ".")


def _plan(seiten, modus: str, chunk_tokens: int, questions: dict, budget: int) -> dict:
    """Modusname -> (Einheiten, kuerzbar, Anteil)."""
    plan = {}
    if modus in ("Gesamttext", "Beide"):
        einheit, anteil = chunking.whole_text(seiten, scoring.text_budget(questions, budget))
        plan["gesamttext"] = ([einheit], True, anteil)
    if modus in ("Chunks", "Beide"):
        plan["chunks"] = (chunking.chunk_pages(seiten, chunk_tokens), False, 1.0)
    return plan


def main() -> None:
    _gate()
    katalog = _katalog()
    if "config" not in st.session_state:
        st.session_state["config"] = cfg.load()
    with st.sidebar:
        config = render_editor(st.session_state["config"], katalog)
        fehler = cfg.validate(config)
        if fehler:
            st.error("Config ungültig:\n\n- " + "\n- ".join(fehler))

    st.title("Jev Grading Demo")
    st.caption("PDF hochladen, Fragen links anpassen, bewerten lassen. Jev 1.13 über OpenRouter.")
    datei = st.file_uploader("PDF hierher ziehen oder auswählen", type=["pdf"])
    if datei is None:
        st.session_state.pop("ergebnis", None)
        st.session_state.pop("datei_sha", None)
        st.info("Noch kein PDF.")
        st.stop()

    data = datei.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    if st.session_state.get("datei_sha") != sha:
        st.session_state["datei_sha"] = sha
        st.session_state.pop("ergebnis", None)
    try:
        seiten = _seiten(data)
    except pdf_text.KeinText as e:
        st.warning(str(e))
        st.stop()
    except pdf_text.PdfFehler as e:
        st.error(str(e))
        st.stop()

    text_gesamt = "\n\n".join(s.text for s in seiten)
    tokens_gesamt = chunking.estimate_tokens(text_gesamt)
    modus = st.radio("Modus", ["Gesamttext", "Chunks", "Beide"], horizontal=True)
    chunk_tokens = st.slider("Chunk-Größe in Token (geschätzt)", 300, 3000, config.chunk_tokens, 100)
    config.chunk_tokens = chunk_tokens

    spalten = st.columns(4)
    spalten[0].metric("Seiten", len(seiten))
    spalten[1].metric("Zeichen", _punkt(len(text_gesamt)))
    spalten[2].metric("Token (geschätzt)", _punkt(tokens_gesamt))
    spalten[3].metric("Chunks bei dieser Größe", len(chunking.chunk_pages(seiten, chunk_tokens)))
    with st.expander("Textvorschau (erste 3.000 Zeichen)"):
        st.text(text_gesamt[:3000])

    if fehler:
        st.error("Config ungültig, siehe Seitenleiste.")
        st.stop()
    questions = cfg.to_questions(config, katalog)
    if not questions:
        st.warning("Keine aktive Frage.")
        st.stop()

    budget = config.budget_tokens
    plan = _plan(seiten, modus, chunk_tokens, questions, budget)
    schaetz = [scoring.schaetzung(einheiten, questions, budget) for einheiten, _, _ in plan.values()]
    aufrufe = sum(s["aufrufe"] for s in schaetz)
    tokens = sum(s["input_tokens"] for s in schaetz)
    kosten = sum(s["kosten_usd"] for s in schaetz)
    sekunden = sum(s["sekunden"] for s in schaetz)
    st.caption(f"Schätzung: {aufrufe} Aufrufe, {_punkt(tokens)} Token, {kosten:.4f} USD, etwa {sekunden:.0f} s")
    if "gesamttext" in plan and plan["gesamttext"][2] < 1:
        st.warning(f"Gesamttext-Modus: Es werden nur {plan['gesamttext'][2]:.0%} des Textes bewertet "
                   f"(Limit {_punkt(scoring.text_budget(questions, budget))} Token je Aufruf). "
                   f"Der Chunk-Modus deckt den ganzen Text ab.")

    if st.button("Bewerten", type="primary"):
        client = JevClient(os.environ["OPENROUTER_API_KEY"], config.model)
        laeufe = {}
        for name, (einheiten, kuerzbar, anteil) in plan.items():
            balken = st.progress(0.0, text=f"{name}: 0 Aufrufe")

            def fortschritt(i: int, n: int, balken=balken, name=name) -> None:
                balken.progress(i / n, text=f"{name}: {i} von {n} Aufrufen")

            lauf = scoring.run(einheiten, questions, client, text_typ=config.text_typ, budget=budget,
                               modus=name, kuerzbar=kuerzbar, anteil=anteil, progress=fortschritt)
            balken.empty()
            laeufe[name] = (lauf, scoring.aggregate(lauf, config, katalog))
        meta = results.meta(datei.name, data, seiten, config.model)
        st.session_state["ergebnis"] = results.build(meta, config, laeufe)

    ergebnis = st.session_state.get("ergebnis")
    if not ergebnis:
        st.stop()
    if all(l["aufrufe"] == 0 for l in ergebnis["laeufe"].values()):
        erste = next((f for l in ergebnis["laeufe"].values() for f in l["fehler"]), "unbekannt")
        st.error(f"Kein Aufruf erfolgreich. Erste Ursache: {erste}")
        st.stop()
    render_meta(ergebnis)
    render_results(ergebnis, config)
    stamm = Path(datei.name).stem
    links, rechts = st.columns(2)
    links.download_button("Ergebnis als JSON", results.to_json(ergebnis), file_name=f"{stamm}_jev.json",
                          mime="application/json")
    rechts.download_button("Extrahierter Text als TXT", text_gesamt, file_name=f"{stamm}.txt", mime="text/plain")


main()
```

- [ ] **Step 2: App starten und Health prüfen**

Run (Hintergrund, im Projektverzeichnis):
```bash
uv run --env-file .env streamlit run app.py --server.port 8501 --server.baseUrlPath jev_grading_demo > /tmp/jevdemo-streamlit.log 2>&1 &
sleep 4
curl -s http://localhost:8501/jev_grading_demo/_stcore/health; echo
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501/jev_grading_demo/
grep -iE "error|traceback" /tmp/jevdemo-streamlit.log || echo "log sauber"
```
Expected: `ok`, `200`, `log sauber`. `.env` muss dafür lokal `APP_PASSWORD=` mit einem Testwert enthalten (ergänzen, falls es fehlt; die Datei ist gitignored).

- [ ] **Step 3: App wieder stoppen**

Run: `pkill -f "streamlit run app.py"` 

- [ ] **Step 4: Commit**

```bash
git add app.py
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "app.py: Passwort-Gate, Upload, Modus, Schätzung, Lauf, Ergebnisse, Download

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: Browser-Abnahme und README

**Files:**
- Modify: `README.md` (Abschnitt "Nutzung", "Config", "Entwicklung" anhängen; der vorhandene Text bleibt)

**Interfaces:**
- Consumes: laufende App aus Task 12, Beispiel-PDF `manifesto/codebook_MPDataset_MPDS2026a.pdf` (32 Seiten, 57.133 Zeichen, also über dem Gesamttext-Limit mit Manifesto-Block: der Kürzungs-Hinweis muss erscheinen).

- [ ] **Step 1: App starten**

Run: `uv run --env-file .env streamlit run app.py --server.port 8501 --server.baseUrlPath jev_grading_demo > /tmp/jevdemo-streamlit.log 2>&1 &` und 4 s warten.

- [ ] **Step 2: Browser-Test mit dem Skill rodney-browser-testing**

Skill `rodney-browser-testing` laden und diese Prüfungen durchführen (die konkreten rodney-Kommandos stehen im Skill):
1. `http://localhost:8501/jev_grading_demo/` öffnen. Erwartet: Titel "Jev Grading Demo" und ein Passwortfeld, keine Upload-Zone.
2. Falsches Passwort eingeben, Enter. Erwartet: "Falsches Passwort".
3. Richtiges Passwort (aus `.env`) eingeben, Enter. Erwartet: Upload-Zone und Seitenleiste "Fragen" mit sechs aufklappbaren Blöcken (`manifesto (manifesto)`, `konkretheit (score)`, …).
4. `manifesto/codebook_MPDataset_MPDS2026a.pdf` in den Uploader laden. Erwartet: Metriken "Seiten 32", Zeichen-Zahl über 50.000, Warnung "Gesamttext-Modus: Es werden nur … % des Textes bewertet" (bei Modus Gesamttext).
5. Modus "Beide" wählen, Slider auf 1000, "Bewerten" klicken. Erwartet: Fortschrittsbalken, danach zwei Spalten "Gesamttext" und "Chunks (Mittelwert)" mit Manifesto-Balken, zwei Score-Balken, einer Choice-Kachel, zwei noul-Kacheln, Expander "Je Chunk (…)", zwei Download-Buttons. Screenshot nach `/tmp/jevdemo-ergebnis.png` und ansehen: keine überlappenden Labels, Balken lesbar.
6. In der Seitenleiste `finanzierung` aufklappen, "Frage löschen". Erwartet: Block verschwindet. "Frage hinzufügen" mit Name `eu` Typ `noul`, Instruction "Geht es um die EU?" eintragen. Erwartet: neuer Block `eu (noul)`, kein Validierungsfehler.
7. "Zurücksetzen auf config.yaml". Erwartet: wieder sechs Blöcke, `eu` weg, `finanzierung` da.
8. Bei `konkretheit` die Stufen bis auf eine Zeile löschen. Erwartet: roter Fehler "score braucht criteria als Liste mit mindestens 2 Stufen" und im Hauptbereich "Config ungültig". Stufen wieder ergänzen, Fehler verschwindet.

Findet sich ein Fehler, Ursache mit dem Skill superpowers:systematic-debugging klären, beheben, Test wiederholen, Fix als eigenen Commit.

- [ ] **Step 3: App stoppen**

Run: `pkill -f "streamlit run app.py"`

- [ ] **Step 4: README ergänzen**

An `README.md` anhängen:
````markdown

## Die Demo benutzen

1. Link öffnen, gemeinsames Passwort eingeben.
2. PDF in die Upload-Zone ziehen. Die App zeigt Seiten, Zeichen und geschätzte Token.
3. Modus wählen:
   - **Gesamttext**: ein Aufruf über den ganzen Text. Jev nimmt maximal rund 26.000 Token je Aufruf;
     längere Texte werden abgeschnitten, die App sagt, wie viel Prozent bewertet wurden.
   - **Chunks**: der Text wird in Stücke geteilt (Slider), jedes Stück einzeln bewertet, die Ergebnisse
     werden token-gewichtet gemittelt. Deckt den ganzen Text ab und ist beim Manifesto-Schema näher am
     Original-Verfahren (Kodierung kleiner Einheiten, dann Anteile).
   - **Beide**: nebeneinander.
4. "Bewerten". Ergebnisse: Manifesto-Anteile und Kennzahlen als Balken, Score-Leitern als Balken je Stufe,
   Choice und Noul als Farbfelder. Download als JSON (mit allen Rohantworten je Einheit) und der
   extrahierte Text als TXT.

## Fragen anpassen

Die Fragen stehen in `config.yaml` und lassen sich in der Seitenleiste je Block ändern, löschen oder
ergänzen; "Zurücksetzen" holt die Datei zurück, "Config als YAML herunterladen" sichert den Stand.
Die Datei auf dem Server wird nie verändert.

| Typ | Felder | Jev antwortet mit |
| --- | --- | --- |
| `noul` | `instructions` | Wert 0 bis 1: trifft die Aussage zu? |
| `choice` | `instructions`, `criteria` als Mapping Option → Beschreibung | Wahl, Wahrscheinlichkeiten, Confidence |
| `score` | `instructions`, `criteria` als geordnete Liste (Leiter), `skala: [min, max]` | Erwartete Stufe, Verteilung, Confidence; die App rechnet auf die Skala um |
| `manifesto` | `instructions`, `domains`, `kennzahlen` | Choice über die 57 Manifesto-Hauptkategorien; daraus Anteile, Domänen, rile, planeco, markeco, welfare, intpeace |

Die Frage schlägt den Instruction-Prompt: Jev bekommt jede Frage einzeln mit ihrer Instruction, der
Text geht als `state` mit dem `text_typ` aus der Config.

## Entwicklung

```bash
uv sync
cp .env.example .env        # OPENROUTER_API_KEY und APP_PASSWORD eintragen
uv run pytest               # ohne Netz
uv run --env-file .env pytest -m live   # ein echter Aufruf gegen OpenRouter
uv run --env-file .env streamlit run app.py --server.baseUrlPath jev_grading_demo
```

Deployment: siehe `docs/superpowers/specs/2026-09-22-jev-grading-demo-design.md`, Abschnitt 11.
````

- [ ] **Step 5: Commit**

```bash
git add README.md
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "README: Nutzung, Fragetypen, Entwicklung

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: Container: Dockerfile, compose.yaml, lokaler Lauf

**Files:**
- Create: `Dockerfile`, `compose.yaml`, `.dockerignore`

**Interfaces:**
- Consumes: `pyproject.toml`, `uv.lock`, `app.py`, `jevdemo/`, `config.yaml`, `manifesto/mp_v5.json`, `.streamlit/config.toml`.
- Produces: Image `jev_grading_demo`, Container hört auf 8501 unter `/jev_grading_demo/`, Healthcheck gegen `/jev_grading_demo/_stcore/health`.

- [ ] **Step 1: Dateien schreiben**

`.dockerignore`:
```
.venv
.git
.env
.env.*
!.env.example
__pycache__
*.pyc
.pytest_cache
tests
docs
results
manifesto/*.pdf
.DS_Store
.claude
```

`Dockerfile`:
```dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app.py config.yaml ./
COPY jevdemo ./jevdemo
COPY manifesto/mp_v5.json ./manifesto/mp_v5.json
COPY .streamlit ./.streamlit

RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD /app/.venv/bin/python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/jev_grading_demo/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["/app/.venv/bin/streamlit", "run", "app.py", \
     "--server.port", "8501", "--server.address", "0.0.0.0", \
     "--server.baseUrlPath", "jev_grading_demo", "--server.headless", "true"]
```

`compose.yaml`:
```yaml
services:
  jev_grading_demo:
    build: .
    image: jev_grading_demo:latest
    container_name: jev_grading_demo
    env_file: .env
    restart: unless-stopped
    networks:
      - caddy

networks:
  caddy:
    external: true
    name: weihnachtswunder-gps-tracker_default
```

- [ ] **Step 2: Lokal bauen und ohne compose starten** (das externe Netz gibt es nur auf dem Server)

```bash
docker build -t jev_grading_demo:latest .
docker run -d --rm --name jevdemo_test --env-file .env -p 8501:8501 jev_grading_demo:latest
sleep 6
curl -s http://localhost:8501/jev_grading_demo/_stcore/health; echo
docker inspect --format '{{.State.Health.Status}}' jevdemo_test
```
Expected: `ok` und nach spätestens 30 s `healthy` (bis dahin `starting`). Erneut prüfen mit `sleep 25; docker inspect --format '{{.State.Health.Status}}' jevdemo_test`.

- [ ] **Step 3: Passwort-Gate im Container prüfen und aufräumen**

```bash
curl -s http://localhost:8501/jev_grading_demo/ | grep -o "<title>[^<]*</title>"
docker stop jevdemo_test
```
Expected: ein `<title>`-Tag (Streamlit-Shell); die Gate-Logik wurde in Task 13 im Browser abgenommen.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile compose.yaml .dockerignore
git -c user.name="Jan Eggers" -c user.email="jan@eggers-elektronik.de" commit -m "Container: Dockerfile mit uv, compose am Caddy-Netz, Healthcheck

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 15: Deployment auf dem Weihnachtswunderserver

**Files:** keine im Repo. Server: `/home/jeggers/projects/jev_grading_demo/`.

**Interfaces:**
- Consumes: Image-Build aus Task 14, SSH `jeggers@34.159.146.213`, Netz `weihnachtswunder-gps-tracker_default` (existiert, gehört zum GPS-Tracker-Projekt).
- Produces: laufender, gesunder Container `jev_grading_demo` im Caddy-Netz. Noch keine öffentliche Route.

Jeder Schritt mit `sudo` wird Jan vorher als Block gezeigt und erst nach Freigabe ausgeführt (CLAUDE.md).

- [ ] **Step 1: Projekt hochladen (kein sudo)**

```bash
ssh jeggers@34.159.146.213 'mkdir -p ~/projects/jev_grading_demo'
rsync -az --delete --exclude .git --exclude .venv --exclude .env --exclude .pytest_cache \
      --exclude __pycache__ --exclude results --exclude 'manifesto/*.pdf' \
      /Users/janeggers/Code/WDR/jev_grading_demo/ jeggers@34.159.146.213:~/projects/jev_grading_demo/
ssh jeggers@34.159.146.213 'ls ~/projects/jev_grading_demo'
```
Expected: `Dockerfile app.py compose.yaml config.yaml jevdemo manifesto pyproject.toml uv.lock …`

- [ ] **Step 2: .env auf dem Server anlegen (kein sudo, aber Secrets: Jan fragen, welches APP_PASSWORD gelten soll)**

```bash
ssh jeggers@34.159.146.213 'umask 077; cat > ~/projects/jev_grading_demo/.env' <<'ENVEOF'
OPENROUTER_API_KEY=<Wert aus der lokalen .env>
APP_PASSWORD=<von Jan gewähltes Passwort>
ENVEOF
ssh jeggers@34.159.146.213 'ls -l ~/projects/jev_grading_demo/.env'
```
Expected: `-rw------- 1 jeggers jeggers`.

- [ ] **Step 3: Bauen und starten (sudo-Block, Freigabe einholen)**

```bash
ssh jeggers@34.159.146.213 'cd ~/projects/jev_grading_demo && sudo docker compose build && sudo docker compose up -d'
```
Expected: Build endet ohne Fehler, `Container jev_grading_demo Started`.

- [ ] **Step 4: Gesundheit prüfen (sudo-Block, Freigabe einholen)**

```bash
ssh jeggers@34.159.146.213 'sleep 25; sudo docker inspect --format "{{.State.Health.Status}}" jev_grading_demo; sudo docker logs --tail 20 jev_grading_demo'
```
Expected: `healthy`, im Log "You can now view your Streamlit app" ohne Traceback.

- [ ] **Step 5: Erreichbarkeit aus dem Caddy-Container prüfen (sudo-Block, Freigabe einholen)**

```bash
ssh jeggers@34.159.146.213 'sudo docker exec weihnachtswunder-gps-tracker-caddy-1 wget -qO- http://jev_grading_demo:8501/jev_grading_demo/_stcore/health'
```
Expected: `ok`. (Das Caddy-Image hat `wget`; fehlt es, stattdessen `sudo docker run --rm --network weihnachtswunder-gps-tracker_default curlimages/curl -s http://jev_grading_demo:8501/jev_grading_demo/_stcore/health`.)

---

### Task 16: Caddy-Route, öffentlicher Test, Server-README

**Files:** Server: `/home/wdr-docker-ssh/projects/weihnachtswunder-gps-tracker/deploy/Caddyfile` (fremd, produktiv), `/var/opt/README.md` (ohne sudo schreibbar).

**Interfaces:**
- Consumes: gesunder Container aus Task 15.
- Produces: `https://interaktive-projekte.de/jev_grading_demo/` liefert die App.

Die Caddyfile gehört zur laufenden Weihnachtswunder-Produktion. Reihenfolge: lesen, Backup, additiv einfügen, validieren, erst dann reload. Jeder sudo-Block einzeln freigeben.

- [ ] **Step 1: Caddyfile und Mount-Pfad lesen (sudo-Block, Freigabe einholen)**

```bash
ssh jeggers@34.159.146.213 'sudo cat /home/wdr-docker-ssh/projects/weihnachtswunder-gps-tracker/deploy/Caddyfile; echo ----; sudo docker inspect --format "{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}" weihnachtswunder-gps-tracker-caddy-1'
```
Expected: eine Site mit `@admin`, `@public` und einem Catch-all `handle {` … `reverse_proxy app:3000`; der Mount zeigt den Container-Pfad der Caddyfile (erwartet `/etc/caddy/Caddyfile`). Diesen Pfad in den nächsten Schritten verwenden.

- [ ] **Step 2: Backup und Einfügen vor dem Catch-all (sudo-Block, Freigabe einholen)**

```bash
ssh jeggers@34.159.146.213 'set -e
F=/home/wdr-docker-ssh/projects/weihnachtswunder-gps-tracker/deploy/Caddyfile
sudo cp "$F" "$F.bak-$(date +%Y%m%d-%H%M%S)"
sudo python3 - "$F" <<'"'"'PYEOF'"'"'
import re, sys
pfad = sys.argv[1]
text = open(pfad, encoding="utf-8").read()
if "jev_grading_demo" in text:
    print("Route ist schon drin"); sys.exit(0)
block = ("    @jev path /jev_grading_demo /jev_grading_demo/*\n"
         "    handle @jev {\n"
         "        reverse_proxy jev_grading_demo:8501\n"
         "    }\n\n")
# vor dem ersten Catch-all "handle {" ohne Matcher einfügen
treffer = re.search(r"^[ \t]*handle[ \t]*\{", text, re.M)
if not treffer:
    print("kein Catch-all handle { gefunden, nichts geändert"); sys.exit(1)
neu = text[:treffer.start()] + block + text[treffer.start():]
open(pfad, "w", encoding="utf-8").write(neu)
print("eingefügt")
PYEOF
sudo cat "$F"'
```
Expected: `eingefügt`, und in der Ausgabe steht der `@jev`-Block direkt vor dem Catch-all, mit derselben Einrückung wie die Nachbarn (bei Bedarf Einrückung im Block anpassen, Caddy ist da tolerant).

- [ ] **Step 3: Validieren und neu laden (sudo-Block, Freigabe einholen)**

```bash
ssh jeggers@34.159.146.213 'sudo docker exec weihnachtswunder-gps-tracker-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo docker exec weihnachtswunder-gps-tracker-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile'
```
Expected: `Valid configuration` und ein Reload ohne Fehler. Schlägt `validate` fehl: Backup zurückkopieren (`sudo cp "$F.bak-…" "$F"`), NICHT reloaden, Ursache klären.

- [ ] **Step 4: Öffentlich prüfen (kein sudo)**

```bash
curl -s https://interaktive-projekte.de/jev_grading_demo/_stcore/health; echo
curl -s -o /dev/null -w "%{http_code}\n" https://interaktive-projekte.de/jev_grading_demo/
curl -s -o /dev/null -w "%{http_code}\n" https://interaktive-projekte.de/
```
Expected: `ok`, `200`, `200` (die GPS-Tracker-Seite antwortet weiter).

- [ ] **Step 5: Browser-Test über die öffentliche URL** (Skill rodney-browser-testing): Seite öffnen, Passwort eingeben, kleines PDF hochladen, Modus Chunks, "Bewerten". Erwartet: Ergebnisse erscheinen. Damit ist auch der WebSocket durch Caddy bestätigt (ohne ihn bliebe die Seite nach dem Passwort hängen). Bleibt sie hängen: Caddy-Log lesen (`sudo docker logs --tail 50 weihnachtswunder-gps-tracker-caddy-1`, sudo-Block) und Streamlit-Log; Caddy 2 reicht WebSockets über `reverse_proxy` ohne Zusatzkonfiguration durch, ein Hänger deutet eher auf `baseUrlPath` oder den Matcher.

- [ ] **Step 6: Server-README ergänzen (kein sudo)**

```bash
ssh jeggers@34.159.146.213 'cat >> /var/opt/README.md' <<'MDEOF'

## jev_grading_demo (seit 2026-09)

- Zweck: Demo, PDF hochladen und mit Jev (TypeSafe, über OpenRouter) bewerten. Passwortgeschützt.
- Pfad: /home/jeggers/projects/jev_grading_demo (compose-Projekt, Container `jev_grading_demo`, Port 8501 intern).
- Netz: hängt am `weihnachtswunder-gps-tracker_default`, Route in der Caddyfile des GPS-Trackers:
  `@jev path /jev_grading_demo /jev_grading_demo/*` -> `reverse_proxy jev_grading_demo:8501`.
- URL: https://interaktive-projekte.de/jev_grading_demo/
- Secrets: `.env` im Projektpfad (OPENROUTER_API_KEY, APP_PASSWORD), nur für jeggers lesbar.
- Update: rsync ins Projektverzeichnis, dann `sudo docker compose build && sudo docker compose up -d`.
- Ansprechpartner: Jan Eggers.
MDEOF
ssh jeggers@34.159.146.213 'tail -12 /var/opt/README.md'
```
Expected: der Abschnitt steht am Ende der Datei.

---

## Self-Review (durchgeführt beim Schreiben des Plans)

**Spec-Abdeckung:** Spec 4 Architektur → Tasks 1–12; Spec 5.1 config → Task 3; 5.2 manifesto → Task 2; 5.3 pdf_text → Task 4; 5.4 chunking → Task 5; 5.5 jev_client → Task 6; 5.6 scoring → Tasks 7–8; 5.7 results → Task 9; 5.8 UI → Tasks 10–12; Spec 6 Default-Config → Task 3; Spec 7 UI-Verhalten → Tasks 11–13; Spec 8 Fehlerbehandlung → Tasks 4, 6, 7, 12; Spec 9 Sicherheit → Tasks 12 (Gate, compare_digest), 14 (Non-Root, kein Host-Port); Spec 10 Tests → jede Task; Spec 11 Deployment → Tasks 14–16. Nicht im Plan, weil außerhalb des Umfangs (Spec 12): OCR, Mehrfach-Upload, Persistenz.

**Abweichungen von der Spec, bewusst:** `manifesto.domaenen` und `manifesto.top` bekommen den Katalog als Parameter (Spec nannte ihn nicht); `scoring.run` nimmt `text_typ`, `budget`, `modus` als Keyword-Argumente statt einer Config (weniger Kopplung); `Lauf.modell` ergänzt, damit das JSON das tatsächlich antwortende Modell trägt; `Frage.skala` ist eine Liste, kein Tupel (YAML-Roundtrip).

**Typ-Konsistenz geprüft:** `Einheit(index, text, seite_von, seite_bis, tokens)` überall gleich; `EinheitErgebnis.antworten: dict[str, dict]`; `aggregate(lauf, config, katalog)` in Task 8 und app.py; `render_results(ergebnis, config)` in Task 10 und 12; `render_editor(config, katalog)` in Task 11 und 12; `whole_text` liefert `(Einheit, float)`, in `_plan` so entpackt; `JevClient(api_key, model)` positional in app.py entspricht der Signatur aus Task 6.
