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
