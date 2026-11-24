import math
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone

from .finanzas import Supuestos, evaluar, escenarios, precio_maximo
from . import temporal as tmp

VERSION = "1.0"


def norm(texto):
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return " ".join(t.lower().replace("-", " ").split())


def _percentil(valores, q):
    v = sorted(valores)
    k = (len(v) - 1) * q
    i = int(k)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * (k - i)


def _fecha(x):
    if isinstance(x, datetime):
        return x
    return datetime.fromisoformat(str(x).replace("Z", "+00:00"))


def calcular_zonas(inmuebles, ahora=None):
    ahora = ahora or datetime.now(timezone.utc)
    grupos = {}
    for i in inmuebles:
        if not i.get("activo", True) or i.get("duplicado_de") or i.get("sospechoso"):
            continue
        if not i.get("precio_usd") or not i.get("area_m2") or float(i["area_m2"]) < 10:
            continue
        m2 = float(i["precio_usd"]) / float(i["area_m2"])
        dep, prov, dist = norm(i.get("departamento")), norm(i.get("provincia")), norm(i.get("distrito"))
        for clave in [(dep, prov, dist), (dep, prov, "*"), (dep, "*", "*")]:
            for seg in ("*", segmento(i)):
                grupos.setdefault((*clave, i.get("tipo") or "*", i["operacion"], seg), []).append((m2, i.get("primera_vez")))
    filas = []
    for (dep, prov, dist, tipo, op, seg), datos in grupos.items():
        valores = [d[0] for d in datos]
        plusvalia = None
        if op == "venta":
            recientes = [m for m, f in datos if f and _fecha(f) > ahora - timedelta(days=120)]
            antiguos = [m for m, f in datos if f and ahora - timedelta(days=500) < _fecha(f) <= ahora - timedelta(days=365)]
            if len(recientes) >= 10 and len(antiguos) >= 10:
                plusvalia = statistics.median(recientes) / statistics.median(antiguos) - 1
        filas.append({
            "departamento": dep, "provincia": prov, "distrito": dist, "tipo": tipo, "operacion": op, "segmento": seg,
            "n": len(valores),
            "mediana_m2_usd": round(statistics.median(valores), 2),
            "p25_m2_usd": round(_percentil(valores, 0.25), 2),
            "p75_m2_usd": round(_percentil(valores, 0.75), 2),
            "plusvalia_anual": plusvalia,
        })
    return filas


def segmento(inm):
    return "nuevo" if inm.get("estado") in ("en_planos", "preventa") else "usado"


def indice_zonas(filas):
    return {(f["departamento"], f["provincia"], f["distrito"], f["tipo"], f["operacion"], f.get("segmento") or "*"): f for f in filas}


def factor_tamano(area, referencia=70):
    return (max(area, 15) / referencia) ** -0.15 if area else 1.0


def buscar_zona(indice, inm, operacion, minimo, mismo_segmento=False, hasta="provincia"):
    dep, prov, dist = norm(inm.get("departamento")), norm(inm.get("provincia")), norm(inm.get("distrito"))
    tipo = inm.get("tipo") or "*"
    segmentos = [segmento(inm)] if mismo_segmento else [segmento(inm), "*"]
    niveles = [("distrito", (dep, prov, dist)), ("provincia", (dep, prov, "*")), ("departamento", (dep, "*", "*"))]
    niveles = niveles[: [n for n, _ in niveles].index(hasta) + 1]
    for nivel, clave in niveles:
        for seg in segmentos:
            z = indice.get((*clave, tipo, operacion, seg))
            if z and z["n"] >= minimo:
                return z, nivel if seg != "*" or segmento(inm) == "usado" else f"{nivel} (todos los segmentos)"
    return None, None


def grupos_parecidos(inmuebles):
    g = {}
    for i in inmuebles:
        if not i.get("activo", True) or i.get("duplicado_de") or i.get("sospechoso") or not i.get("precio_usd") or float(i.get("area_m2") or 0) < 10:
            continue
        g.setdefault((norm(i.get("departamento")), norm(i.get("provincia")), norm(i.get("distrito")), i.get("tipo"), i["operacion"]), []).append(i)
    return g


def parecidos(inm, grupos, operacion, maximo=8):
    area, dorm = float(inm.get("area_m2") or 0), inm.get("dormitorios")
    if not area or not grupos:
        return []
    clave = (norm(inm.get("departamento")), norm(inm.get("provincia")), norm(inm.get("distrito")), inm.get("tipo"), operacion)
    c = [x for x in grupos.get(clave, []) if x.get("id") != inm.get("id") and 0.75 <= float(x["area_m2"]) / area <= 1.33
         and (not dorm or not x.get("dormitorios") or abs(int(x["dormitorios"]) - int(dorm)) <= 1)]
    if operacion == "venta":
        mismo = [x for x in c if segmento(x) == segmento(inm)]
        c = mismo if len(mismo) >= 5 else c
    c.sort(key=lambda x: abs(math.log(float(x["area_m2"]) / area)))
    return c[:maximo]


def _resumen(lista):
    return [{"url": x.get("url"), "precio_usd": float(x["precio_usd"]), "area_m2": float(x["area_m2"]), "dormitorios": x.get("dormitorios")} for x in lista]


def estimar_renta(inm, indice, per_distrito, p):
    area = float(inm.get("area_m2") or 0)
    if inm.get("tipo") == "terreno":
        return 0.0, "terreno", 0
    z, nivel = buscar_zona(indice, inm, "alquiler", p["min_comparables"])
    if z and area:
        return z["mediana_m2_usd"] * area * factor_tamano(area) * p["ajuste_renta"], f"comparables_{nivel}", z["n"]
    zv, _ = buscar_zona(indice, inm, "venta", p["min_comparables"])
    base = zv["mediana_m2_usd"] * area * factor_tamano(area) if zv and area else float(inm["precio_usd"])
    d = norm(inm.get("distrito"))
    per = next((v for k, v in per_distrito.items() if d and (k == d or k.startswith(d) or d.startswith(k))), None)
    if per and norm(inm.get("departamento")) in ("lima", "callao"):
        return base / per / 12, "bcrp_per", 0
    rd = (p.get("rentabilidad_por_departamento") or {}).get(norm(inm.get("departamento")))
    if rd:
        return base * rd / 12, "rentabilidad_departamento", 0
    return base * p["rentabilidad_bruta_default"] / 12, "supuesto", 0


def _limitar(x, a=0.0, b=10.0):
    return max(a, min(b, x))


def puntaje_tir(t, meta):
    return 0.0 if t is None else round(_limitar(5 + (t - meta) * 100), 2)


def meses_hasta_renta(inm, ahora=None):
    if inm.get("estado") not in ("en_planos", "preventa"):
        return 0
    if inm.get("fecha_entrega"):
        ahora = ahora or datetime.now(timezone.utc)
        entrega = datetime.fromisoformat(str(inm["fecha_entrega"])).replace(tzinfo=timezone.utc)
        return max(0, (entrega.year - ahora.year) * 12 + entrega.month - ahora.month) + 2
    return 24


def analizar(inm, indice, per_distrito, p, renta_usuario=None, temporal=None, grupos=None):
    riesgos = []
    precio, area = float(inm["precio_usd"]), float(inm.get("area_m2") or 0)
    alq = parecidos(inm, grupos, "alquiler") if inm.get("tipo") != "terreno" else []
    ven = parecidos(inm, grupos, "venta")
    if renta_usuario:
        renta, fuente_renta, n_alq = float(renta_usuario), "usuario", 0
    elif len(alq) >= 5:
        renta = statistics.median(float(x["precio_usd"]) / float(x["area_m2"]) for x in alq) * area * p["ajuste_renta"]
        fuente_renta, n_alq = "parecidos", len(alq)
    else:
        renta, fuente_renta, n_alq = estimar_renta(inm, indice, per_distrito, p)
    zv, nivel_v = buscar_zona(indice, inm, "venta", p["min_comparables"])
    descuento = None
    if len(ven) >= 5:
        descuento = 1 - (precio / area) / statistics.median(float(x["precio_usd"]) / float(x["area_m2"]) for x in ven)
    elif zv and area:
        descuento = 1 - (precio / area) / (zv["mediana_m2_usd"] * factor_tamano(area))
    plusvalia = p["plusvalia_default"]
    if zv and zv.get("plusvalia_anual") is not None and zv["n"] >= 30:
        plusvalia = _limitar(float(zv["plusvalia_anual"]), -0.05, 0.12)
    elif p.get("plusvalia_bcrp") is not None and norm(inm.get("departamento")) in ("lima", "callao"):
        plusvalia = _limitar(float(p["plusvalia_bcrp"]), -0.05, 0.12)

    nuevo = inm.get("estado") in ("en_planos", "preventa")
    zseg, _ = buscar_zona(indice, inm, "venta", p["min_comparables"], mismo_segmento=True)
    mercado = 0.0
    if zseg and area:
        mercado = zseg["mediana_m2_usd"] * area * factor_tamano(area) * (1 - p.get("descuento_negociacion", 0.07))
        mercado = min(max(mercado, precio * 0.7), precio * 1.3)
    elif nuevo:
        mercado = precio * (1 - p.get("descuento_negociacion", 0.07))
    s = Supuestos(
        precio_usd=precio,
        renta_mensual_usd=renta,
        plusvalia=plusvalia,
        mantenimiento_usd=float(inm.get("mantenimiento_usd") or 0),
        meses_hasta_renta=meses_hasta_renta(inm),
        nuevo=nuevo,
        valor_mercado=mercado,
        pago_diferido=(1 - p.get("pago_inicial_preventa", 0.2)) if nuevo else 0.0,
    )
    r = evaluar(s, p)
    esc = escenarios(s, p)
    s_largo, r_largo = s, r
    estrategia, r_temp, est, regla, nota_regla = "largo_plazo", None, None, "desconocido", None
    if temporal:
        est = tmp.estimar(inm, temporal.get("indice") or {}, p, (temporal.get("airroi") or {}).get(inm.get("id")))
        regla, nota_regla = tmp.regulacion(temporal.get("reglas") or {}, inm)
        if est:
            s_temp = tmp.supuestos_temporal(s, inm, est, p)
            r_temp = evaluar(s_temp, p)
            mejor = (r_temp["tir_10"] or -1) > (r_largo["tir_10"] or -1) + p["prima_riesgo_temporal"]
            if mejor and regla not in ("restringido", "prohibido"):
                estrategia, s, r = "temporal", s_temp, r_temp
                esc = escenarios(s, p)

    meta = p["tasa_descuento"]
    descuento_util = descuento if (zseg or not nuevo) else 0
    corto = 5 + (descuento_util or 0) * 12 + ((r["rentabilidad_neta"] or 0) - 0.04) * 60 + (0.5 if r["flujo_mensual_usd"] > 0 else -1.5)
    if s.meses_hasta_renta:
        corto -= min(3, s.meses_hasta_renta / 12)
    corto = round(_limitar(corto), 2)
    mediano = puntaje_tir(r["tir_5"], meta)
    largo = puntaje_tir(r["tir_10"], meta)
    pes = esc["pesimista"]["tir_10"]
    if pes is not None and pes < 0:
        largo = round(max(0, largo - 1.5), 2)
        riesgos.append("En el escenario pesimista se pierde dinero a 10 años")
    total = round(0.25 * corto + 0.35 * mediano + 0.40 * largo, 2)

    if not area:
        riesgos.append("Sin área: no se puede comparar el precio por m²")
    if fuente_renta == "supuesto":
        riesgos.append("Alquiler estimado con un supuesto general: faltan datos de alquileres en la zona")
    if not zv:
        riesgos.append("Pocos inmuebles parecidos en venta en la zona")
    elif nivel_v != "distrito":
        riesgos.append(f"Comparado a nivel de {nivel_v}")
    if nuevo and not zseg:
        riesgos.append("Sin otros proyectos nuevos para comparar: el precio se compara con departamentos usados")
    if s.meses_hasta_renta:
        riesgos.append(f"Proyecto en planos: renta en ~{s.meses_hasta_renta} meses; revisar la constructora y la garantía bancaria")
    if descuento is not None and descuento > 0.30:
        riesgos.append("Precio muy por debajo de la zona: puede ser una gran oportunidad o tener un problema (antigüedad, estado, papeles, cargas). Verifica antes")
    if inm.get("estado") == "remate":
        riesgos.append("Remate: revisar deudas, ocupantes y proceso judicial")
    if inm.get("sospechoso"):
        riesgos.append(f"Dato sospechoso: {inm['sospechoso']}")
    if r_temp and regla in ("restringido", "prohibido"):
        riesgos.append(f"Alquiler por días {regla} en el distrito: {nota_regla or 'revisar la norma municipal'}")
    if estrategia == "temporal":
        riesgos.append("Estrategia por días: revisa que el reglamento interno del edificio lo permita y ten en cuenta que la ocupación varía por temporada")
        if est["nivel"] != "distrito" or est["fuentes"] < 2:
            riesgos.append(f"Datos de Airbnb solo a nivel de {est['nivel']} y de {est['fuentes']} fuente(s)")

    if (fuente_renta == "parecidos" or inm.get("tipo") == "terreno") and len(ven) >= 5 or fuente_renta.startswith("comparables_distrito") and (nivel_v or "").startswith("distrito") and n_alq >= 15 and len(ven) >= 5:
        confianza = "alta"
    elif fuente_renta not in ("supuesto", "rentabilidad_departamento") and zv:
        confianza = "media"
    else:
        confianza = "baja"
    if estrategia == "temporal" and confianza == "alta" and (est["nivel"] != "distrito" or est["fuentes"] < 2):
        confianza = "media"

    pmax = precio_maximo(s, p)
    bruta = r["rentabilidad_bruta"] or 0
    if bruta > 0.15:
        riesgos.append(f"Alquiler estimado muy alto para el precio ({bruta:.0%} al año): probable dato mal leído")
    desde = " desde " in f" {(inm.get('titulo') or '').lower()} " or "/proyecto" in (inm.get("url") or "")
    if desde:
        riesgos.append("Precio 'desde': corresponde a la unidad más barata del proyecto; confirma área y precio de la unidad que te interesa")
    if inm.get("tipo") == "terreno":
        riesgos.append("Terreno: se evalúa solo por precio frente a la zona y plusvalía, sin alquiler")
    pes_ok = pes is not None and pes >= p.get("tir_minima_peor_caso", 0.03)
    frenos = [m for falla, m in (
        (confianza != "alta", "pocos datos de la zona"),
        (len(ven) < 5 or (inm.get("tipo") != "terreno" and len(alq) < 5), "menos de 5 inmuebles parecidos (mismo distrito, tamaño y dormitorios) para confirmar precio y alquiler"),
        (not (nivel_v or "").startswith("distrito"), "sin comparación en el mismo distrito"),
        (bruta > 0.12 or inm.get("sospechoso"), "datos dudosos"),
        ((descuento or 0) > 0.30, "precio demasiado bajo para ser normal"),
        (not pes_ok, "en el peor caso no gana lo suficiente"),
        (desde, "precio 'desde'"),
        (bool(s.meses_hasta_renta), "aún no está construido"),
        (inm.get("estado") == "remate", "remate"),
        (not area or inm.get("tipo") == "terreno", "sin área o es terreno"),
        (precio > pmax, "cuesta más de lo que conviene pagar"),
    ) if falla]
    if bruta > 0.15:
        corto = mediano = largo = total = None
        veredicto = "Revisar a mano"
    elif total >= 7.5:
        veredicto = "Revisar a mano" if frenos else "Comprar"
        if frenos:
            riesgos.append("No llega a 'Comprar' porque: " + ", ".join(frenos))
    elif total >= 6 or pmax >= precio * 0.9:
        veredicto = "Negociar"
    else:
        veredicto = "Descartar"

    return {
        "inmueble_id": inm.get("id"),
        "precio_usd": precio,
        "renta_mensual_usd": round(renta, 2),
        "fuente_renta": fuente_renta,
        "rentabilidad_bruta": r["rentabilidad_bruta"],
        "rentabilidad_neta": r["rentabilidad_neta"],
        "flujo_mensual_usd": r["flujo_mensual_usd"],
        "descuento_vs_zona": descuento,
        "tir_2": r["tir_2"], "tir_5": r["tir_5"], "tir_10": r["tir_10"],
        "van_10": r["van_10"],
        "payback_anios": r["payback_anios"],
        "precio_max_recomendado": pmax,
        "puntaje_corto": corto, "puntaje_mediano": mediano, "puntaje_largo": largo, "puntaje_total": total,
        "veredicto": veredicto,
        "confianza": confianza,
        "riesgos": riesgos,
        "estrategia": estrategia,
        "tir_10_temporal": r_temp["tir_10"] if r_temp else None,
        "flujo_mensual_temporal": r_temp["flujo_mensual_usd"] if r_temp else None,
        "ingreso_temporal_anual": r_temp["ingreso_bruto_anual"] if r_temp else None,
        "detalle": {
            "comparacion": {
                "largo_plazo": {k: r_largo[k] for k in ("tir_5", "tir_10", "flujo_mensual_usd", "rentabilidad_neta", "ingreso_bruto_anual")},
                "temporal": ({k: r_temp[k] for k in ("tir_5", "tir_10", "flujo_mensual_usd", "rentabilidad_neta", "ingreso_bruto_anual", "inversion_inicial")}
                             | {"adr_usd": round(est["adr_usd"], 2), "ocupacion": est["ocupacion"], "fuente": est["fuente"], "nivel": est["nivel"], "amoblado_usd": s.amoblado_usd if estrategia == "temporal" else tmp.amoblado(inm, p)}) if r_temp else None,
                "regulacion": regla,
            },
            "plusvalia_usada": plusvalia,
            "meses_hasta_renta": s.meses_hasta_renta,
            "zona_venta": zv, "nivel_zona_venta": nivel_v,
            "comparables_alquiler": n_alq,
            "parecidos": {"alquiler": _resumen(alq), "venta": _resumen(ven)},
            "inversion_inicial": r["inversion_inicial"],
            "costos_compra": r["costos_compra"],
            "cuota_hipoteca_mensual": r["cuota_hipoteca_mensual"],
            "flujos_10": r["flujos_10"],
            "escenarios": esc,
            "supuestos": {k: p[k] for k in ("vacancia", "tasa_descuento", "cuota_inicial", "tasa_hipoteca", "inflacion_alquiler", "tipo_cambio")},
        },
        "version": VERSION,
    }
