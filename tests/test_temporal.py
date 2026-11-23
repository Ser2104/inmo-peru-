from inmo import temporal as tmp
from inmo.agents import temporal as agente
from inmo.config import PARAMETROS_BASE as P
from inmo.finanzas import Supuestos, evaluar
from inmo.valoracion import analizar
from tests.fake_db import FakeDB
from tests.test_valoracion import mercado
from inmo.valoracion import calcular_zonas, indice_zonas

MERCADO = [{"departamento": "Lima", "provincia": "Lima", "distrito": "Barranco", "adr_usd": 70, "ocupacion": 0.55, "fuente": "a"},
           {"departamento": "Lima", "provincia": "Lima", "distrito": "Barranco", "adr_usd": 80, "ocupacion": 0.65, "fuente": "b"},
           {"departamento": "Lima", "provincia": "Lima", "distrito": "Miraflores", "adr_usd": 75, "ocupacion": 0.6, "fuente": "a"}]


def test_finanzas_temporal_cobra_mas_pero_gasta_mas():
    largo = evaluar(Supuestos(120000, 600, 0.03, 60), P)
    dias = evaluar(Supuestos(120000, 600, 0.03, 60, adr_usd=75, ocupacion=0.6, amoblado_usd=5000), P)
    assert dias["ingreso_bruto_anual"] == 75 * 365 * 0.6
    assert dias["inversion_inicial"] - largo["inversion_inicial"] == 5000
    margen = lambda r: r["flujo_mensual_usd"] * 12 / r["ingreso_bruto_anual"]
    assert margen(dias) < margen(largo)


def test_estimar_por_distrito_y_dormitorios():
    idx = tmp.indice_mercado(MERCADO)
    uno = tmp.estimar({"departamento": "Lima", "provincia": "Lima", "distrito": "Barranco", "dormitorios": 1}, idx, P)
    dos = tmp.estimar({"departamento": "Lima", "provincia": "Lima", "distrito": "Barranco", "dormitorios": 2}, idx, P)
    assert uno["nivel"] == "distrito" and uno["fuentes"] == 2 and abs(uno["ocupacion"] - 0.6) < 1e-9
    assert dos["adr_usd"] > uno["adr_usd"]
    otro = tmp.estimar({"departamento": "Lima", "provincia": "Lima", "distrito": "Lince"}, idx, P)
    assert otro["nivel"] == "provincia"
    assert tmp.estimar({"departamento": "Puno", "distrito": "Juliaca"}, idx, P) is None


def _inm(distrito):
    return {"id": "x", "operacion": "venta", "tipo": "departamento", "departamento": "Lima", "provincia": "Lima",
            "distrito": distrito, "area_m2": 45, "dormitorios": 1, "precio_usd": 45 * 2500}


def test_elige_temporal_solo_si_esta_permitido():
    idx = indice_zonas(calcular_zonas(mercado()))
    temporal = {"indice": tmp.indice_mercado(MERCADO + [{**MERCADO[2], "distrito": "Barranco", "fuente": "c"}]), "reglas": {("lima", "miraflores"): {"estado": "restringido", "nota": "ordenanza"}}}
    barranco = analizar(_inm("Barranco"), idx, {}, P, temporal=temporal)
    miraflores = analizar(_inm("Miraflores"), idx, {}, P, temporal=temporal)
    assert barranco["estrategia"] == "temporal" and barranco["tir_10_temporal"] > barranco["detalle"]["comparacion"]["largo_plazo"]["tir_10"]
    assert miraflores["estrategia"] == "largo_plazo" and miraflores["tir_10_temporal"] is not None
    assert any("restringido" in r for r in miraflores["riesgos"])


def test_arbitraje():
    idx = tmp.indice_mercado(MERCADO)
    barato = tmp.arbitraje({"id": "a", "precio_usd": 450, "area_m2": 45, "dormitorios": 1, "distrito": "Barranco"}, tmp.estimar({"departamento": "Lima", "provincia": "Lima", "distrito": "Barranco", "dormitorios": 1}, idx, P), P, "desconocido")
    caro = tmp.arbitraje({"id": "b", "precio_usd": 1300, "area_m2": 45, "dormitorios": 1}, tmp.estimar({"departamento": "Lima", "provincia": "Lima", "distrito": "Barranco", "dormitorios": 1}, idx, P), P, "desconocido")
    assert barato["utilidad_mensual_usd"] > 0 and barato["payback_meses"] > 0
    assert caro["utilidad_mensual_usd"] < 0 and caro["veredicto"] == "No conviene"
    bloqueado = tmp.arbitraje({"id": "c", "precio_usd": 450, "area_m2": 45}, tmp.estimar({"departamento": "Lima", "provincia": "Lima", "distrito": "Barranco", "dormitorios": 1}, idx, P), P, "prohibido")
    assert bloqueado["puntaje"] <= 3


def test_agente_guarda_datos_y_regulacion():
    db = FakeDB()
    datos = [{"fuente": "bnbcalc", "adr": 243, "moneda_adr": "PEN", "ocupacion": 34, "ingreso_anual": None, "url": "https://bnbcalc.com"},
             {"fuente": "absurdo", "adr": 99999, "ocupacion": 0.5},
             {"fuente": "solo ingreso", "ingreso_anual": 10500, "moneda_ingreso": "USD", "ocupacion": 0.5},
             {"tipo": "regulacion", "estado": "restringido", "nota": "ordenanza"}]
    n, regla = agente.guardar(db, ("Lima", "Lima", "Miraflores"), datos, 3.44)
    assert n == 2 and regla == "restringido"
    bnb = next(f for f in db.t["mercado_temporal"] if f["fuente"] == "bnbcalc")
    assert abs(bnb["adr_usd"] - 243 / 3.44) < 0.01 and bnb["ocupacion"] == 0.34
    solo = next(f for f in db.t["mercado_temporal"] if f["fuente"] == "solo ingreso")
    assert abs(solo["adr_usd"] - 10500 / (365 * 0.5)) < 0.01
    assert db.t["regulacion_temporal"][0]["estado"] == "restringido"


def test_regulacion_manual_no_se_pisa():
    db = FakeDB()
    db.upsert("regulacion_temporal", {"departamento": "lima", "distrito": "miraflores", "estado": "restringido", "fuente": "https://dplnews.com"})
    agente.guardar(db, ("Lima", "Lima", "Miraflores"), [{"tipo": "regulacion", "estado": "permitido"}], 3.44)
    assert db.t["regulacion_temporal"][0]["estado"] == "restringido"


def test_leer_airroi():
    assert tmp.leer_airroi({"average_daily_rate": 80.0, "occupancy": 62}) == {"adr_usd": 80.0, "ocupacion": 0.62}
    assert tmp.leer_airroi({"percentiles": {"average_daily_rate": {"p50": 70}, "occupancy": {"p50": 0.5}}}) == {"adr_usd": 70, "ocupacion": 0.5}
    assert tmp.leer_airroi({"x": 1}) is None
