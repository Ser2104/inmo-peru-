from inmo.config import PARAMETROS_BASE as P
from inmo.finanzas import Supuestos, cuota_hipoteca, saldo_hipoteca, tir, van, evaluar, precio_maximo, costos_compra


def test_cuota_y_saldo():
    c = cuota_hipoteca(100000, 0.085, 20)
    assert 840 < c < 860
    assert saldo_hipoteca(100000, 0.085, 20, 0) == 100000
    assert saldo_hipoteca(100000, 0.085, 20, 240) < 1


def test_tir_van():
    assert abs(tir([-100, 10, 10, 110]) - 0.10) < 1e-6
    assert abs(van([-100, 110], 0.10)) < 1e-9
    assert tir([-100, -5]) is None


def test_alcabala_solo_reventa():
    assert costos_compra(200000, True, P) == 2000
    assert costos_compra(200000, False, P) > 2000


def test_evaluar_y_precio_maximo():
    s = Supuestos(precio_usd=150000, renta_mensual_usd=700, plusvalia=0.03)
    r = evaluar(s, P)
    assert 0.05 < r["rentabilidad_bruta"] < 0.06
    assert r["tir_10"] > r["tir_2"]
    pm = precio_maximo(s, P)
    assert pm < 150000
    assert abs(tir(evaluar(Supuestos(**{**s.__dict__, "precio_usd": pm}), P)["flujos_10"]) - P["tasa_descuento"]) < 0.005


def test_en_planos_retrasa_renta():
    hoy = evaluar(Supuestos(150000, 700, 0.03), P)
    planos = evaluar(Supuestos(150000, 700, 0.03, meses_hasta_renta=24, nuevo=True), P)
    assert planos["tir_10"] < hoy["tir_10"] + 0.01
    assert planos["flujos_10"][1] < 0


def test_hipoteca_reduce_inversion_inicial():
    p = {**P, "cuota_inicial": 0.2}
    r = evaluar(Supuestos(150000, 700, 0.03), p)
    assert r["inversion_inicial"] < 40000
    assert r["cuota_hipoteca_mensual"] > 0
