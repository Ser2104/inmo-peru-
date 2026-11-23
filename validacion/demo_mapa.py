"""Genera mapa/demo.json con los proyectos reales de la validación, ubicados en el centro aproximado de su distrito."""
import json
from pathlib import Path

from inmo import temporal as tmp
from inmo.agents.ubicador import desplazar
from validacion.airbnb_real import ADR_USD
from validacion.mercado_real import PARAMETROS_BASE, PER, PROYECTOS, M2_SOLES, TC, indice
from inmo.valoracion import analizar

CENTROS = {"San Isidro": (-12.097, -77.036), "Surquillo": (-12.113, -77.012), "Jesús María": (-12.077, -77.047), "La Victoria": (-12.072, -77.016),
           "Santiago de Surco": (-12.144, -76.991), "Lince": (-12.085, -77.036), "Cercado de Lima": (-12.046, -77.043), "Chorrillos": (-12.170, -77.015)}
CAMPOS = ["precio_usd", "veredicto", "confianza", "puntaje_total", "puntaje_corto", "puntaje_mediano", "puntaje_largo", "estrategia", "tir_10",
          "tir_10_temporal", "renta_mensual_usd", "flujo_mensual_usd", "flujo_mensual_temporal", "precio_max_recomendado", "descuento_vs_zona", "rentabilidad_neta"]


def main():
    p = {**PARAMETROS_BASE, "tipo_cambio": TC}
    temporal = {"indice": {("lima", "lima", tmp.norm(d)): {"adr_usd": ADR_USD * 1.15, "ocupacion": occ, "fuentes": 2, "n": 2}
                           for d, occ in CENTROS.items() for occ in [0.55 if d in ("Surquillo", "Lince", "Cercado de Lima") else 0.40]}, "reglas": {}}
    salida = []
    casos = [(n, s, a, d, "preventa") for n, s, a, d in PROYECTOS]
    casos += [(f"Departamento usado en {d}", M2_SOLES[d] * a * f, a, d, "terminado") for d, a, f in
              [("Lince", 65, 0.72), ("Surquillo", 50, 0.80), ("San Isidro", 80, 0.95), ("Jesús María", 70, 0.85), ("Santiago de Surco", 90, 1.0)]]
    casos += [("Remate judicial departamento", M2_SOLES["La Victoria"] * 75 * 0.6, 75, "La Victoria", "remate")]
    for k, (nombre, soles, area, distrito, est) in enumerate(casos):
        inm = {"id": f"demo-{k}", "titulo": nombre, "operacion": "venta", "tipo": "departamento", "estado": est, "departamento": "Lima",
               "provincia": "Lima", "distrito": distrito, "area_m2": area, "dormitorios": 1 if area < 55 else 2 if area < 85 else 3, "precio_usd": soles / TC}
        a = analizar(inm, indice(), PER, p, temporal=temporal)
        lat, lng = desplazar(*CENTROS[distrito], inm["id"], 900)
        salida.append({**inm, "lat": lat, "lng": lng, "ubicacion_precision": "distrito", "url": "https://nexoinmobiliario.pe" if est == "preventa" else "",
                       **{c: a[c] for c in CAMPOS}, "_analisis": {"riesgos": a["riesgos"], "detalle": a["detalle"], "renta_mensual_usd": a["renta_mensual_usd"]}})
    arb = []
    for k, (distrito, renta, occ) in enumerate([("Surquillo", 480, 0.62), ("Lince", 520, 0.55), ("San Isidro", 650, 0.45), ("Cercado de Lima", 380, 0.6)]):
        inm = {"id": f"arb-{k}", "titulo": f"Departamento en alquiler en {distrito}", "precio_usd": renta, "area_m2": 45, "dormitorios": 1, "mantenimiento_usd": 60,
               "departamento": "Lima", "provincia": "Lima", "distrito": distrito}
        r = tmp.arbitraje(inm, {"adr_usd": ADR_USD, "ocupacion": occ, "nivel": "distrito", "fuentes": 2}, p, "desconocido")
        lat, lng = desplazar(*CENTROS[distrito], inm["id"], 900)
        arb.append({**inm, **r, "lat": lat, "lng": lng, "ubicacion_precision": "distrito", "url": ""})
    Path("mapa/demo.json").write_text(json.dumps({"inmuebles": salida, "arbitrajes": arb}, ensure_ascii=False, default=str))
    print(len(salida), "inmuebles,", len(arb), "arbitrajes")
    for i in salida:
        print(f"{i['titulo'][:32]:32} {i['veredicto']:15} {i['estrategia']:12} {i['puntaje_total']}")


if __name__ == "__main__":
    main()
