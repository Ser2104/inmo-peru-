from inmo.ubigeo import resolver


def test_barrio_y_distrito():
    assert resolver("Lobaton", "Lince", "Lince") == {"departamento": "Lima", "provincia": "Lima", "distrito": "Lince", "barrio": "Lobaton"}
    assert resolver("Orrantia", "San Isidro")["distrito"] == "San Isidro"


def test_distrito_con_provincia():
    assert resolver("Santiago de Surco", "Lima", "Lima")["distrito"] == "Santiago de Surco"
    assert resolver("Cayma, Arequipa")["departamento"] == "Arequipa"
    assert resolver("Huaral", "Huaral", "Lima")["provincia"] == "Huaral"


def test_nombres_repetidos():
    assert resolver("Miraflores")["departamento"] == "Lima"
    assert resolver("Miraflores", None, "Arequipa")["departamento"] == "Arequipa"


def test_alias_y_solo_departamento():
    assert resolver("Surco")["distrito"] == "Santiago de Surco"
    assert resolver(None, None, "Loreto") == {"departamento": "Loreto"}
    assert resolver("lugar inventado") == {}
