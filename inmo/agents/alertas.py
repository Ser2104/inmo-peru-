from ..notificar import telegram


def mensaje(a, i):
    estrategia = "alquiler por días" if a.get("estrategia") == "temporal" else "alquiler tradicional"
    return (
        f"🏠 {a['veredicto']} — puntaje {a['puntaje_total']}/10 (confianza {a['confianza']}) · mejor como {estrategia}\n"
        f"{i.get('tipo') or ''} en {i.get('distrito') or ''}, {i.get('departamento') or ''}\n"
        f"Precio: US$ {a['precio_usd']:,.0f} | Máx. recomendado: US$ {a['precio_max_recomendado']:,.0f}\n"
        f"Alquiler estimado: US$ {a['renta_mensual_usd']:,.0f}/mes | TIR 10 años: {(a['tir_10'] or 0) * 100:.1f}%\n"
        f"Corto {a['puntaje_corto']} · Mediano {a['puntaje_mediano']} · Largo {a['puntaje_largo']}\n"
        f"{i['url']}"
    )


def enviar(texto):
    telegram(texto)


def ejecutar(db, p):
    enviadas = {a["inmueble_id"] for a in db.select_all("alertas", select="inmueble_id")}
    candidatos = db.select("analisis", select="*", puntaje_total=f"gte.{p['umbral_alerta']}", veredicto="eq.Comprar", order="puntaje_total.desc", limit="50")
    nuevos = [a for a in candidatos if a["inmueble_id"] not in enviadas]
    n_arb = arbitrajes(db, p, enviadas)
    if not nuevos:
        return {"enviadas": 0, "arbitraje": n_arb}
    ids = ",".join(a["inmueble_id"] for a in nuevos)
    info = {i["id"]: i for i in db.select("inmuebles", select="id,url,tipo,distrito,departamento,activo,sospechoso", id=f"in.({ids})")}
    n = 0
    for a in nuevos:
        i = info.get(a["inmueble_id"])
        if not i or not i["activo"] or i.get("sospechoso"):
            continue
        enviar(mensaje(a, i))
        db.upsert("alertas", {"inmueble_id": a["inmueble_id"]}, on_conflict="inmueble_id")
        n += 1
    return {"enviadas": n, "arbitraje": n_arb}


def arbitrajes(db, p, enviadas):
    candidatos = db.select("arbitraje", select="*", puntaje=f"gte.{p['umbral_alerta']}", order="puntaje.desc", limit="20")
    nuevos = [a for a in candidatos if a["inmueble_id"] not in enviadas]
    if not nuevos:
        return 0
    info = {i["id"]: i for i in db.select("inmuebles", select="id,url,distrito,departamento,activo,dormitorios", id=f"in.({','.join(a['inmueble_id'] for a in nuevos)})")}
    n = 0
    for a in nuevos:
        i = info.get(a["inmueble_id"])
        if not i or not i["activo"]:
            continue
        enviar(
            f"🔑 Arbitraje: alquilar y operar por días — puntaje {a['puntaje']}/10\n"
            f"{i.get('distrito') or ''}, {i.get('departamento') or ''} · {i.get('dormitorios') or '?'} dorm.\n"
            f"Alquiler: US$ {a['renta_usd']:,.0f}/mes | Ingreso por días: US$ {a['ingreso_temporal_mensual_usd']:,.0f}/mes\n"
            f"Ganancia: US$ {a['utilidad_mensual_usd']:,.0f}/mes | Recuperas el amoblado en {a['payback_meses'] or '—'} meses\n"
            f"Necesitas permiso escrito del dueño para subarrendar.\n{i['url']}"
        )
        db.upsert("alertas", {"inmueble_id": a["inmueble_id"]}, on_conflict="inmueble_id")
        n += 1
    return n
