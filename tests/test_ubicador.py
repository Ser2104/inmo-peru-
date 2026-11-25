from inmo.agents import ubicador
from tests.fake_db import FakeDB

LUGARES = {"av. ejercito 123, yanahuara, arequipa, arequipa, peru": (-16.39, -71.54), "cayma, arequipa, arequipa, peru": (-16.37, -71.55)}


def falso(llamadas):
    def consultar(texto):
        llamadas.append(texto)
        return LUGARES.get(ubicador.norm(texto))
    return consultar


def test_direccion_distrito_y_cache():
    db, llamadas = FakeDB(), []
    u = ubicador.Ubicador(db, falso(llamadas))
    assert u.ubicar({"id": "a", "direccion": "Av. Ejército 123", "distrito": "Yanahuara", "provincia": "Arequipa", "departamento": "Arequipa"})[2] == "direccion"
    lat, lng, prec = u.ubicar({"id": "b", "distrito": "Cayma", "provincia": "Arequipa", "departamento": "Arequipa"})
    assert prec == "distrito" and abs(lat + 16.3625) < 0.01
    assert not any("Cayma" in x for x in llamadas)
    assert ubicador.Ubicador(db, falso([])).cache


def test_fuera_de_peru_se_rechaza():
    assert not ubicador.dentro_peru(40.7, -74.0)
    assert ubicador.dentro_peru(-12.1, -77.03)


def test_ejecutar(monkeypatch):
    db = FakeDB()
    db.upsert("inmuebles", {"url": "1", "activo": True, "lat": -12.1, "lng": -77.0})
    db.upsert("inmuebles", {"url": "2", "activo": True, "distrito": "Cayma", "provincia": "Arequipa", "departamento": "Arequipa"})
    monkeypatch.setattr(ubicador, "consultar", lambda t: LUGARES.get(ubicador.norm(t)))
    assert ubicador.ejecutar(db)["ubicados_por_distrito"] == 2
    assert {i["ubicacion_precision"] for i in db.t["inmuebles"]} == {"exacta", "distrito"}


def test_prefiere_el_pueblo_y_rechaza_direcciones_lejanas():
    lugares = {"poblado|cayma, arequipa, arequipa, peru": (-16.38, -71.545), "cayma, arequipa, arequipa, peru": (-16.20, -71.45),
               "calle lejana 1, cayma, arequipa, arequipa, peru": (-15.9, -71.0)}
    u = ubicador.Ubicador(FakeDB(), lambda t: lugares.get(ubicador.norm(t)))
    lat, lng, prec = u.ubicar({"id": "x", "direccion": "Calle Lejana 1", "distrito": "Cayma", "provincia": "Arequipa", "departamento": "Arequipa"})
    assert prec == "distrito" and abs(lat + 16.3625) < 0.01


def test_reubicar_mueve_puntos_del_centro_geografico(monkeypatch):
    db = FakeDB()
    db.upsert("inmuebles", {"url": "1", "activo": True, "lat": -16.20, "lng": -71.45, "ubicacion_precision": "distrito", "distrito": "Cayma", "provincia": "Arequipa", "departamento": "Arequipa"})
    monkeypatch.setattr(ubicador, "consultar", lambda t: {"poblado|cayma, arequipa, arequipa, peru": (-16.38, -71.545)}.get(ubicador.norm(t)))
    assert ubicador.reubicar(db)["reubicados"] == 1 and abs(db.t["inmuebles"][0]["lat"] + 16.3625) < 0.01
