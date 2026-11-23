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
