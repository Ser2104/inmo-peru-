import random
from collections import Counter

from inmo import config, llm
from inmo.agents import explorador
from inmo.collectors import base, ia
from tests.fake_db import FakeDB


def test_pistas_sin_duplicados():
    db = FakeDB()
    pistas = [{"nombre": "Edificio Punku", "distrito": "Cayma", "url": "https://inventa.pe/punku"},
              {"nombre": "EDIFICIO PUNKU", "distrito": "cayma", "url": "https://foro.pe/hilo"},
              {"nombre": None, "url": None}]
    assert explorador.guardar_pistas(db, pistas, "foros", "Arequipa") == 1
    assert explorador.guardar_pistas(db, pistas, "foros", "Arequipa") == 0
    assert db.t["pistas"][0]["departamento"] == "Arequipa"


def test_prioriza_departamentos_sin_datos():
    random.seed(3)
    db = FakeDB()
    for k in range(500):
        db.upsert("inmuebles", {"url": f"u{k}", "departamento": "Lima", "operacion": "venta", "activo": True})
    elegidos = Counter(d for _ in range(40) for d, _ in explorador.elegir(db, db.parametros()))
    assert elegidos["Lima"] < 8
    assert sum(elegidos.values()) > 150


def test_aprende_categorias_utiles(monkeypatch):
    random.seed(1)
    db = FakeDB()
    p = {**db.parametros(), "explorador_stats": {"remates": {"usos": 10, "utiles": 9}, "foros": {"usos": 10, "utiles": 0}}}
    cats = Counter(c for _ in range(30) for _, c in explorador.elegir(db, p))
    assert cats["remates"] > cats["foros"] * 3


def test_verificar_convierte_pista_en_inmueble(monkeypatch):
    db = FakeDB()
    explorador.guardar_pistas(db, [{"nombre": "Torre Sol", "distrito": "Yanahuara", "url": "https://constructora-sol.pe/torre", "estado_obra": "preventa"}], "constructoras_pequenas", "Arequipa")
    monkeypatch.setattr(base, "descargar", lambda url, **k: "<html></html>")
    monkeypatch.setattr(ia, "extraer", lambda html, url: [{"url": url + "/a", "titulo": "Depa 2 dorm", "precio": 320000, "moneda": "PEN", "area_m2": 70, "tipo": "departamento"}])
    r = explorador.verificar(db, {**db.parametros(), "tipo_cambio": 3.45})
    assert r["verificadas"] == 1
    inm = db.t["inmuebles"][0]
    assert inm["distrito"] == "Yanahuara" and inm["departamento"] == "Arequipa" and inm["estado"] == "preventa"
    assert db.t["pistas"][0]["estado"] == "verificada"


def test_pista_sin_datos_se_descarta(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    explorador.guardar_pistas(db, [{"nombre": "Proyecto X", "url": "https://x.pe"}], "foros", "Puno")
    monkeypatch.setattr(base, "descargar", lambda url, **k: (_ for _ in ()).throw(RuntimeError("403")))
    for _ in range(3):
        explorador.verificar(db, db.parametros())
    assert db.t["pistas"][0]["estado"] == "descartada"


def test_aprende_fuentes_nuevas():
    db = FakeDB()
    for k in range(3):
        db.upsert("inmuebles", {"url": f"https://www.inmobiliaria-sur.pe/p{k}", "fuente": "explorador", "activo": True})
    assert explorador.aprender_fuentes(db)["fuentes_nuevas"] == ["inmobiliaria-sur-pe"]


def test_enlaces_pdf():
    html = '<a href="/docs/catalogo.pdf">Lima</a><a href="/x.html">x</a><a href="/docs/catalogo.pdf">dup</a>'
    assert ia.enlaces_pdf(html, "https://www.bbva.pe/irbsa.html") == ["https://www.bbva.pe/docs/catalogo.pdf"]
