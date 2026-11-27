from datetime import datetime, timezone

from inmo import config
from inmo.valoracion import analizar, calcular_zonas, grupos_parecidos, indice_zonas


def _t(i, precio, area=200, dist="Cerro Colorado"):
    return {"id": f"t{i}", "tipo": "terreno", "operacion": "venta", "estado": "terminado", "departamento": "Arequipa", "provincia": "Arequipa",
            "distrito": dist, "area_m2": area, "precio_usd": precio, "primera_vez": datetime.now(timezone.utc).isoformat()}


def test_terreno_barato_y_caro():
    p = {**config.PARAMETROS_BASE, "tipo_cambio": 3.7, "uit_soles": 5350}
    zona = [_t(i, 40000 + i * 500) for i in range(12)]
    idx, g = indice_zonas(calcular_zonas(zona)), grupos_parecidos(zona)
    barato = analizar(_t("b", 33000), idx, {}, p, grupos=g)
    caro = analizar(_t("c", 60000), idx, {}, p, grupos=g)
    assert barato["estrategia"] == "terreno" and barato["descuento_vs_zona"] > 0.1
    assert barato["puntaje_total"] > caro["puntaje_total"] and caro["veredicto"] == "Descartar"
    assert barato["veredicto"] in ("Comprar", "Revisar a mano", "Negociar")
