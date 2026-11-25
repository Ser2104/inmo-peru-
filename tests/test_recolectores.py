from pathlib import Path

from inmo.collectors import base, navent, runner
from inmo.collectors.ia import json_ld

HTML = (Path(__file__).parent / "fixtures" / "navent.html").read_text()


def test_numeros_y_precios():
    assert base.numero("150,000") == 150000
    assert base.numero("380.000") == 380000
    assert base.numero("1.234,50") == 1234.5
    assert base.precio("S/ 2,736 · USD 800") == (800, "USD")
    assert base.precio("S/ 380.000") == (380000, "PEN")


def test_navent():
    items = navent.parsear(HTML, "https://urbania.pe/x")
    assert len(items) == 3
    venta, alquiler, preventa = items
    assert venta["operacion"] == "venta" and venta["area_m2"] == 95 and venta["dormitorios"] == 3
    assert venta["distrito"] == "Santiago de Surco" and venta["departamento"] == "Lima"
    assert alquiler["operacion"] == "alquiler" and alquiler["precio"] == 800
    assert preventa["estado"] == "preventa" and preventa["departamento"] == "Arequipa"


def test_normalizar():
    item = runner.normalizar(navent.parsear(HTML, "https://urbania.pe/x")[2], "urbania", 3.75)
    assert item["precio_usd"] == round(380000 / 3.75, 2)
    assert base.valido(item)
    assert set(item) == set(runner.COLUMNAS)


def test_json_ld():
    html = '<script type="application/ld+json">{"@type":"Residence","name":"Depa","url":"/a","offers":{"price":"120000","priceCurrency":"USD"},"floorSize":{"value":70}}</script>'
    items = json_ld(html, "https://x.pe/")
    assert items[0]["precio"] == 120000 and items[0]["url"] == "https://x.pe/a"


def test_rangos_y_textos():
    item = base.limpiar({"url": "u", "precio": "S/ 350,000", "moneda": "PEN", "dormitorios": "1 - 3", "area_m2": "70 m²"}, 3.45)
    assert item["dormitorios"] == 1 and item["area_m2"] == 70 and item["precio"] == 350000


def test_proyecto_usa_unidad_mas_chica_y_tipo_de_url():
    html = ('<div data-qa="posting PROPERTY" data-to-posting="/inmueble/proyecto/ememvein-proyecto-sol-cayma-1">'
            '<div data-qa="POSTING_CARD_PRICE">Departamentos desde S/ 299,000</div><div data-qa="POSTING_CARD_LOCATION">Cayma, Arequipa</div>'
            '<div data-qa="POSTING_CARD_FEATURES">45 un. 1 a 3 dorm. 41 a 133 m² tot.</div></div>'
            '<div data-qa="posting PROPERTY" data-to-posting="/inmueble/clasificado/vecltein-venta-de-terreno-en-lurin-2">'
            '<h3>Lindo departamento</h3><div data-qa="POSTING_CARD_PRICE">USD 90,000</div><div data-qa="POSTING_CARD_FEATURES">500 m² tot.</div></div>')
    proyecto, terreno = navent.parsear(html, "https://urbania.pe/x")
    assert proyecto["area_m2"] == 41 and proyecto["dormitorios"] == 1
    assert terreno["tipo"] == "terreno" and terreno["area_m2"] == 500


def test_fecha_entrega_texto():
    from inmo.collectors.base import fecha
    assert fecha("junio 2027") == "2027-06-01" and fecha("2027-06-30") == "2027-06-30" and fecha("Entrega inmediata") is None


def test_guardar_salta_fila_rechazada():
    import httpx
    from inmo.collectors import runner
    from tests.fake_db import FakeDB

    class DBQuisquillosa(FakeDB):
        def upsert(self, tabla, filas, **k):
            if tabla == "inmuebles" and any(f.get("operacion") == "mala" for f in (filas if isinstance(filas, list) else [filas])):
                raise httpx.HTTPStatusError("400", request=httpx.Request("POST", "http://x"), response=httpx.Response(400, text="check"))
            return super().upsert(tabla, filas, **k)

    db = DBQuisquillosa()
    filas = runner.guardar(db, [{"url": "a", "operacion": "venta", "precio_usd": 1e5}, {"url": "b", "operacion": "mala"}])
    assert [f["url"] for f in filas] == ["a"]


def test_tipo_por_primera_palabra():
    from inmo.collectors.base import tipo_desde
    assert tipo_desde("Depósito en San Isidro") == "deposito"
    assert tipo_desde("Departamento con cochera en Cayma") == "departamento"
    assert tipo_desde("Venta de cochera en edificio") == "estacionamiento"


def test_coordenadas_de_urbania():
    from inmo.collectors import navent
    html = ('{"postingId":"151524906","title":"x","postingLocation":{"postingGeolocation":{"geolocation":{"latitude":-12.0982826,"longitude":-76.9806876}}}}'
            '{"postingId":"151465432","postingGeolocation":{"geolocation":{"latitude":-12.111,"longitude":-76.994}}}')
    assert navent.coordenadas(html) == {"151524906": (-12.0982826, -76.9806876), "151465432": (-12.111, -76.994)}


def test_portal_completo_tipologias(monkeypatch):
    from inmo.agents import rastreador
    from inmo.collectors import base, ia
    from tests.fake_db import FakeDB
    monkeypatch.setattr(rastreador, "leer_sitemap", lambda url, limite=0: ["https://nexoinmobiliario.pe/departamentos/lince/lombardia-2393"])
    monkeypatch.setattr(base, "descargar", lambda url, **k: "<html>")
    monkeypatch.setattr(ia, "extraer", lambda html, url: [
        {"titulo": "Flat 1 dorm", "precio": 99000, "moneda": "USD", "area_m2": 40, "operacion": "venta", "distrito": "Lince", "departamento": "Lima"},
        {"titulo": "Flat 2 dorm", "precio": 139000, "moneda": "USD", "area_m2": 62, "operacion": "venta", "distrito": "Lince", "departamento": "Lima"}])
    db = FakeDB()
    r = rastreador.portal_completo(db, {"tipo_cambio": 3.45}, "nexoinmobiliario", "https://nexoinmobiliario.pe/sitemap-proyectos.xml")
    assert r["inmuebles"] == 2 and len({i["url"] for i in db.t["inmuebles"]}) == 2
    assert rastreador.portal_completo(db, {"tipo_cambio": 3.45}, "nexoinmobiliario", "https://nexoinmobiliario.pe/sitemap-proyectos.xml")["paginas"] == 0
