"""Brute-Force-Bremse und Passwortvergleich, ohne Streamlit."""

from jevdemo import auth


class Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_passwort_ok():
    assert auth.passwort_ok("geheim", "geheim")
    assert not auth.passwort_ok("geheiM", "geheim")
    assert not auth.passwort_ok("", "geheim")
    # Leeres Soll-Passwort darf nie durchlassen, auch nicht bei leerer Eingabe
    assert not auth.passwort_ok("", "")


def test_drossel_sperrt_ab_dem_maximum():
    uhr = Uhr()
    d = auth.Drossel(max_fehler=3, fenster=600, uhr=uhr)
    d.fehler()
    d.fehler()
    assert d.gesperrt() == 0
    d.fehler()
    assert d.gesperrt() == 600


def test_drossel_zaehlt_nur_im_fenster():
    uhr = Uhr()
    d = auth.Drossel(max_fehler=3, fenster=600, uhr=uhr)
    d.fehler()
    uhr.t += 400
    d.fehler()
    d.fehler()
    assert d.gesperrt() == 200  # der erste Fehlversuch fällt nach 200 s aus dem Fenster
    uhr.t += 200
    assert d.gesperrt() == 0
