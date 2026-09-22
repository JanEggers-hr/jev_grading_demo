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
    data = _pdf(["Nord-\nRhein bleibt getrennt, weil danach ein Großbuchstabe steht."])
    assert pdf_text.extract_pages(data)[0].text == "Nord- Rhein bleibt getrennt, weil danach ein Großbuchstabe steht."


def test_leeres_pdf_wirft_keintext():
    with pytest.raises(pdf_text.KeinText):
        pdf_text.extract_pages(_pdf([]))


def test_muell_wirft_pdffehler():
    with pytest.raises(pdf_text.PdfFehler):
        pdf_text.extract_pages(b"das ist kein pdf")
