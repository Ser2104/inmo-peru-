import statistics

import httpx

from . import config
from .finanzas import Supuestos, evaluar, operativo

FACTOR_DORMITORIOS = {0: 0.8, 1: 1.0, 2: 1.35, 3: 1.7}


def norm(texto):
    from .valoracion import norm as n
    return n(texto)


def dormitorios(inm):
    if inm.get("dormitorios") is not None:
        return int(inm["dormitorios"])
    area = float(inm.get("area_m2") or 0)
    if not area:
        return 1
    return 0 if area < 35 else 1 if area < 55 else 2 if area < 85 else 3 if area < 120 else 4


def indice_mercado(filas):
    grupos = {}
    for f in filas:
        if f.get("fuente") == "airroi_inmueble" or not f.get("adr_usd") or not f.get("ocupacion"):
            continue
        dep, prov, dist = norm(f.get("departamento")), norm(f.get("provincia")), norm(f.get("distrito"))
        claves = [(dep, prov or "*", dist or "*")]
        if dist:
            claves.append((dep, prov or "*", "*"))
        claves.append((dep, "*", "*"))
        for c in dict.fromkeys(claves):
            grupos.setdefault(c, []).append(f)
    salida = {}
    for clave, fs in grupos.items():
        salida[clave] = {
            "adr_usd": statistics.median(float(x["adr_usd"]) for x in fs),
            "ocupacion": statistics.median(float(x["ocupacion"]) for x in fs),
            "fuentes": len({x.get("fuente") for x in fs}),
            "n": len(fs),
        }
    return salida


def buscar_mercado(indice, inm):
    dep, prov, dist = norm(inm.get("departamento")), norm(inm.get("provincia")), norm(inm.get("distrito"))
    for nivel, clave in [("distrito", (dep, prov, dist)), ("distrito", (dep, "*", dist)), ("provincia", (dep, prov, "*")), ("departamento", (dep, "*", "*"))]:
        if clave in indice:
            return indice[clave], nivel
    return None, None


def regulacion(reglas, inm):
    r = reglas.get((norm(inm.get("departamento")), norm(inm.get("distrito"))))
    return (r["estado"], r.get("nota")) if r else ("desconocido", None)


def estimar(inm, indice, p, airroi=None):
    if airroi and airroi.get("adr_usd"):
        return {"adr_usd": float(airroi["adr_usd"]), "ocupacion": min(0.85, float(airroi["ocupacion"])), "fuente": "airroi", "nivel": "inmueble", "fuentes": 1}
    m, nivel = buscar_mercado(indice, inm)
    if not m:
        return None
    factor = FACTOR_DORMITORIOS.get(dormitorios(inm), 2.0) / 1.15
    return {"adr_usd": m["adr_usd"] * factor, "ocupacion": min(0.85, m["ocupacion"]), "fuente": "mercado", "nivel": nivel, "fuentes": m["fuentes"]}


def amoblado(inm, p):
    return max(p["amoblado_minimo_usd"], float(inm.get("area_m2") or 50) * p["amoblado_usd_m2"])


def supuestos_temporal(s_largo: Supuestos, inm, est, p):
    return Supuestos(**{**s_largo.__dict__, "adr_usd": est["adr_usd"], "ocupacion": est["ocupacion"], "amoblado_usd": amoblado(inm, p)})


def arbitraje(inm, est, p, estado_regla):
    renta = float(inm["precio_usd"])
    s = Supuestos(precio_usd=1, renta_mensual_usd=0, plusvalia=0, mantenimiento_usd=float(inm.get("mantenimiento_usd") or 0),
                  adr_usd=est["adr_usd"], ocupacion=est["ocupacion"], amoblado_usd=amoblado(inm, p))
    pp = {**p, "predial_anual": 0, "seguro_anual": 0, "reparaciones_anual": 0}
    cobrado, gastos = operativo(s, pp, 2, 0, 12, 12)
    utilidad_anual = cobrado - gastos - renta * 12
    garantia = renta * 2
    inversion = s.amoblado_usd + garantia
    retorno = utilidad_anual / inversion if inversion else None
    payback = (s.amoblado_usd / (utilidad_anual / 12)) if utilidad_anual > 0 else None
    pes_s = Supuestos(**{**s.__dict__, "ocupacion": s.ocupacion * 0.75, "adr_usd": s.adr_usd * 0.9})
    c2, g2 = operativo(pes_s, pp, 2, 0, 12, 12)
    utilidad_pes = c2 - g2 - renta * 12
    puntaje = max(0.0, min(10.0, 5 + (retorno or -1) * 5 + (1 if utilidad_pes > 0 else -2)))
    riesgos = ["Necesitas autorización escrita del dueño para subarrendar por días",
               "El reglamento interno del edificio puede prohibir el alquiler por días"]
    if estado_regla in ("restringido", "prohibido"):
        riesgos.insert(0, f"Alquiler por días {estado_regla} en este distrito")
        puntaje = min(puntaje, 3.0)
    if utilidad_pes <= 0:
        riesgos.append("Con menos turistas (escenario pesimista) pierdes dinero")
    veredicto = "Buena oportunidad" if puntaje >= 7.5 else "Evaluar" if puntaje >= 6 else "No conviene"
    return {
        "inmueble_id": inm.get("id"),
        "renta_usd": round(renta, 2),
        "ingreso_temporal_mensual_usd": round(cobrado / 12, 2),
        "utilidad_mensual_usd": round(utilidad_anual / 12, 2),
        "inversion_usd": round(inversion, 2),
        "retorno_anual": retorno,
        "payback_meses": round(payback, 1) if payback else None,
        "puntaje": round(puntaje, 2),
        "veredicto": veredicto,
        "confianza": "media" if est["nivel"] == "distrito" and est["fuentes"] >= 2 else "baja",
        "riesgos": riesgos,
        "detalle": {"adr_usd": round(est["adr_usd"], 2), "ocupacion": est["ocupacion"], "nivel": est["nivel"],
                    "utilidad_mensual_pesimista_usd": round(utilidad_pes / 12, 2), "amoblado_usd": s.amoblado_usd, "regulacion": estado_regla},
    }


def airroi_estimar(inm):
    if not config.AIRROI_API_KEY:
        return None
    params = {"bedrooms": max(0, dormitorios(inm)), "baths": max(1, int(inm.get("banos") or 1)), "guests": max(2, dormitorios(inm) * 2), "currency": "usd"}
    if inm.get("lat") and inm.get("lng"):
        params.update(lat=inm["lat"], lng=inm["lng"])
    elif inm.get("direccion"):
        params["address"] = f"{inm['direccion']}, {inm.get('distrito') or ''}, {inm.get('departamento') or ''}, Peru"
    else:
        return None
    r = httpx.get("https://api.airroi.com/calculator/estimate", params=params, headers={"x-api-key": config.AIRROI_API_KEY}, timeout=60)
    r.raise_for_status()
    return leer_airroi(r.json())


def _buscar(d, *nombres):
    for k, v in d.items():
        if any(n in k.lower() for n in nombres) and isinstance(v, (int, float)):
            return float(v)
    return None


def leer_airroi(datos):
    adr = _buscar(datos, "average_daily_rate", "adr")
    occ = _buscar(datos, "occupancy")
    perc = datos.get("percentiles") or {}
    if adr is None and isinstance(perc.get("average_daily_rate") or perc.get("adr"), dict):
        adr = (perc.get("average_daily_rate") or perc.get("adr")).get("p50")
    if occ is None and isinstance(perc.get("occupancy"), dict):
        occ = perc["occupancy"].get("p50")
    if adr is None or occ is None:
        return None
    return {"adr_usd": adr, "ocupacion": occ / 100 if occ > 1 else occ}
