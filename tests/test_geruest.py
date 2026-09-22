import importlib


def test_paket_importierbar():
    assert importlib.import_module("jevdemo").__doc__


def test_manifesto_json_vorhanden(root):
    assert (root / "manifesto" / "mp_v5.json").is_file()
