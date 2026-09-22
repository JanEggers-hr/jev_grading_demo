from jevdemo.ui import views


def test_mische_und_noul_farbe():
    assert views.mische("#000000", "#ffffff", 0.5) == "#808080"
    assert views.noul_farbe(0.0) == views.ROT
    assert views.noul_farbe(0.5) == views.MITTE
    assert views.noul_farbe(1.0) == views.BLAU
    assert views.noul_farbe(-3) == views.ROT
    assert views.noul_farbe(7) == views.BLAU
    assert views.noul_farbe(0.25) not in (views.ROT, views.MITTE)


def test_textfarbe_nach_luminanz():
    assert views.textfarbe("#2a78d6") == views.TEXT_HELL
    assert views.textfarbe("#e34948") == views.TEXT_HELL
    assert views.textfarbe("#f0efec") == views.TEXT_DUNKEL
    assert views.textfarbe("#eda100") == views.TEXT_DUNKEL


def test_optionsfarbe_und_kurz():
    assert views.optionsfarbe(0) == "#2a78d6"
    assert views.optionsfarbe(7) == "#e34948"
    assert views.optionsfarbe(8) == views.SONSTIGE
    assert views.kurz("kurz") == "kurz"
    assert views.kurz("a" * 60, 10) == "a" * 9 + "…"


def test_balken_figur():
    fig = views.balken(["a", "b"], [10.0, 20.0], views.BLAU, "x")
    assert list(fig.data[0].x) == [10.0, 20.0]
    assert fig.data[0].orientation == "h"
    fig = views.rile_balken(-12.0)
    assert fig.data[0].marker.color == views.ROT
    assert fig.layout.xaxis.range == (-100, 100)
