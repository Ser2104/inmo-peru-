from inmo import llm, negocios
from inmo.agents import concesiones
from inmo.finanzas import tir
from tests.fake_db import FakeDB

P = {"tasa_descuento": 0.07, "tipo_cambio": 3.45}


def test_flujos_y_tir_de_traspaso():
    n = negocios.Negocio(inversion_usd=20000, ventas_mensuales_usd=10000, canon_mensual_usd=800, rubro="cafeteria", plazo_meses=36)
    f = negocios.flujos(n)
    assert f[0] == -21600 and f[1] == (2500 - 800) * 0.6 and f[-1] == 1700 + 1600
    r = negocios.evaluar(n, P)
    assert abs(r["tir_anual"] - ((1 + tir(f)) ** 12 - 1)) < 1e-9
    assert r["payback_meses"] and r["van_pesimista_usd"] < r["van_usd"]


def test_veredictos():
    base = {"tipo": "traspaso", "rubro": "cafeteria", "canon_mensual_usd": 800}
    assert negocios.veredicto({**base, "inversion_usd": 15000, "ventas_mensuales_usd": 12000}, P)["veredicto"] == "Atractivo"
    assert negocios.veredicto({**base, "inversion_usd": 60000, "ventas_mensuales_usd": 4000}, P)["veredicto"] == "Descartar"
    assert negocios.veredicto({**base, "inversion_usd": 15000}, P)["veredicto"] == "Falta información"
    assert negocios.veredicto({"tipo": "estado", "inversion_usd": 80e6}, P)["veredicto"] == "Fuera de escala"


def test_busca_guarda_y_analiza(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(llm, "disponible", lambda: True)
    monkeypatch.setattr(llm, "pedir_json", lambda prompt, **k: [
        {"nombre": "Traspaso cafetería frente a UNSA", "rubro": "cafeteria", "distrito": "Cercado", "departamento": "Arequipa",
         "inversion": 50000, "ventas_mensuales": 40000, "canon_mensual": 2500, "moneda": "PEN", "telefono": "958 111 222"}])
    concesiones.buscar(db, P, cantidad=2)
    concesiones.buscar(db, P, cantidad=2)
    assert len({c["clave"] for c in db.t["concesiones"]}) == len(db.t["concesiones"]) <= len(concesiones.TIPOS)
    c = db.t["concesiones"][0]
    assert round(c["inversion_usd"]) == 14493 and c["telefono"] == "51958111222" and c["provincia"] == "Arequipa"
    monkeypatch.setattr(concesiones.Ubicador, "ubicar", lambda self, c: (-16.4, -71.5, "distrito"))
    conteo = concesiones.analizar(db, P)
    assert sum(conteo.values()) == len(db.t["concesiones"]) and db.t["concesiones"][0]["lat"] == -16.4


def test_respuesta_completa_datos(monkeypatch):
    db = FakeDB()
    db.upsert("concesiones", {"clave": "local|cafeteria hospital|cayma", "tipo": "local", "nombre": "Cafetería hospital", "departamento": "Arequipa", "revisado": True})
    db.t["concesiones"][0].update(contacto_estado="respondido", respuesta="Canon S/ 3,000 al mes, venden S/ 45,000, inversión S/ 60,000, contrato 3 años")
    monkeypatch.setattr(llm, "disponible", lambda: True)
    monkeypatch.setattr(llm, "pedir_json", lambda prompt, **k: {"canon_mensual": 3000, "ventas_mensuales": 45000, "inversion": 60000, "plazo_meses": 36, "moneda": "PEN"})
    assert concesiones.completar(db, P)["respuestas_procesadas"] == 1
    c = db.t["concesiones"][0]
    assert c["contacto_estado"] == "procesado" and c["plazo_meses"] == 36 and round(c["canon_mensual_usd"]) == 870
