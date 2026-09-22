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
