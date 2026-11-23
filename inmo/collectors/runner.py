from datetime import date, datetime, timedelta, timezone

from .. import config
from . import base, navent, ia
from .. import ubigeo

COLUMNAS = [
    "fuente", "url", "titulo", "tipo", "operacion", "estado", "departamento", "provincia", "distrito", "direccion",
    "lat", "lng", "area_m2", "dormitorios", "banos", "estacionamientos", "precio", "moneda", "precio_usd",
    "mantenimiento_usd", "fecha_entrega", "constructora", "descripcion", "activo", "ultima_vez",
]


def normalizar(item, fuente_id, tc):
    item = base.limpiar(dict(item), tc)
    pista = f"{item.get('url', '')} {item.get('titulo', '')} {item.get('descripcion', '')}"
    item["tipo"] = item.get("tipo") or base.tipo_desde(pista)
    item["operacion"] = item.get("operacion") or base.operacion_desde(pista)
    item["estado"] = item.get("estado") if item.get("estado") in ("terminado", "en_planos", "preventa", "remate") else base.estado_desde(pista)
    texto = pista.lower()
    if item["estado"] == "terminado" and ("/proyecto" in texto or " desde " in f" {texto}") and "entrega inmediata" not in texto:
        item["estado"] = "preventa"
    lugar = ubigeo.resolver(item.get("distrito"), item.get("provincia"), item.get("departamento"))
    if lugar.get("distrito"):
        if lugar.get("barrio") and not item.get("direccion"):
            item["direccion"] = lugar["barrio"]
        item.update({k: lugar[k] for k in ("departamento", "provincia", "distrito")})
    elif lugar.get("departamento"):
        item["departamento"] = lugar["departamento"]
    item["fuente"] = fuente_id
    item["activo"] = True
    item["ultima_vez"] = datetime.now(timezone.utc).isoformat()
    return {c: item.get(c) for c in COLUMNAS}


def guardar(db, items):
    if not items:
        return []
    unicos = list({i["url"]: i for i in items}.values())
    filas = db.upsert("inmuebles", unicos, on_conflict="url", devolver=True)
    hoy = date.today().isoformat()
    db.upsert("precios_historial", [{"inmueble_id": f["id"], "fecha": hoy, "precio_usd": f["precio_usd"]} for f in filas if f.get("precio_usd")], on_conflict="inmueble_id,fecha")
    return filas


def parsear(fuente, html, url):
    cfg = fuente.get("config") or {}
    if fuente["tipo"] == "navent":
        return navent.parsear(html, url, cfg.get("selectores"))
    items = ia.extraer(html, url)
    if cfg.get("seguir_pdf"):
        for pdf in ia.enlaces_pdf(html, url):
            try:
                items += [{**x, "estado": x.get("estado") or "remate"} for x in ia.extraer(base.descargar(pdf), pdf)]
            except Exception:
                continue
    return items


def en_pausa(fuente):
    hasta = (fuente.get("config") or {}).get("pausado_hasta")
    return bool(hasta) and datetime.fromisoformat(hasta) > datetime.now(timezone.utc)


def recolectar_fuente(db, fuente, p, completo=False, reparar=None):
    if en_pausa(fuente) and not completo:
        return {"fuente": fuente["id"], "omitido": f"en pausa hasta {fuente['config']['pausado_hasta']}"}
    tc = p["tipo_cambio"]
    nuevos = total = 0
    errores = []
    limite = config.MAX_PAGINAS * (5 if completo else 1)
    hace_un_dia = datetime.now(timezone.utc) - timedelta(days=1)
    vistos = set()
    for plantilla in fuente["urls"]:
        for n in range(1, limite + 1):
            url = plantilla.format(n=n)
            try:
                html = base.descargar(url)
            except RuntimeError as e:
                errores.append(str(e))
                break
            crudos = parsear(fuente, html, url)
            if not crudos and n == 1 and reparar:
                crudos = reparar(db, fuente, html, url)
            items = [i for i in (normalizar(c, fuente["id"], tc) for c in crudos) if base.valido(i)]
            if not items:
                if n == 1:
                    errores.append(f"0 avisos en {url}")
                break
            if all(i["url"] in vistos for i in items):
                break
            vistos.update(i["url"] for i in items)
            filas = guardar(db, items)
            total += len(filas)
            nuevas = [f for f in filas if datetime.fromisoformat(f["primera_vez"].replace("Z", "+00:00")) > hace_un_dia]
            nuevos += len(nuevas)
            if "{n}" not in plantilla or (not completo and len(nuevas) < len(filas) * 0.1):
                break
    ok = total > 0
    fallos = 0 if ok else fuente.get("fallos_seguidos", 0) + 1
    cfg = dict(fuente.get("config") or {})
    cfg.pop("pausado_hasta", None)
    if fallos >= 3:
        horas = min(168, 6 * 2 ** (fallos - 3))
        cfg["pausado_hasta"] = (datetime.now(timezone.utc) + timedelta(hours=horas)).isoformat()
    cfg["ultimo_total"] = total
    if ok:
        previo = cfg.get("promedio_total") or total
        cfg["promedio_total"] = round(0.8 * previo + 0.2 * total, 1)
    db.update("fuentes", {
        "ultimo_ok": datetime.now(timezone.utc).isoformat() if ok else fuente.get("ultimo_ok"),
        "ultimo_error": "; ".join(errores)[:1000] or None,
        "fallos_seguidos": fallos,
        "config": cfg,
    }, id=f"eq.{fuente['id']}")
    return {"fuente": fuente["id"], "total": total, "nuevos": nuevos, "errores": errores}
