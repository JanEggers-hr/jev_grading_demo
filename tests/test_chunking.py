import pytest

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


def test_whole_text_ohne_seiten_wirft():
    with pytest.raises(ValueError):
        chunking.whole_text([], max_tokens=100)


def test_absatz_ohne_satzzeichen_wird_an_wortgrenzen_geteilt():
    text = ("Wortsalat ohne Satzzeichen " * 200).strip()
    chunks = chunking.chunk_pages([Seite(1, text)], chunk_tokens=100)
    assert len(chunks) > 1
    assert all(c.tokens <= 100 for c in chunks)
    assert "".join("".join(c.text.split()) for c in chunks) == "".join(text.split())
