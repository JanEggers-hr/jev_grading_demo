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
