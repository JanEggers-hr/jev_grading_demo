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
                fehler.append(p + "choice braucht criteria als Mapping Option -> Beschreibung "
                                  "mit mindestens 2 Optionen")
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


def durchnummeriert(criteria: list[str] | dict[str, str]) -> list[str] | dict[str, str]:
    """Jede Zeile mit '1. ', '2. ', ... voranstellen (score: Liste, choice: Mapping-Keys);
    hilft Jev, die Reihenfolge/Zuordnung der Kriterien eindeutig zu erkennen."""
    if isinstance(criteria, list):
        return [f"{i}. {c}" for i, c in enumerate(criteria, start=1)]
    return {f"{i}. {k}": v for i, (k, v) in enumerate(criteria.items(), start=1)}


def to_questions(config: Config, katalog: list[manifesto.Kategorie]) -> dict[str, dict]:
    """Aktive Fragen im Jev-Format, Reihenfolge wie in der Config."""
    out: dict[str, dict] = {}
    for f in aktive(config):
        if f.type == "manifesto":
            out[f.name] = manifesto.build_question(f.instructions, f.domains or [], katalog)
        elif f.type == "noul":
            out[f.name] = {"type": "noul", "instructions": f.instructions}
        else:
            out[f.name] = {"type": f.type, "instructions": f.instructions,
                            "criteria": durchnummeriert(f.criteria)}
    return out
