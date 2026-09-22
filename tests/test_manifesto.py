from jevdemo import manifesto as m


def test_katalog_hat_57_hauptkategorien():
    kat = m.load_catalog()
    codes = [k.code for k in kat]
    assert len(codes) == 57
    assert len(set(codes)) == 57
    assert "000" in codes
    assert all("." not in c for c in codes)
    assert codes == sorted(codes)


def test_eltern_beschreibung_verkettet_kinder():
    kat = {k.code: k for k in m.load_catalog()}
    assert kat["601"].title == "National Way of Life: Positive"
    assert kat["601"].domain_code == "6"
    assert "Immigration: Negative" in kat["601"].description
    assert kat["104"].title == "Military: Positive"


def test_kennzahl_codes_existieren_im_katalog():
    codes = {k.code for k in m.load_catalog()}
    for plus, minus in m.KENNZAHLEN.values():
        assert set(plus) <= codes
        assert set(minus) <= codes


def test_label_und_code():
    k = m.Kategorie("104", "Military: Positive", "1", "External Relations", "x")
    assert m.label(k) == "104 Military: Positive"
    assert m.code_of(m.label(k)) == "104"


def test_build_question_filtert_domaenen_und_behaelt_000():
    kat = m.load_catalog()
    q = m.build_question("Which category?", ["1"], kat)
    codes = {m.code_of(lbl) for lbl in q["criteria"]}
    assert q["type"] == "choice"
    assert q["instructions"] == "Which category?"
    assert "000" in codes
    assert "104" in codes
    assert "401" not in codes
    assert q["criteria"]["104 Military: Positive"].startswith("The importance")


def test_anteile_domaenen_top():
    kat = m.load_catalog()
    ant = m.anteile({"104 Military: Positive": 0.75, "401 Free Market Economy": 0.25})
    assert ant == {"104": 75.0, "401": 25.0}
    dom = m.domaenen(ant, kat)
    assert dom["1"] == 75.0
    assert dom["4"] == 25.0
    assert dom["0"] == 0.0
    assert m.top(ant, kat, n=1) == [("104", "Military: Positive", 75.0)]


def test_kennzahlen_auf_synthetischen_anteilen():
    assert m.kennzahlen({"104": 100.0}, ["rile", "intpeace"]) == {"rile": 100.0, "intpeace": 0.0}
    ant = {"105": 40.0, "504": 10.0, "401": 50.0}
    kz = m.kennzahlen(ant, ["rile", "planeco", "markeco", "welfare", "intpeace"])
    assert kz == {"rile": 0.0, "planeco": 0.0, "markeco": 50.0, "welfare": 10.0, "intpeace": 40.0}
