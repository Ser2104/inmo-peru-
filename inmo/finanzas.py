from dataclasses import dataclass, asdict


def tasa_mensual(tea):
    return (1 + tea) ** (1 / 12) - 1


def cuota_hipoteca(principal, tea, anios):
    if principal <= 0:
        return 0.0
    i, n = tasa_mensual(tea), anios * 12
    return principal * i / (1 - (1 + i) ** -n)


def saldo_hipoteca(principal, tea, anios, meses_pagados):
    if principal <= 0:
        return 0.0
    i, c = tasa_mensual(tea), cuota_hipoteca(principal, tea, anios)
    return max(0.0, principal * (1 + i) ** meses_pagados - c * ((1 + i) ** meses_pagados - 1) / i)


def van(flujos, tasa):
    return sum(f / (1 + tasa) ** t for t, f in enumerate(flujos))


def tir(flujos):
    if not any(f > 0 for f in flujos) or not any(f < 0 for f in flujos):
        return None
    bajo, alto = -0.99, 1.0
    while van(flujos, alto) > 0 and alto < 100:
        alto *= 2
    if van(flujos, bajo) * van(flujos, alto) > 0:
        return None
    for _ in range(200):
        medio = (bajo + alto) / 2
        if van(flujos, bajo) * van(flujos, medio) <= 0:
            alto = medio
        else:
            bajo = medio
    return (bajo + alto) / 2


def costos_compra(precio_usd, nuevo, p):
    tc = p["tipo_cambio"]
    exento = p["alcabala_uit_exentas"] * p["uit_soles"] / tc
    alcabala = 0.0 if nuevo else p["alcabala"] * max(0.0, precio_usd - exento)
    return alcabala + p["gastos_notariales"] * precio_usd


@dataclass
class Supuestos:
    precio_usd: float
    renta_mensual_usd: float
    plusvalia: float
    mantenimiento_usd: float = 0.0
    meses_hasta_renta: int = 0
    nuevo: bool = False
    valor_mercado: float = 0.0
    pago_diferido: float = 0.0
    adr_usd: float = 0.0
    ocupacion: float = 0.0
    amoblado_usd: float = 0.0


def operativo(s: Supuestos, p, t, valor, meses_renta, meses_entregado):
    infl = (1 + p["inflacion_alquiler"]) ** (t - 1)
    fijos = valor * (p["predial_anual"] + p["seguro_anual"])
    if s.adr_usd:
        rampa = p.get("rampa_temporal", 0.75) if t == 1 or meses_renta < 12 else 1.0
        noches = 365 * s.ocupacion * rampa * meses_renta / 12
        cobrado = s.adr_usd * noches * infl
        gastos = (
            fijos
            + valor * p["reparaciones_anual"] * 1.5
            + s.mantenimiento_usd * meses_entregado
            + cobrado * (p["comision_plataforma"] * 1.18 + p["gestion_temporal"] + p["impuesto_renta_alquiler"])
            + noches / p["estadia_promedio"] * p["limpieza_neta_usd"]
            + p["servicios_temporal_usd"] * meses_renta * infl
            + s.amoblado_usd * p["reposicion_amoblado"] * meses_renta / 12
        )
        return cobrado, gastos
    cobrado = s.renta_mensual_usd * meses_renta * infl * (1 - p["vacancia"])
    gastos = (
        fijos
        + valor * p["reparaciones_anual"]
        + s.mantenimiento_usd * (max(0, meses_entregado - meses_renta) + meses_renta * p["vacancia"])
        + cobrado * (p["administracion"] + p["impuesto_renta_alquiler"])
    )
    return cobrado, gastos


def proyectar(s: Supuestos, p, anios):
    costos = costos_compra(s.precio_usd, s.nuevo, p)
    prestamo = s.precio_usd * (1 - p["cuota_inicial"])
    cuota = cuota_hipoteca(prestamo, p["tasa_hipoteca"], p["plazo_hipoteca"])
    propio = s.precio_usd - prestamo
    diferido = propio * s.pago_diferido
    anio_entrega = max(1, -(-max(0, s.meses_hasta_renta - 2) // 12))
    flujos = [-(propio - diferido + costos)]
    operativos = []
    anio_amoblado = max(0, -(-s.meses_hasta_renta // 12)) if s.meses_hasta_renta else 0
    if s.amoblado_usd and anio_amoblado == 0:
        flujos[0] -= s.amoblado_usd
    for t in range(1, anios + 1):
        meses_renta = min(12, max(0, t * 12 - s.meses_hasta_renta))
        meses_entregado = min(12, max(0, t * 12 - max(0, s.meses_hasta_renta - 2)))
        valor = (s.valor_mercado or s.precio_usd) * (1 + s.plusvalia) ** t
        cobrado, gastos = operativo(s, p, t, valor, meses_renta, meses_entregado)
        if s.amoblado_usd and anio_amoblado and t == anio_amoblado:
            gastos += s.amoblado_usd
        inicio_deuda = anio_entrega if s.pago_diferido else 1
        paga = inicio_deuda <= t < inicio_deuda + p["plazo_hipoteca"]
        neto = cobrado - gastos - cuota * 12 * paga
        operativos.append(neto)
        flujos.append(neto - (diferido if diferido and t == anio_entrega else 0))
    venta = (s.valor_mercado or s.precio_usd) * (1 + s.plusvalia) ** anios
    ganancia = max(0.0, venta * (1 - p["comision_venta"]) - s.precio_usd - costos)
    flujos[-1] += (
        venta * (1 - p["comision_venta"])
        - p.get("impuesto_ganancia_capital", 0.05) * ganancia
        - saldo_hipoteca(prestamo, p["tasa_hipoteca"], p["plazo_hipoteca"], max(0, anios - ((anio_entrega if s.pago_diferido else 1) - 1)) * 12)
    )
    return flujos, operativos, costos, cuota


def evaluar(s: Supuestos, p):
    f2, _, _, _ = proyectar(s, p, 2)
    f5, _, _, _ = proyectar(s, p, 5)
    f10, op10, costos, cuota = proyectar(s, p, 10)
    inversion = -f10[0]
    acumulado, payback = 0.0, None
    for t, f in enumerate(op10, 1):
        acumulado += f
        if payback is None and acumulado >= inversion:
            payback = t
    if payback is None and op10 and op10[-1] > 0:
        payback = round(inversion / op10[-1], 1)
    bruto_maduro = s.adr_usd * 365 * s.ocupacion if s.adr_usd else s.renta_mensual_usd * 12
    cobrado, gastos = operativo(s, p, 2, s.valor_mercado or s.precio_usd, 12, 12)
    noi = cobrado - gastos
    indice = min(len(op10), -(-(s.meses_hasta_renta + 12) // 12)) - 1
    primer_anio_rentado = op10[min(len(op10) - 1, indice + 1)] if s.adr_usd else op10[indice]
    return {
        "inversion_inicial": round(inversion, 2),
        "costos_compra": round(costos, 2),
        "cuota_hipoteca_mensual": round(cuota, 2),
        "ingreso_bruto_anual": round(bruto_maduro, 2),
        "rentabilidad_bruta": bruto_maduro / s.precio_usd if s.precio_usd else None,
        "rentabilidad_neta": noi / (s.precio_usd + costos + s.amoblado_usd) if s.precio_usd else None,
        "flujo_mensual_usd": round(primer_anio_rentado / 12, 2),
        "tir_2": tir(f2),
        "tir_5": tir(f5),
        "tir_10": tir(f10),
        "van_10": round(van(f10, p["tasa_descuento"]), 2),
        "payback_anios": payback,
        "flujos_10": [round(f, 2) for f in f10],
    }


def precio_maximo(s: Supuestos, p, objetivo=None):
    objetivo = p["tasa_descuento"] if objetivo is None else objetivo
    bajo, alto = s.precio_usd * 0.2, s.precio_usd * 3
    for _ in range(60):
        medio = (bajo + alto) / 2
        prueba = Supuestos(**{**asdict(s), "precio_usd": medio})
        t = tir(proyectar(prueba, p, 10)[0])
        if t is not None and t > objetivo:
            bajo = medio
        else:
            alto = medio
    return round(bajo, -2)


def escenarios(s: Supuestos, p):
    d = asdict(s)
    pes = Supuestos(**{**d, "renta_mensual_usd": s.renta_mensual_usd * 0.85, "plusvalia": s.plusvalia - 0.02, "ocupacion": s.ocupacion * 0.75, "adr_usd": s.adr_usd * 0.9})
    opt = Supuestos(**{**d, "renta_mensual_usd": s.renta_mensual_usd * 1.10, "plusvalia": s.plusvalia + 0.01, "ocupacion": min(0.9, s.ocupacion * 1.1)})
    p_pes = {**p, "vacancia": min(0.5, p["vacancia"] * 2), "tasa_hipoteca": p["tasa_hipoteca"] + 0.02}
    return {
        "pesimista": {k: v for k, v in evaluar(pes, p_pes).items() if k != "flujos_10"},
        "base": {k: v for k, v in evaluar(s, p).items() if k != "flujos_10"},
        "optimista": {k: v for k, v in evaluar(opt, p).items() if k != "flujos_10"},
    }
