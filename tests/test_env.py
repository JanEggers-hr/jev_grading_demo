from jevdemo.env import lade_env


def test_lade_env_setzt_nur_fehlende_schluessel(tmp_path):
    datei = tmp_path / ".env"
    datei.write_text('A=1\nexport B="zwei"\n# Kommentar\nC=drei # kein Kommentar\n\nD=\'vier\'\n', encoding="utf-8")
    umgebung = {"B": "alt"}
    lade_env(datei, umgebung)
    assert umgebung == {"A": "1", "B": "alt", "C": "drei # kein Kommentar", "D": "vier"}


def test_lade_env_ohne_datei_tut_nichts(tmp_path):
    umgebung = {}
    lade_env(tmp_path / "fehlt", umgebung)
    assert umgebung == {}
