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


def _wortgruppen(text: str, chunk_tokens: int) -> list[str]:
    """Harte Teilung an Wortgrenzen für Stücke ohne Satzzeichen."""
    gruppen: list[str] = []
    aktuell = ""
    for wort in text.split():
        kandidat = f"{aktuell} {wort}".strip()
        if aktuell and estimate_tokens(kandidat) > chunk_tokens:
            gruppen.append(aktuell)
            aktuell = wort
        else:
            aktuell = kandidat
    if aktuell:
        gruppen.append(aktuell)
    return gruppen


def _stuecke(absatz: str, chunk_tokens: int) -> list[str]:
    """Absatz, falls zu lang, in Satzgruppen bis chunk_tokens; Sätze ohne Satzzeichen an Wortgrenzen."""
    if estimate_tokens(absatz) <= chunk_tokens:
        return [absatz]
    stuecke: list[str] = []
    aktuell = ""
    for satz in (s for s in _SATZENDE.split(absatz) if s):
        if estimate_tokens(satz) > chunk_tokens:
            if aktuell:
                stuecke.append(aktuell)
                aktuell = ""
            stuecke.extend(_wortgruppen(satz, chunk_tokens))
            continue
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
    if not pages:
        raise ValueError("whole_text braucht mindestens eine Seite")
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
