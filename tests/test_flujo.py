from pathlib import Path

from inmo.agents import analista, auditor, alertas, mejora
from inmo.collectors import base, runner
from tests.fake_db import FakeDB
from tests.test_valoracion import mercado

HTML = (Path(__file__).parent / "fixtures" / "navent.html").read_text()


def test_flujo_completo(monkeypatch):
    db = FakeDB()
    db.upsert("fuentes", {"id": "urbania", "nombre": "Urbania", "tipo": "navent", "urls": ["https://urbania.pe/p-{n}.html"], "config": {}, "fallos_seguidos": 0})
    monkeypatch.setattr(base, "descargar", lambda url, **k: HTML)
    p = db.parametros()
    r = runner.recolectar_fuente(db, db.select("fuentes")[0], p)
    assert r["total"] == 3 and r["nuevos"] == 3
    assert len(db.t["precios_historial"]) == 3

    for m in mercado():
        m.pop("id")
        m.update(url=f"https://x.pe/{len(db.t['inmuebles'])}", activo=True, ultima_vez=mercado()[0]["primera_vez"])
        db.upsert("inmuebles", m)
    db.upsert("inmuebles", {"url": "https://x.pe/ganga", "operacion": "venta", "tipo": "departamento", "departamento": "Lima",
                            "provincia": "Lima", "distrito": "Miraflores", "area_m2": 90, "precio_usd": 90 * 1900, "activo": True,
                            "ultima_vez": mercado()[0]["primera_vez"]})

    auditor.ejecutar(db)
    res = analista.ejecutar(db, p)
    assert res["analizados"] >= 42
    ganga = next(a for a in db.t["analisis"] if a["precio_usd"] == 90 * 1900)
    assert ganga["veredicto"] == "Comprar" and ganga["detalle"]["escenarios"]["pesimista"]["tir_10"] >= 0.03

    enviados = []
    monkeypatch.setattr(alertas, "enviar", enviados.append)
    assert alertas.ejecutar(db, p)["enviadas"] >= 1
    assert alertas.ejecutar(db, p)["enviadas"] == 0

    cal = mejora.calibrar(db, p)
    assert 0.03 <= cal["rentabilidad_por_departamento"]["lima"] <= 0.12


def test_fuente_caida_suma_fallos(monkeypatch):
    db = FakeDB()
    db.upsert("fuentes", {"id": "f", "nombre": "F", "tipo": "navent", "urls": ["https://a.pe/{n}"], "config": {}, "fallos_seguidos": 2})

    def falla(url, **k):
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr(base, "descargar", falla)
    runner.recolectar_fuente(db, db.select("fuentes")[0], db.parametros())
    assert db.t["fuentes"][0]["fallos_seguidos"] == 3


def test_releer_no_borra_ubicacion(monkeypatch):
    db = FakeDB()
    db.upsert("fuentes", {"id": "urbania", "nombre": "U", "tipo": "navent", "urls": ["https://urbania.pe/p-{n}.html"], "config": {}, "fallos_seguidos": 0})
    monkeypatch.setattr(base, "descargar", lambda url, **k: HTML)
    runner.recolectar_fuente(db, db.select("fuentes")[0], db.parametros())
    db.t["inmuebles"][0].update(lat=-12.1, lng=-77.0, ubicacion_precision="distrito")
    runner.recolectar_fuente(db, db.select("fuentes")[0], db.parametros(), completo=True)
    assert db.t["inmuebles"][0]["lat"] == -12.1
