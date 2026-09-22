import pytest

from jevdemo import config as cfg
from jevdemo import manifesto


@pytest.fixture(scope="module")
def katalog():
    return manifesto.load_catalog()


def test_default_laedt_und_ist_gueltig():
    config = cfg.load()
    assert cfg.validate(config) == []
    assert config.model == "typesafe/jev-1.13"
    assert 300 <= config.chunk_tokens <= 3000
    assert 1000 <= config.budget_tokens <= 28000
    assert len(config.fragen) >= 2
    assert sum(f.type == "manifesto" for f in config.fragen) == 1


def test_yaml_roundtrip():
    config = cfg.load()
    text = cfg.to_yaml(config)
    assert "Wahlprogramm" in text and "ä" in text
    assert cfg.to_dict(cfg.loads(text)) == cfg.to_dict(config)


def _frage(**kw) -> cfg.Frage:
    basis = dict(name="f", type="noul", instructions="Frage?")
    basis.update(kw)
    return cfg.Frage(**basis)


def _config(*fragen) -> cfg.Config:
    return cfg.Config(text_typ="t", fragen=list(fragen))


def test_score_ohne_criteria_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="score", skala=[1, 5])))
    assert any("score braucht criteria" in f for f in fehler)


def test_score_mit_falscher_skala_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="score", criteria=["a", "b"], skala=[5, 1])))
    assert any("skala" in f for f in fehler)


def test_choice_mit_liste_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="choice", criteria=["a", "b"])))
    assert any("choice braucht criteria als Mapping" in f for f in fehler)


def test_noul_mit_criteria_faellt_durch():
    fehler = cfg.validate(_config(_frage(type="noul", criteria=["a"])))
    assert any("noul hat weder" in f for f in fehler)


def test_doppelter_manifesto_block_faellt_durch():
    m = dict(type="manifesto", domains=["1"], kennzahlen=["rile"])
    fehler = cfg.validate(_config(_frage(name="a", **m), _frage(name="b", **m)))
    assert any("höchstens eine Frage vom Typ manifesto" in f for f in fehler)


def test_ungueltiger_name_und_doppelter_name():
    fehler = cfg.validate(_config(_frage(name="Böse Frage"), _frage(name="x"), _frage(name="x")))
    assert any("Name darf nur" in f for f in fehler)
    assert any("doppelt" in f for f in fehler)


def test_unbekannter_typ_und_leere_instruction():
    fehler = cfg.validate(_config(_frage(type="essay"), _frage(name="g", instructions="  ")))
    assert any("unbekannter Typ" in f for f in fehler)
    assert any("instructions fehlt" in f for f in fehler)


def test_grenzen_fuer_tokens():
    config = _config(_frage())
    config.chunk_tokens = 100
    config.budget_tokens = 50000
    fehler = cfg.validate(config)
    assert any("chunk_tokens" in f for f in fehler)
    assert any("budget_tokens" in f for f in fehler)


def test_to_questions_laesst_inaktive_weg_und_baut_manifesto(katalog):
    config = _config(
        _frage(name="ja", type="noul"),
        _frage(name="aus", type="noul", aktiv=False),
        _frage(name="stufe", type="score", criteria=["a", "b"], skala=[0, 1]),
        _frage(name="wahl", type="choice", criteria={"A": "a", "B": "b"}),
        _frage(name="manifesto", type="manifesto", domains=["1"], kennzahlen=["rile"]),
    )
    fragen = cfg.to_questions(config, katalog)
    assert list(fragen) == ["ja", "stufe", "wahl", "manifesto"]
    assert fragen["ja"] == {"type": "noul", "instructions": "Frage?"}
    assert fragen["stufe"] == {"type": "score", "instructions": "Frage?", "criteria": ["a", "b"]}
    assert fragen["wahl"]["criteria"] == {"A": "a", "B": "b"}
    assert fragen["manifesto"]["type"] == "choice"
    assert "000 No meaningful category applies" in fragen["manifesto"]["criteria"]


def test_from_dict_ohne_fragen_wirft():
    with pytest.raises(cfg.ConfigError):
        cfg.from_dict({"model": "x"})
    with pytest.raises(cfg.ConfigError):
        cfg.loads("fragen:\n  a: [1, 2]\n")
