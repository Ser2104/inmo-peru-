from inmo import entorno

BASE = {k: 0 for k in entorno.CATEGORIAS}


def test_demanda_sube_y_competencia_baja():
    cerca_u = {**BASE, "universidad": 3, "paradero": 10}
    assert entorno.puntaje(cerca_u, "cafeteria")[0] > entorno.puntaje({**BASE, "paradero": 2}, "cafeteria")[0]
    assert entorno.puntaje({**cerca_u, "cafe": 20}, "cafeteria")[0] < entorno.puntaje(cerca_u, "cafeteria")[0]


def test_resumen_sugiere_rubros():
    r = entorno.resumen({**BASE, "hospital": 3, "paradero": 5}, "otro")
    assert r["mejores_rubros"][0][0] in ("farmacia", "estacionamiento") and "3 hospitales o clínicas" in r["cerca"]


def test_contar_etiquetas_osm():
    c = entorno.contar([{"tags": {"amenity": "university"}}, {"tags": {"amenity": "cafe"}}, {"tags": {"shop": "convenience"}}])
    assert c["universidad"] == 1 and c["cafe"] == 1 and c["bodega"] == 1 and c["tienda"] == 1
