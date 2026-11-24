from inmo.agents import confirmador
from tests.fake_db import FakeDB

INM = {"url": "https://urbania.pe/inmueble/clasificado/veclapin-departamento-en-cayma-1.html", "titulo": "Departamento en Cayma con vista", "precio": 120000, "precio_usd": 120000}


def pagina(estado=200, final=None, html="USD 120,000 · Departamento en Cayma con vista"):
    return lambda url: (estado, final or url, html)


def test_revisar():
    assert confirmador.revisar(INM, pagina()) == "ok"
    assert confirmador.revisar(INM, pagina(404)) == "no_disponible"
    assert confirmador.revisar(INM, pagina(final="https://urbania.pe/buscar/venta-de-departamentos")) == "no_disponible"
    assert confirmador.revisar(INM, pagina(html="Este aviso ya no está disponible")) == "no_disponible"
    assert confirmador.revisar(INM, pagina(html="USD 135,000 · Departamento en Cayma con vista")) == "precio_cambio"
    assert confirmador.revisar(INM, pagina(403)) == "no_verificable"


def test_solo_queda_comprar_si_se_confirma(monkeypatch):
    monkeypatch.setattr(confirmador.time, "sleep", lambda s: None)
    db = FakeDB()
    a = db.upsert("inmuebles", {**INM, "activo": True}, devolver=True)[0]
    b = db.upsert("inmuebles", {**INM, "url": INM["url"] + "x", "activo": True}, devolver=True)[0]
    db.upsert("analisis", [{"inmueble_id": a["id"], "veredicto": "Comprar", "riesgos": []}, {"inmueble_id": b["id"], "veredicto": "Comprar", "riesgos": []}])
    abrir = lambda url: (200, url, "USD 120,000") if url == INM["url"] else (404, url, "")
    assert confirmador.ejecutar(db, abrir_fn=abrir) == {"ok": 1, "no_disponible": 1}
    v = {x["inmueble_id"]: x["veredicto"] for x in db.t["analisis"]}
    assert v[a["id"]] == "Comprar" and v[b["id"]] == "Revisar a mano"
    assert db.t["inmuebles"][1]["activo"] is False and db.t["inmuebles"][0]["confirmacion"] == "ok"
