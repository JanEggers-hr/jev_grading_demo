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
    """Gesamttext: Gruppen nacheinander. Bei ZuLang kürzen und alle Gruppen neu, damit jede Antwort denselben Text meint. Beliebige Fehler werden gesammelt."""
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
        except Exception as e:
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
