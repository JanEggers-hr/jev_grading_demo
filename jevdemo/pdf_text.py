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
    if sum(len(s.text) for s in seiten) == 0:
        raise KeinText("Das PDF enthält keine Textebene (Scan?). OCR wird nicht unterstützt.")
    return seiten
