from dataclasses import dataclass

from .finanzas import tir, van

MARGEN = {
    "cafeteria": 0.25, "restaurante": 0.22, "comida_rapida": 0.25, "bodega": 0.12, "minimarket": 0.12, "farmacia": 0.15,
    "libreria": 0.30, "fotocopiadora": 0.35, "gimnasio": 0.35, "lavanderia": 0.35, "estacionamiento": 0.55, "quiosco": 0.20,
    "hospedaje": 0.30, "salon_belleza": 0.30, "otro": 0.20,
}
RUBROS = "|".join(MARGEN)


@dataclass
class Negocio:
    inversion_usd: float
    ventas_mensuales_usd: float | None = None
    canon_mensual_usd: float = 0.0
    utilidad_declarada_usd: float | None = None
    rubro: str = "otro"
    plazo_meses: int = 60
    garantia_meses: int = 2
    arranque_meses: int = 3


def utilidad_mensual(n: Negocio, factor_ventas=1.0):
    if n.utilidad_declarada_usd is not None:
        return n.utilidad_declarada_usd * 0.8 * factor_ventas
    return n.ventas_mensuales_usd * factor_ventas * MARGEN.get(n.rubro, MARGEN["otro"]) - n.canon_mensual_usd


def flujos(n: Negocio, factor_ventas=1.0):
    u, garantia = utilidad_mensual(n, factor_ventas), n.canon_mensual_usd * n.garantia_meses
    f = [-(n.inversion_usd + garantia)] + [u * (0.6 if m <= n.arranque_meses else 1) for m in range(1, n.plazo_meses + 1)]
    f[-1] += garantia
    return f


def evaluar(n: Negocio, p):
    tasa_anual = p.get("tasa_descuento", 0.07) + p.get("prima_negocio", 0.08)
    tm = (1 + tasa_anual) ** (1 / 12) - 1
    f = flujos(n)
    t = tir(f)
    acumulado, payback = 0.0, None
    for m, x in enumerate(f):
        acumulado += x
        if m and acumulado >= 0:
            payback = m
            break
    pesimista = flujos(n, 0.8)
    return {
        "utilidad_mensual_usd": round(utilidad_mensual(n), 2),
        "tir_anual": None if t is None else (1 + t) ** 12 - 1,
        "van_usd": round(van(f, tm), 2),
        "payback_meses": payback,
        "van_pesimista_usd": round(van(pesimista, tm), 2),
        "tir_pesimista": None if tir(pesimista) is None else (1 + tir(pesimista)) ** 12 - 1,
        "tasa_exigida": tasa_anual,
        "margen_usado": None if n.utilidad_declarada_usd is not None else MARGEN.get(n.rubro, MARGEN["otro"]),
    }


def veredicto(c, p, ubic=None):
    riesgos = []
    if c["tipo"] == "estado":
        inv = c.get("inversion_usd")
        if inv and inv > p.get("tope_inversion_usd", 2_000_000):
            return {"veredicto": "Fuera de escala", "riesgos": [f"Requiere unos US$ {inv/1e6:.1f} millones: solo con socios grandes o en consorcio."]}
        return {"veredicto": "Revisar a mano", "riesgos": ["Proceso del Estado: revisa bases, requisitos de experiencia y garantías."]}
    tiene_ventas = c.get("ventas_mensuales_usd") or c.get("utilidad_declarada_usd") is not None
    if not c.get("inversion_usd") or not tiene_ventas:
        falta = [x for x, ok in (("inversión o precio", c.get("inversion_usd")), ("ventas o utilidad al mes", tiene_ventas)) if not ok]
        return {"veredicto": "Falta información", "riesgos": ["Falta: " + ", ".join(falta) + ". Pídelo por WhatsApp."]}
    n = Negocio(
        inversion_usd=c["inversion_usd"], ventas_mensuales_usd=c.get("ventas_mensuales_usd"), canon_mensual_usd=c.get("canon_mensual_usd") or 0,
        utilidad_declarada_usd=c.get("utilidad_declarada_usd"), rubro=c.get("rubro") if c.get("rubro") in MARGEN else "otro",
        plazo_meses=int(c.get("plazo_meses") or (36 if c["tipo"] == "local" else 60)),
    )
    r = evaluar(n, p)
    t = r["tir_anual"] or -1
    if c.get("utilidad_declarada_usd") is not None:
        riesgos.append("La utilidad la declara el vendedor (se le resta 20%): pide boletas, declaraciones a SUNAT y el contrato de alquiler.")
    else:
        riesgos.append(f"Ganancia estimada con un margen típico de {r['margen_usado']:.0%} para {n.rubro}: confírmalo con números reales.")
    if c["tipo"] == "traspaso" and not c.get("plazo_meses"):
        riesgos.append("No se sabe cuánto le queda al contrato del local: se asumió 5 años sin renovar.")
    if n.plazo_meses < 24:
        riesgos.append("Contrato corto: hay poco tiempo para recuperar la inversión.")
    if n.ventas_mensuales_usd and n.canon_mensual_usd > 0.15 * n.ventas_mensuales_usd:
        riesgos.append("El canon o alquiler supera el 15% de las ventas: es alto.")
    if r["van_pesimista_usd"] < 0:
        riesgos.append("Si las ventas caen 20%, pierdes dinero.")
    financiero = round(max(0.0, min(10.0, t * 20)), 1)
    if ubic is None:
        riesgos.append("Ubicación aproximada: no se pudo evaluar si la zona es estratégica para este negocio.")
    else:
        detalle = ", ".join(ubic["cerca"]) or "poca actividad"
        riesgos.append(f"Zona a {ubic['radio_m']} m: {detalle}; {ubic['competidores']} competidores directos. Ubicación {ubic['puntaje']}/10.")
        if ubic["puntaje"] < 4:
            riesgos.append("Zona poco estratégica para este rubro: poca demanda o mucha competencia.")
    if r["utilidad_mensual_usd"] <= 0:
        v = "Descartar"
    elif t >= 0.30 and (r["payback_meses"] or 999) <= 30 and r["van_pesimista_usd"] > 0 and ubic and ubic["puntaje"] >= 6:
        v = "Atractivo"
    elif (t >= 0.18 or (r["payback_meses"] or 999) <= 40) and not (ubic and ubic["puntaje"] < 4 and t < 0.30):
        v = "Negociar"
    else:
        v = "Descartar"
    total = financiero if ubic is None else round(0.7 * financiero + 0.3 * ubic["puntaje"], 1)
    return {"veredicto": v, "puntaje": total, "puntaje_financiero": financiero, "riesgos": riesgos, **r}
