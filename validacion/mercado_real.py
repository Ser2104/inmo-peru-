"""Prueba del motor con datos reales de Lima (noviembre 2026).

Fuentes:
- PER por distrito: BCRP, T1-2026 (series PD41940PQ a PD41952PQ)
- Precio de venta por m² por distrito: Urbania (abril 2026 y nov. 2025)
- Proyectos: Nexo Inmobiliario, sección destacados, 22/11/2026 (precio "desde" y área mínima)
- Tipo de cambio: BCRP, 3.441 al 19/11/2026
"""
from inmo.config import PARAMETROS_BASE
from inmo.valoracion import analizar, norm

TC = 3.441
PER = {"barranco": 17.04, "jesus maria": 17.52, "la molina": 15.52, "lince": 15.07, "magdalena del mar": 15.39,
       "miraflores": 17.78, "pueblo libre": 16.91, "san borja": 17.58, "san isidro": 16.70, "san miguel": 17.45,
       "santiago de surco": 18.15, "surquillo": 14.97}
M2_SOLES = {"San Isidro": 9268, "Jesús María": 7711, "Lince": 7703, "Surquillo": 6873, "Santiago de Surco": 6690,
            "La Victoria": 6981, "Cercado de Lima": 6253, "Chorrillos": 5718}
PROYECTOS = [
    ("Tree San Isidro", 360699, 39.81, "San Isidro"),
    ("Aurora Loft21", 358000, 40.24, "Surquillo"),
    ("Liguria", 349420, 40.68, "Jesús María"),
    ("Hercelles", 383520, 53.71, "La Victoria"),
    ("Look&Feel Etapa 2", 440322, 47.72, "Santiago de Surco"),
    ("Lombardia", 498145, 63.78, "Lince"),
    ("Cristobal", 326250, 47.90, "Santiago de Surco"),
    ("RDC 525", 730000, 90.00, "Santiago de Surco"),
    ("Monte Carmelo 551", 750300, 100.18, "Santiago de Surco"),
    ("Nova Colonial", 259560, 42.00, "Cercado de Lima"),
    ("LIV 360", 199000, 27.32, "Chorrillos"),
]


def indice():
    idx = {}
    for d, m2 in M2_SOLES.items():
        idx[("lima", "lima", norm(d), "departamento", "venta", "*")] = {"n": 100, "mediana_m2_usd": m2 / TC, "plusvalia_anual": None}
    return idx


def main(p=None):
    p = {**PARAMETROS_BASE, "tipo_cambio": TC, **(p or {})}
    filas = []
    for nombre, soles, area, distrito in PROYECTOS:
        inm = {"id": nombre, "operacion": "venta", "tipo": "departamento", "estado": "preventa", "departamento": "Lima",
               "provincia": "Lima", "distrito": distrito, "area_m2": area, "precio_usd": soles / TC}
        a = analizar(inm, indice(), PER, p)
        filas.append((nombre, distrito, a))
    return filas


if __name__ == "__main__":
    import sys
    p = {"cuota_inicial": 0.2} if "--hipoteca" in sys.argv else {}
    print(f"{'Proyecto':20} {'Distrito':18} {'US$':>8} {'vs zona':>8} {'Alq/mes':>8} {'Bruta':>6} {'Neta':>6} {'TIR10':>6} {'Pes.':>6} {'Máx US$':>8} {'C/M/L':>14} Veredicto")
    for n, d, a in main(p):
        esc = a["detalle"]["escenarios"]["pesimista"]["tir_10"]
        print(f"{n:20} {d:18} {a['precio_usd']:8,.0f} {a['descuento_vs_zona']:+8.1%} {a['renta_mensual_usd']:8,.0f} "
              f"{a['rentabilidad_bruta']:6.1%} {a['rentabilidad_neta']:6.1%} {a['tir_10']:6.1%} {esc or 0:6.1%} "
              f"{a['precio_max_recomendado']:8,.0f} {a['puntaje_corto']:4.1f}/{a['puntaje_mediano']:4.1f}/{a['puntaje_largo']:4.1f} {a['veredicto']} ({a['confianza']})")
