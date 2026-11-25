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
    buena = {"puntaje": 8, "cerca": ["2 universidades o institutos"], "competidores": 1, "radio_m": 500}
    mala = {**buena, "puntaje": 2}
    assert negocios.veredicto({**base, "inversion_usd": 15000, "ventas_mensuales_usd": 12000}, P, buena)["veredicto"] == "Atractivo"
    assert negocios.veredicto({**base, "inversion_usd": 15000, "ventas_mensuales_usd": 12000}, P)["veredicto"] == "Negociar"
    assert negocios.veredicto({**base, "inversion_usd": 15000, "ventas_mensuales_usd": 6000}, P, mala)["veredicto"] != "Atractivo"
    assert negocios.veredicto({**base, "inversion_usd": 60000, "ventas_mensuales_usd": 4000}, P)["veredicto"] == "Descartar"
    assert negocios.veredicto({**base, "inversion_usd": 15000}, P)["veredicto"] == "Falta información"
    assert negocios.veredicto({"tipo": "estado", "inversion_usd": 80e6}, P)["veredicto"] == "Fuera de escala"


def test_busca_guarda_y_analiza(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(llm, "disponible", lambda: True)
    monkeypatch.setattr(llm, "pedir_json", lambda prompt, **k: [
        {"nombre": "Traspaso cafetería frente a UNSA", "rubro": "cafeteria", "distrito": "Cercado", "departamento": "Arequipa", "direccion": "Av. Venezuela 100",
         "inversion": 50000, "ventas_mensuales": 40000, "canon_mensual": 2500, "moneda": "PEN", "telefono": "958 111 222"}])
    concesiones.buscar(db, P, cantidad=2)
    concesiones.buscar(db, P, cantidad=2)
    assert len({c["clave"] for c in db.t["concesiones"]}) == len(db.t["concesiones"]) <= len(concesiones.TIPOS)
    c = db.t["concesiones"][0]
    assert round(c["inversion_usd"]) == 14493 and c["telefono"] == "51958111222" and c["provincia"] == "Arequipa"
    monkeypatch.setattr(concesiones.Ubicador, "buscar", lambda self, t: (-16.40, -71.53))
    monkeypatch.setattr(concesiones.entorno, "consultar", lambda lat, lng: {**{k: 0 for k in concesiones.entorno.CATEGORIAS}, "universidad": 3, "paradero": 10, "cafe": 2})
    monkeypatch.setattr(concesiones.entorno.time, "sleep", lambda s: None)
    conteo = concesiones.analizar(db, P)
    assert sum(v for k, v in conteo.items() if k != "consultas_entorno") == len(db.t["concesiones"]) and db.t["concesiones"][0]["lat"] == -16.40
    c = next(x for x in db.t["concesiones"] if x["tipo"] != "estado")
    assert c["ubicacion_precision"] == "lugar" and c["puntaje_ubicacion"] > 6 and c["entorno"]["mejores_rubros"][0][0] in ("cafeteria", "libreria", "fotocopiadora")


def test_respuesta_completa_datos(monkeypatch):
    db = FakeDB()
    db.upsert("concesiones", {"clave": "local|cafeteria hospital|cayma", "tipo": "local", "nombre": "Cafetería hospital", "departamento": "Arequipa", "revisado": True})
    db.t["concesiones"][0].update(contacto_estado="respondido", respuesta="Canon S/ 3,000 al mes, venden S/ 45,000, inversión S/ 60,000, contrato 3 años")
    monkeypatch.setattr(llm, "disponible", lambda: True)
    monkeypatch.setattr(llm, "pedir_json", lambda prompt, **k: {"canon_mensual": 3000, "ventas_mensuales": 45000, "inversion": 60000, "plazo_meses": 36, "moneda": "PEN"})
    assert concesiones.completar(db, P)["respuestas_procesadas"] == 1
    c = db.t["concesiones"][0]
    assert c["contacto_estado"] == "procesado" and c["plazo_meses"] == 36 and round(c["canon_mensual_usd"]) == 870
