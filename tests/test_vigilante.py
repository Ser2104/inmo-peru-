from datetime import datetime, timedelta, timezone

from inmo import config
from inmo.agents import vigilante
from inmo.collectors import base, runner
from tests.fake_db import FakeDB

AHORA = datetime.now(timezone.utc)


def sano(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "x")
    monkeypatch.setattr(config, "SUPABASE_KEY", "x")
    monkeypatch.setattr(config, "TELEGRAM_TOKEN", "x")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "x")
    db = FakeDB()
    db.registrar("analista", True, {})
    db.upsert("inmuebles", {"url": "u", "operacion": "venta", "precio_usd": 1})
    db.upsert("parametros", {"clave": "tipo_cambio", "valor": 3.7, "actualizado": AHORA.isoformat()})
    db.upsert("mercado_temporal", {"clave": "lima|lima|miraflores|x|*", "fecha": AHORA.isoformat()})
    db.upsert("fuentes", {"id": "f", "nombre": "F", "tipo": "navent", "activo": True, "fallos_seguidos": 0, "config": {"promedio_total": 100, "ultimo_total": 95}})
    return db


def textos(db):
    return " ".join(x["texto"] for x in vigilante.revisar(db))


def test_todo_bien(monkeypatch):
    assert vigilante.revisar(sano(monkeypatch)) == []


def test_detecta_fallas(monkeypatch):
    db = sano(monkeypatch)
    db.t["ejecuciones"][0]["fin"] = (AHORA - timedelta(hours=12)).isoformat()
    db.t["fuentes"][0]["config"]["ultimo_total"] = 10
    db.t["parametros"][0]["valor"] = 37
    db.tamano = 480 * 1024 * 1024
    t = textos(db)
    assert "analista" in t and "trajo 10 avisos" in t and "Tipo de cambio raro" in t and "límite gratis" in t


def test_sin_inmuebles_nuevos(monkeypatch):
    db = sano(monkeypatch)
    db.t["inmuebles"][0]["primera_vez"] = (AHORA - timedelta(days=5)).isoformat()
    assert "48 horas" in textos(db)


def test_avisa_una_sola_vez(monkeypatch):
    db = sano(monkeypatch)
    db.t["inmuebles"].clear()
    enviados = []
    monkeypatch.setattr(vigilante, "telegram", enviados.append)
    monkeypatch.setattr(vigilante, "crear_issue", lambda *a, **k: None)
    vigilante.ejecutar(db, db.parametros())
    vigilante.ejecutar(db, db.parametros())
    assert len(enviados) == 1
    db.upsert("inmuebles", {"url": "nuevo", "operacion": "venta", "precio_usd": 1})
    vigilante.ejecutar(db, db.parametros())
    assert "normalidad" in enviados[-1]


def test_cortacircuitos(monkeypatch):
    db = FakeDB()
    db.upsert("fuentes", {"id": "f", "nombre": "F", "tipo": "navent", "urls": ["https://a.pe/{n}"], "config": {}, "fallos_seguidos": 2})
    monkeypatch.setattr(base, "descargar", lambda url, **k: (_ for _ in ()).throw(RuntimeError("HTTP 403")))
    runner.recolectar_fuente(db, db.select("fuentes")[0], db.parametros())
    f = db.select("fuentes")[0]
    assert runner.en_pausa(f)
    assert "omitido" in runner.recolectar_fuente(db, f, db.parametros())
