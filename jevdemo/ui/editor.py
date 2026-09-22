"""Formular pro Frage in der Seitenleiste. Die Config lebt in st.session_state["config"];
config.yaml auf der Platte wird nie beschrieben. Der data_editor für Choice-Optionen erhält
einen festen Quell-Frame, sodass Streamlits Edit-Delta auf derselben Basis bei jedem Rerun angewendet wird."""

import pandas as pd
import streamlit as st

from jevdemo import config as cfg
from jevdemo import manifesto

PREFIX = "q__"
TYPEN = ["noul", "choice", "score"]
DOMAENEN_OPTIONEN = [f"{code} {name}" for code, name in manifesto.DOMAENEN.items() if code != "0"]


def _key(name: str, feld: str) -> str:
    return f"{PREFIX}{name}__{feld}"


def _startwerte(typ: str) -> dict:
    """criteria/skala beim Anlegen oder Typwechsel."""
    if typ == "score":
        return {"criteria": ["Stufe 1", "Stufe 2", "Stufe 3"], "skala": [1, 5]}
    if typ == "choice":
        return {"criteria": {"Option A": "", "Option B": ""}, "skala": None}
    return {"criteria": None, "skala": None}


def _widget_keys_loeschen(name: str | None = None) -> None:
    praefixe = (f"{PREFIX}{name}__",) if name else (PREFIX, "cfg__")
    for key in list(st.session_state):
        if key.startswith(praefixe):
            del st.session_state[key]


def _frage(name: str) -> cfg.Frage:
    return next(f for f in st.session_state["config"].fragen if f.name == name)


def _typ_geaendert(name: str) -> None:
    frage = _frage(name)
    frage.type = st.session_state[_key(name, "type")]
    for feld, wert in _startwerte(frage.type).items():
        setattr(frage, feld, wert)
    for feld in ("criteria", "criteria_quelle", "skala_min", "skala_max"):
        st.session_state.pop(_key(name, feld), None)


def _loeschen(name: str) -> None:
    config = st.session_state["config"]
    config.fragen = [f for f in config.fragen if f.name != name]
    _widget_keys_loeschen(name)


def _hinzufuegen() -> None:
    name = st.session_state.get("neu__name", "").strip()
    typ = st.session_state.get("neu__type", "noul")
    config = st.session_state["config"]
    if not cfg.SLUG.match(name):
        st.session_state["neu__fehler"] = "Name darf nur a-z, 0-9 und _ enthalten"
        return
    if any(f.name == name for f in config.fragen):
        st.session_state["neu__fehler"] = f"'{name}' gibt es schon"
        return
    config.fragen.append(cfg.Frage(name=name, type=typ, instructions="", **_startwerte(typ)))
    st.session_state["neu__name"] = ""
    st.session_state.pop("neu__fehler", None)


def _reset() -> None:
    _widget_keys_loeschen()
    try:
        st.session_state["config"] = cfg.load()
    except cfg.ConfigError as e:
        st.session_state["cfg__fehler"] = f"config.yaml lässt sich nicht laden: {e}"


def _zahl(x: float) -> float | int:
    return int(x) if float(x).is_integer() else float(x)


def _frage_block(frage: cfg.Frage) -> None:
    name = frage.name
    frage.aktiv = st.toggle("Aktiv", value=frage.aktiv, key=_key(name, "aktiv"))
    st.selectbox("Typ", TYPEN, index=TYPEN.index(frage.type), key=_key(name, "type"),
                 on_change=_typ_geaendert, args=(name,))
    frage.instructions = st.text_area("Instruction", value=frage.instructions, key=_key(name, "instructions"), height=100)
    if frage.type == "score":
        stufen_alt = frage.criteria if isinstance(frage.criteria, list) else []
        stufen = st.text_area("Stufen, eine je Zeile, von niedrig nach hoch",
                              value="\n".join(str(s) for s in stufen_alt), key=_key(name, "criteria"), height=160)
        frage.criteria = [z.strip() for z in stufen.splitlines() if z.strip()]
        skala = list(frage.skala or [])[:2]
        if len(skala) != 2 or not all(isinstance(x, (int, float)) for x in skala):
            skala = [1, 5]
        links, rechts = st.columns(2)
        unten = links.number_input("Skala min", value=float(skala[0]), key=_key(name, "skala_min"))
        oben = rechts.number_input("Skala max", value=float(skala[1]), key=_key(name, "skala_max"))
        frage.skala = [_zahl(unten), _zahl(oben)]
    elif frage.type == "choice":
        quelle_key = _key(name, "criteria_quelle")
        if quelle_key not in st.session_state:
            criteria = frage.criteria if isinstance(frage.criteria, dict) else {}
            st.session_state[quelle_key] = pd.DataFrame(
                {"Option": list(criteria), "Beschreibung": list(criteria.values())}, dtype="string"
            )
        bearbeitet = st.data_editor(st.session_state[quelle_key], num_rows="dynamic", key=_key(name, "criteria"),
                                    width="stretch", hide_index=True)
        frage.criteria = {
            str(o).strip(): ("" if pd.isna(b) else str(b).strip())
            for o, b in zip(bearbeitet["Option"], bearbeitet["Beschreibung"])
            if not pd.isna(o) and str(o).strip()
        }
    st.button("Frage löschen", key=_key(name, "loeschen"), on_click=_loeschen, args=(name,))


def _manifesto_block(frage: cfg.Frage, katalog: list[manifesto.Kategorie]) -> None:
    name = frage.name
    frage.aktiv = st.toggle("Aktiv", value=frage.aktiv, key=_key(name, "aktiv"))
    frage.instructions = st.text_area("Instruction", value=frage.instructions, key=_key(name, "instructions"), height=140)
    vorauswahl = [o for o in DOMAENEN_OPTIONEN if o.split()[0] in (frage.domains or [])]
    auswahl = st.multiselect("Domänen", DOMAENEN_OPTIONEN, default=vorauswahl, key=_key(name, "domains"))
    frage.domains = [o.split()[0] for o in auswahl]
    frage.kennzahlen = st.multiselect("Kennzahlen", list(manifesto.KENNZAHLEN), default=frage.kennzahlen or [],
                                      key=_key(name, "kennzahlen"))
    anzahl = sum(1 for k in katalog if k.domain_code in frage.domains or k.code == "000")
    st.caption(f"{anzahl} Hauptkategorien gehen als Optionen an Jev. Der Katalog selbst ist nicht editierbar.")
    st.button("Frage löschen", key=_key(name, "loeschen"), on_click=_loeschen, args=(name,))


def render_editor(config: cfg.Config, katalog: list[manifesto.Kategorie]) -> cfg.Config:
    st.header("Fragen")
    if st.session_state.get("cfg__fehler"):
        st.error(st.session_state["cfg__fehler"])
    st.caption(f"Modell: {config.model}")
    config.text_typ = st.text_area("Texttyp (Kontext, geht als text_type an Jev)", value=config.text_typ,
                                   key="cfg__text_typ", height=68)
    for frage in list(config.fragen):
        with st.expander(f"{frage.name} ({frage.type})", expanded=False):
            if frage.type == "manifesto":
                _manifesto_block(frage, katalog)
            elif frage.type in TYPEN:
                _frage_block(frage)
            else:
                st.error(f"Unbekannter Typ '{frage.type}'. In config.yaml korrigieren oder Frage löschen.")
                st.button("Frage löschen", key=_key(frage.name, "loeschen"), on_click=_loeschen, args=(frage.name,))
    st.divider()
    st.subheader("Frage hinzufügen")
    st.text_input("Name (a-z, 0-9, _)", key="neu__name")
    st.selectbox("Typ", TYPEN, key="neu__type")
    st.button("Hinzufügen", on_click=_hinzufuegen)
    if st.session_state.get("neu__fehler"):
        st.error(st.session_state["neu__fehler"])
    st.divider()
    st.button("Zurücksetzen auf config.yaml", on_click=_reset)
    st.download_button("Config als YAML herunterladen", cfg.to_yaml(config), file_name="config.yaml", mime="text/yaml")
    return config
