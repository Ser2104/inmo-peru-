import random
from datetime import datetime, timedelta, timezone

from inmo.config import PARAMETROS_BASE as P
from inmo.valoracion import calcular_zonas, indice_zonas, analizar
from inmo.agents.auditor import duplicados, sospechosos

AHORA = datetime.now(timezone.utc)


def mercado(n=40):
    random.seed(1)
    filas = []
    for k in range(n):
        area = random.uniform(60, 120)
        filas.append({"id": f"v{k}", "operacion": "venta", "tipo": "departamento", "departamento": "Lima", "provincia": "Lima",
                      "distrito": "Miraflores", "area_m2": area, "precio_usd": area * random.uniform(2300, 2700),
                      "primera_vez": (AHORA - timedelta(days=k)).isoformat()})
        filas.append({"id": f"a{k}", "operacion": "alquiler", "tipo": "departamento", "departamento": "Lima", "provincia": "Lima",
                      "distrito": "Miraflores", "area_m2": area, "precio_usd": area * random.uniform(11, 13),
                      "primera_vez": AHORA.isoformat()})
    return filas


def test_zonas_y_analisis():
    idx = indice_zonas(calcular_zonas(mercado()))
    z = idx[("lima", "lima", "miraflores", "departamento", "venta", "*")]
    assert 2300 < z["mediana_m2_usd"] < 2700 and z["n"] == 40
    barato = {"id": "x", "operacion": "venta", "tipo": "departamento", "departamento": "Lima", "provincia": "Lima",
              "distrito": "Miraflores", "area_m2": 90, "precio_usd": 90 * 1700}
    caro = {**barato, "id": "y", "precio_usd": 90 * 3400}
    a, b = analizar(barato, idx, {}, P), analizar(caro, idx, {}, P)
    assert a["fuente_renta"] == "comparables_distrito" and a["confianza"] == "alta"
    assert a["descuento_vs_zona"] > 0.25 and b["descuento_vs_zona"] < 0
    assert a["puntaje_total"] > b["puntaje_total"]
    assert a["veredicto"] in ("Comprar", "Negociar") and b["veredicto"] == "Descartar"
    assert set(a["detalle"]["escenarios"]) == {"pesimista", "base", "optimista"}


def test_sin_datos_usa_supuesto_y_baja_confianza():
    inm = {"id": "z", "operacion": "venta", "tipo": "casa", "departamento": "Puno", "distrito": "Juliaca", "area_m2": 150, "precio_usd": 60000}
    a = analizar(inm, {}, {}, P)
    assert a["fuente_renta"] == "supuesto" and a["confianza"] == "baja"
    assert a["veredicto"] != "Comprar"


def test_auditor():
    m = mercado(20)
    copia = {**m[0], "id": "dup", "primera_vez": AHORA.isoformat()}
    m[0]["primera_vez"] = (AHORA - timedelta(days=30)).isoformat()
    m[0]["dormitorios"] = copia["dormitorios"] = 2
    assert duplicados(m + [copia]).get("dup") == "v0"
    raro = {**m[2], "id": "raro", "precio_usd": 1000.0}
    idx = indice_zonas(calcular_zonas(m))
    assert "raro" in sospechosos(m + [raro], idx)
