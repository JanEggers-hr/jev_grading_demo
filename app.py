"""Jev Grading Demo: PDF hochladen, Fragen anpassen, mit Jev bewerten lassen."""

import hashlib
import os
from pathlib import Path

import streamlit as st

from jevdemo import auth, chunking, manifesto, pdf_text, results, scoring
from jevdemo import config as cfg
from jevdemo.env import lade_env
from jevdemo.jev_client import JevClient
from jevdemo.ui.editor import render_editor
from jevdemo.ui.views import punkt, render_meta, render_results

ROOT = Path(__file__).resolve().parent
lade_env(ROOT / ".env")

st.set_page_config(page_title="Jev Grading Demo", page_icon="📄", layout="wide")


# Caches begrenzt: PDF-Texte liegen sessionübergreifend im RAM, der Host hat keinen Swap (ADR-001)
@st.cache_data(show_spinner="PDF wird gelesen …", max_entries=16, ttl=3600)
def _seiten(data: bytes) -> list[pdf_text.Seite]:
    return pdf_text.extract_pages(data)


@st.cache_resource
def _katalog() -> list[manifesto.Kategorie]:
    return manifesto.load_catalog()


@st.cache_data(show_spinner=False, max_entries=64, ttl=3600)
def _chunks(seiten: list[pdf_text.Seite], chunk_tokens: int) -> list[chunking.Einheit]:
    return chunking.chunk_pages(seiten, chunk_tokens)


@st.cache_data(show_spinner=False, max_entries=64, ttl=3600)
def _gesamttext(seiten: list[pdf_text.Seite], max_tokens: int) -> tuple[chunking.Einheit, float]:
    return chunking.whole_text(seiten, max_tokens)


def _plan(seiten, chunks: list[chunking.Einheit], modus: str, questions: dict, budget: int) -> dict:
    """Modusname -> (Einheiten, kuerzbar, Anteil)."""
    plan = {}
    if modus in ("Gesamttext", "Beide"):
        einheit, anteil = _gesamttext(seiten, scoring.text_budget(questions, budget))
        plan["gesamttext"] = ([einheit], True, anteil)
    if modus in ("Chunks", "Beide"):
        plan["chunks"] = (chunks, False, 1.0)
    return plan


def main() -> None:
    auth.gate()
    katalog = _katalog()
    if "config" not in st.session_state:
        try:
            st.session_state["config"] = cfg.load()
        except cfg.ConfigError as e:
            st.error(f"config.yaml lässt sich nicht laden: {e}")
            st.stop()
    with st.sidebar:
        config = render_editor(st.session_state["config"], katalog)
        fehler = cfg.validate(config)
        if fehler:
            st.error("Config ungültig:\n\n- " + "\n- ".join(fehler))

    st.title("Jev Grading Demo")
    st.caption("PDF hochladen, Fragen links anpassen, bewerten lassen. Jev 1.13 über OpenRouter.")
    datei = st.file_uploader("PDF hierher ziehen oder auswählen", type=["pdf"])
    if datei is None:
        st.session_state.pop("ergebnis", None)
        st.session_state.pop("ergebnis_json", None)
        st.session_state.pop("datei_sha", None)
        st.info("Noch kein PDF.")
        st.stop()

    data = datei.getvalue()
    sha = hashlib.sha256(data).hexdigest()
    if st.session_state.get("datei_sha") != sha:
        st.session_state["datei_sha"] = sha
        st.session_state.pop("ergebnis", None)
        st.session_state.pop("ergebnis_json", None)
    try:
        seiten = _seiten(data)
    except pdf_text.KeinText as e:
        st.warning(str(e))
        st.stop()
    except pdf_text.PdfFehler as e:
        st.error(str(e))
        st.stop()

    text_gesamt = "\n\n".join(s.text for s in seiten)
    tokens_gesamt = chunking.estimate_tokens(text_gesamt)
    modus = st.radio("Modus", ["Chunks", "Gesamttext", "Beide"], horizontal=True)
    chunk_tokens = st.slider("Chunk-Größe in Token (geschätzt)", 300, 3000,
                             min(3000, max(300, config.chunk_tokens)), 100)
    config.chunk_tokens = chunk_tokens
    chunks = _chunks(seiten, chunk_tokens)
    seiten_je_chunk = len(seiten) / len(chunks) if chunks else 0.0
    st.caption(f"Ein Chunk entspricht bei {chunk_tokens} Token etwa "
               f"{f'{seiten_je_chunk:.1f}'.replace('.', ',')} Seiten dieses PDFs ({len(chunks)} Chunks).")

    spalten = st.columns(4)
    spalten[0].metric("Seiten", len(seiten))
    spalten[1].metric("Zeichen", punkt(len(text_gesamt)))
    spalten[2].metric("Token (geschätzt)", punkt(tokens_gesamt))
    spalten[3].metric("Chunks bei dieser Größe", len(chunks))
    with st.expander("Textvorschau (erste 3.000 Zeichen)"):
        st.text(text_gesamt[:3000])

    if fehler:
        st.error("Config ungültig, siehe Seitenleiste.")
        st.stop()
    questions = cfg.to_questions(config, katalog)
    if not questions:
        st.warning("Keine aktive Frage.")
        st.stop()

    budget = config.budget_tokens
    plan = _plan(seiten, chunks, modus, questions, budget)
    schaetz = [scoring.schaetzung(einheiten, questions, budget) for einheiten, _, _ in plan.values()]
    aufrufe = sum(s["aufrufe"] for s in schaetz)
    tokens = sum(s["input_tokens"] for s in schaetz)
    kosten = sum(s["kosten_usd"] for s in schaetz)
    sekunden = sum(s["sekunden"] for s in schaetz)
    st.caption(f"Schätzung: {aufrufe} Aufrufe, {punkt(tokens)} Token, {kosten:.4f} USD, etwa {sekunden:.0f} s")
    if "gesamttext" in plan and plan["gesamttext"][2] < 1:
        st.warning(f"Gesamttext-Modus: Es werden nur {plan['gesamttext'][2]:.0%} des Textes bewertet "
                   f"(Limit {punkt(scoring.text_budget(questions, budget))} Token je Aufruf). "
                   f"Der Chunk-Modus deckt den ganzen Text ab.")

    if st.button("Bewerten", type="primary"):
        client = JevClient(os.environ["OPENROUTER_API_KEY"], config.model)
        laeufe = {}
        for name, (einheiten, kuerzbar, anteil) in plan.items():
            balken = st.progress(0.0, text=f"{name}: 0 Aufrufe")

            def fortschritt(i: int, n: int, balken=balken, name=name) -> None:
                balken.progress(i / n, text=f"{name}: {i} von {n} Aufrufen")

            lauf = scoring.run(einheiten, questions, client, text_typ=config.text_typ, budget=budget,
                               modus=name, kuerzbar=kuerzbar, anteil=anteil, progress=fortschritt)
            balken.empty()
            laeufe[name] = (lauf, scoring.aggregate(lauf, config, katalog))
        meta = results.meta(datei.name, data, seiten, config.model)
        st.session_state["ergebnis"] = results.build(meta, config, laeufe)
        st.session_state["ergebnis_json"] = results.to_json(st.session_state["ergebnis"])

    ergebnis = st.session_state.get("ergebnis")
    if not ergebnis:
        st.stop()
    if all(eintrag["aufrufe"] == 0 for eintrag in ergebnis["laeufe"].values()):
        erste = next((f for eintrag in ergebnis["laeufe"].values() for f in eintrag["fehler"]), "unbekannt")
        st.error(f"Kein Aufruf erfolgreich. Erste Ursache: {erste}")
        st.stop()
    render_meta(ergebnis)
    render_results(ergebnis, cfg.from_dict(ergebnis["config"]))
    stamm = Path(datei.name).stem
    links, rechts = st.columns(2)
    links.download_button("Ergebnis als JSON", st.session_state["ergebnis_json"], file_name=f"{stamm}_jev.json",
                          mime="application/json")
    rechts.download_button("Extrahierter Text als TXT", text_gesamt, file_name=f"{stamm}.txt", mime="text/plain")


main()
