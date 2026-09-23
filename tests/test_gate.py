"""Das Passwort-Gate der echten App, über Streamlits AppTest (ohne Netz).

Deckt die vier Bedingungen von auth.gate ab: Env fehlt, schon angemeldet, Eingabe leer,
Vergleich wahr/falsch, dazu die Sperre durch die Brute-Force-Bremse.
"""

import pytest
from streamlit.testing.v1 import AppTest

from jevdemo import auth

PASSWORT = "richtig-und-lang"


@pytest.fixture
def app(root, monkeypatch):
    # setenv vor dem Start: lade_env() überschreibt vorhandene Variablen nicht
    monkeypatch.setenv("APP_PASSWORD", PASSWORT)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(auth, "PAUSE", 0)
    monkeypatch.setattr(auth, "DROSSEL", auth.Drossel())
    return AppTest.from_file(str(root / "app.py"), default_timeout=30)


def _hinter_dem_gate(at) -> bool:
    return any("Noch kein PDF" in i.value for i in at.info)


def test_fehlende_env_stoppt_vor_dem_gate(app, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "")
    app.run()
    assert any("APP_PASSWORD" in e.value for e in app.error)
    assert len(app.text_input) == 0


def test_leere_eingabe_zeigt_nur_das_feld(app):
    app.run()
    assert len(app.text_input) == 1
    assert len(app.error) == 0
    assert not _hinter_dem_gate(app)


def test_falsches_passwort_bleibt_draussen(app):
    app.run()
    app.text_input[0].input("falsch").run()
    assert any("Falsches Passwort" in e.value for e in app.error)
    assert not _hinter_dem_gate(app)


def test_richtiges_passwort_laesst_rein_und_bleibt_angemeldet(app):
    app.run()
    app.text_input[0].input(PASSWORT).run()
    assert _hinter_dem_gate(app)
    app.run()
    assert _hinter_dem_gate(app)


def test_fehlversuch_wird_gezaehlt(app):
    app.run()
    app.text_input[0].input("falsch").run()
    app.run()  # Rerun mit derselben Eingabe zählt nicht doppelt
    assert len(auth.DROSSEL._fehler) == 1


def test_sperre_blockiert_auch_das_richtige_passwort(app):
    for _ in range(auth.DROSSEL.max_fehler):
        auth.DROSSEL.fehler()
    app.run()
    app.text_input[0].input(PASSWORT).run()
    assert not _hinter_dem_gate(app)
    assert any("Zu viele Fehlversuche" in e.value for e in app.error)
