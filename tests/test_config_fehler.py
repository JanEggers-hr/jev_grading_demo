import pytest

from jevdemo import config as cfg


def test_unbekanntes_feld_wirft_configerror():
    with pytest.raises(cfg.ConfigError):
        cfg.loads("fragen:\n  a:\n    type: noul\n    instructions: x\n    unbekannt: 1\n")
