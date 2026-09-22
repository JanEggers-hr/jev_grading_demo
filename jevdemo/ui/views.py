"""Darstellung der Ergebnisse: Kacheln für noul/choice, Balken für score und Manifesto.

Farben aus der dataviz-Referenzpalette (Light). Kategoriale Slots in fester Reihenfolge,
eine Farbe je Entität (Option, Domäne); Magnitude in einem Blau; Polarität rot↔blau mit
neutraler Mitte. Text auf Kacheln nach Luminanz dunkel oder hell.
"""

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from jevdemo import config as cfg
from jevdemo import manifesto

KATEGORIAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SONSTIGE = "#9a9892"
BLAU, ROT, MITTE = "#2a78d6", "#e34948", "#f0efec"
TEXT_DUNKEL, TEXT_HELL = "#0b0b0b", "#ffffff"
MODUS_TITEL = {"gesamttext": "Gesamttext", "chunks": "Chunks (Mittelwert)"}
KENNZAHL_HILFE = {
    "rile": "Rechts-links-Position nach Laver/Budge: Summe rechter minus Summe linker Kategorien, in Prozentpunkten. "
            "Im Gesamttext-Modus ist das die Verteilung einer einzigen Entscheidung, im Chunk-Modus der "
            "token-gewichtete Mittelwert vieler Entscheidungen (näher am Manifesto-Verfahren).",
    "planeco": "Planwirtschaft: 403 Marktregulierung + 404 Wirtschaftsplanung + 412 gelenkte Wirtschaft.",
    "markeco": "Marktwirtschaft: 401 freier Markt + 414 wirtschaftliche Orthodoxie.",
    "welfare": "Wohlfahrt: 503 Gleichheit + 504 Ausbau des Sozialstaats.",
    "intpeace": "Internationaler Frieden: 102 besondere Beziehungen negativ + 105 Militär negativ + 106 Frieden.",
}

KENNZAHL_KURZ = {
    "rile": "Rechts-links, -100 links bis +100 rechts",
    "planeco": "Planwirtschaft",
    "markeco": "Marktwirtschaft",
    "welfare": "Wohlfahrt",
    "intpeace": "Internationaler Frieden",
}


def _rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def mische(a: str, b: str, t: float) -> str:
    """Linear zwischen zwei Hex-Farben, t = 0 → a, t = 1 → b."""
    return _hex(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b)))


def noul_farbe(wert: float) -> str:
    """0 → rot (nein), 0.5 → neutral, 1 → blau (ja)."""
    wert = max(0.0, min(1.0, wert))
    if wert <= 0.5:
        return mische(ROT, MITTE, wert * 2)
    return mische(MITTE, BLAU, (wert - 0.5) * 2)


def textfarbe(hintergrund: str) -> str:
    """Dunkler Text auf hellen Flächen, heller auf dunklen (relative Luminanz nach sRGB)."""

    def lin(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in _rgb(hintergrund))
    return TEXT_DUNKEL if 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 else TEXT_HELL


def optionsfarbe(index: int) -> str:
    return KATEGORIAL[index] if 0 <= index < len(KATEGORIAL) else SONSTIGE


def kurz(text: str, n: int = 48) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def punkt(zahl: int) -> str:
    """Ganze Zahl mit Tausenderpunkt, z. B. 8234 -> '8.234'."""
    return f"{zahl:,}".replace(",", ".")


def kachel(titel: str, text: str, farbe: str, untertitel: str = "") -> None:
    ink = textfarbe(farbe)
    unten = f'<div style="font-size:0.85rem;opacity:0.85">{html.escape(untertitel)}</div>' if untertitel else ""
    st.markdown(
        f'<div style="background:{farbe};color:{ink};padding:14px 18px;border-radius:8px;margin:4px 0 12px 0">'
        f'<div style="font-size:0.85rem;opacity:0.85">{html.escape(titel)}</div>'
        f'<div style="font-size:1.5rem;font-weight:600">{html.escape(text)}</div>{unten}</div>',
        unsafe_allow_html=True,
    )


def balken(labels: list[str], werte: list[float], farben, x_titel: str, hoehe: int | None = None) -> go.Figure:
    """Horizontale Balken, dünn, mit Wert außen; eine Farbe (str) oder eine Liste je Balken."""
    fig = go.Figure(go.Bar(
        x=werte, y=labels, orientation="h",
        marker=dict(color=farben, line=dict(width=0)),
        text=[f"{v:.1f}" for v in werte], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        height=hoehe or max(160, 26 * len(labels) + 70),
        margin=dict(l=10, r=40, t=10, b=30),
        yaxis=dict(autorange="reversed", tickfont=dict(size=12)),
        xaxis=dict(title=x_titel, showgrid=True, gridcolor="#eeeeee", zeroline=False),
        plot_bgcolor="white", paper_bgcolor="white", showlegend=False, bargap=0.25,
    )
    return fig


def rile_balken(wert: float) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=[wert], y=["rile"], orientation="h",
        marker=dict(color=BLAU if wert >= 0 else ROT, line=dict(width=0)),
        hovertemplate="rile: %{x:.1f}<extra></extra>",
    ))
    fig.update_layout(
        height=110, margin=dict(l=10, r=10, t=10, b=30),
        xaxis=dict(range=[-100, 100], zeroline=True, zerolinecolor="#888888", title="links  ←  rile  →  rechts"),
        yaxis=dict(showticklabels=False), plot_bgcolor="white", paper_bgcolor="white", bargap=0.4,
    )
    return fig


def kennzahlen_tabelle(kennzahlen: dict[str, float]) -> str:
    """Kompakte HTML-Tabelle: Kennzahl, Wert, Kurzbezeichnung; Erklärung als Tooltip."""
    zeilen = "".join(
        f'<tr title="{html.escape(KENNZAHL_HILFE.get(name, ""))}">'
        f'<td style="padding:2px 10px 2px 0;font-weight:600">{html.escape(name)}</td>'
        f'<td style="padding:2px 10px;text-align:right;font-variant-numeric:tabular-nums">{wert:.1f}</td>'
        f'<td style="padding:2px 0;color:#52514e">{html.escape(KENNZAHL_KURZ.get(name, ""))}</td></tr>'
        for name, wert in kennzahlen.items()
    )
    return f'<table style="font-size:0.85rem;border-collapse:collapse;margin:4px 0 8px 0">{zeilen}</table>'


def render_meta(ergebnis: dict) -> None:
    teile = []
    for name, lauf in ergebnis["laeufe"].items():
        text = (f"{MODUS_TITEL.get(name, name)}: {lauf['einheiten']} Einheiten, "
                f"{lauf['anteil_bewertet']:.0%} des Textes, {lauf['aufrufe']} Aufrufe, "
                f"{punkt(lauf['input_tokens'])} Token, {lauf['kosten_usd']:.4f} USD, {lauf['sekunden']:.1f} s")
        if lauf["fehler"]:
            text += f", {len(lauf['fehler'])} Fehler"
        teile.append(text)
    modell = next((l["modell"] for l in ergebnis["laeufe"].values() if l.get("modell")), ergebnis["meta"]["modell"])
    st.caption(f"Modell {modell} · " + " · ".join(teile))


def _noul_block(frage: cfg.Frage, agg: dict) -> None:
    kachel(frage.instructions, f"{agg['noul']:.2f}", noul_farbe(agg["noul"]), f"0 = nein, 1 = ja · n = {agg['n']}")


def _choice_block(frage: cfg.Frage, agg: dict, key: str) -> None:
    optionen = list(frage.criteria)
    farbe = optionsfarbe(optionen.index(agg["choice"])) if agg["choice"] in optionen else SONSTIGE
    kachel(frage.instructions, agg["choice"], farbe, f"Confidence {agg['confidence']:.2f} · n = {agg['n']}")
    top5 = sorted(agg["probabilities"].items(), key=lambda kv: -kv[1])[:5]
    farben = [optionsfarbe(optionen.index(o)) if o in optionen else SONSTIGE for o, _ in top5]
    fig = balken([kurz(o) for o, _ in top5], [p * 100 for _, p in top5], farben, "Wahrscheinlichkeit in %")
    st.plotly_chart(fig, width="stretch", key=key)


def _score_block(frage: cfg.Frage, agg: dict, key: str) -> None:
    unten, oben = frage.skala
    st.markdown(f"**{frage.instructions}**  \n"
                f"{agg['wert']:.2f} auf der Skala {unten} bis {oben} · Confidence {agg['confidence']:.2f} · n = {agg['n']}")
    labels = [f"{i}: {kurz(s, 60)}" for i, s in enumerate(frage.criteria)]
    werte = [agg["probabilities"].get(str(i), 0.0) * 100 for i in range(len(frage.criteria))]
    st.plotly_chart(balken(labels, werte, BLAU, "Wahrscheinlichkeit je Stufe in %"), width="stretch", key=key)


def _manifesto_block(frage: cfg.Frage, agg: dict, key: str) -> None:
    st.markdown(f"**Manifesto-Kategorien** · Confidence {agg['confidence']:.2f} · n = {agg['n']}")
    top = agg["top"][:10]
    fig = balken([f"{code} {kurz(title, 40)}" for code, title, _ in top], [p for *_, p in top], BLAU, "Anteil in %")
    st.plotly_chart(fig, width="stretch", key=f"{key}_top")
    dom = [(code, manifesto.DOMAENEN[code], p) for code, p in agg["domaenen"].items() if code != "0" or p > 0]
    fig = balken([f"{c} {n}" for c, n, _ in dom], [p for *_, p in dom],
                 [optionsfarbe(int(c)) for c, *_ in dom], "Anteil je Domäne in %")
    st.plotly_chart(fig, width="stretch", key=f"{key}_dom")
    kennzahlen = agg.get("kennzahlen", {})
    if kennzahlen:
        st.markdown(kennzahlen_tabelle(kennzahlen), unsafe_allow_html=True)
        if "rile" in kennzahlen:
            st.plotly_chart(rile_balken(kennzahlen["rile"]), width="stretch", key=f"{key}_rile")


def _chunk_tabelle(lauf: dict, config: cfg.Config) -> None:
    zeilen = []
    for d in lauf["einheiten_detail"]:
        zeile: dict = {"Chunk": d["index"], "Seiten": f"{d['seite_von']}–{d['seite_bis']}", "Token": d["tokens"]}
        for frage in cfg.aktive(config):
            a = d["antworten"].get(frage.name)
            if a is None:
                zeile[frage.name] = None
            elif frage.type == "noul":
                zeile[frage.name] = round(a["noul"], 2)
            elif frage.type == "score":
                unten, oben = frage.skala
                zeile[frage.name] = round(unten + a["score"] * (oben - unten) / (len(frage.criteria) - 1), 2)
            else:
                zeile[frage.name] = a["choice"]
        zeile["Fehler"] = "; ".join(d["fehler"]) if d["fehler"] else ""
        zeilen.append(zeile)
    with st.expander(f"Je Chunk ({len(zeilen)})"):
        st.dataframe(pd.DataFrame(zeilen), width="stretch", hide_index=True)


def render_results(ergebnis: dict, config: cfg.Config) -> None:
    laeufe = ergebnis["laeufe"]
    spalten = st.columns(len(laeufe))
    for spalte, (name, lauf) in zip(spalten, laeufe.items()):
        with spalte:
            st.subheader(MODUS_TITEL.get(name, name))
            if lauf["fehler"]:
                with st.expander(f"{len(lauf['fehler'])} Fehler"):
                    st.text("\n".join(lauf["fehler"]))
            for frage in cfg.aktive(config):
                agg = lauf["aggregat"].get(frage.name)
                key = f"{name}_{frage.name}"
                if not agg or agg.get("n", 0) == 0:
                    st.warning(f"{frage.name}: keine Antwort")
                elif frage.type == "noul":
                    _noul_block(frage, agg)
                elif frage.type == "choice":
                    _choice_block(frage, agg, key)
                elif frage.type == "score":
                    _score_block(frage, agg, key)
                else:
                    _manifesto_block(frage, agg, key)
            if name == "chunks":
                _chunk_tabelle(lauf, config)
