"""Alquiler por días vs. tradicional con datos reales de Lima (2026).

- Tarifa promedio Lima: S/243 por noche, ocupación 34% (bnbcalc, mayo 2026)
- Ocupación mediana Miraflores: 66% (Airbtics, nov 2024 - oct 2025)
- Ingreso promedio por anuncio: US$10.5K al año (AirDNA, oct 2026)
"""
from inmo import temporal as tmp
from inmo.valoracion import analizar
from validacion.mercado_real import PARAMETROS_BASE, PER, M2_SOLES, TC, indice

ADR_USD = 243 / TC


def main():
    p = {**PARAMETROS_BASE, "tipo_cambio": TC}
    print(f"{'Distrito':12} {'Tamaño':10} {'Ocup.':>6} {'Ingreso días':>12} {'TIR trad.':>9} {'TIR días':>9} {'Elegida':>12}")
    for distrito in ("San Isidro", "Surquillo", "Lince"):
        for dorm, area in ((1, 45), (2, 70)):
            for occ in (0.34, 0.45, 0.55, 0.66):
                inm = {"id": "x", "operacion": "venta", "tipo": "departamento", "estado": "terminado", "departamento": "Lima", "provincia": "Lima",
                       "distrito": distrito, "area_m2": area, "dormitorios": dorm, "precio_usd": M2_SOLES[distrito] / TC * area}
                t = {"indice": {("lima", "lima", tmp.norm(distrito)): {"adr_usd": ADR_USD * 1.15, "ocupacion": occ, "fuentes": 2, "n": 2}}, "reglas": {}}
                a = analizar(inm, indice(), PER, p, temporal=t)
                c = a["detalle"]["comparacion"]
                print(f"{distrito:12} {dorm} dorm {area}m² {occ:6.0%} {c['temporal']['ingreso_bruto_anual']:12,.0f} {c['largo_plazo']['tir_10']:9.1%} {c['temporal']['tir_10']:9.1%} {a['estrategia']:>12}")
    print()
    print("Arbitraje (alquilar a largo plazo y operar por días), 1 dorm 45 m²:")
    for distrito in ("San Isidro", "Surquillo"):
        renta = M2_SOLES[distrito] / TC * 45 / PER[tmp.norm(distrito)] / 12
        for occ in (0.34, 0.45, 0.55, 0.66):
            est = {"adr_usd": ADR_USD, "ocupacion": occ, "nivel": "distrito", "fuentes": 2}
            r = tmp.arbitraje({"id": "x", "precio_usd": renta, "area_m2": 45, "dormitorios": 1, "mantenimiento_usd": 60}, est, p, "desconocido")
            print(f"  {distrito:11} alquiler US$ {renta:4.0f}/mes, ocupación {occ:.0%}: ganancia US$ {r['utilidad_mensual_usd']:6,.0f}/mes, "
                  f"pesimista US$ {r['detalle']['utilidad_mensual_pesimista_usd']:6,.0f}, recuperas amoblado en {r['payback_meses'] or '—'} meses → {r['veredicto']}")


if __name__ == "__main__":
    main()
