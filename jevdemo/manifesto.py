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
