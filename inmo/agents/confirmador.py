import re
import time
from datetime import datetime, timedelta, timezone

from ..collectors import base

RETIRADO = re.compile(r"(ya no est[aá] disponible|aviso (finalizado|no disponible|ha sido dado de baja)|publicaci[oó]n (finalizada|no disponible)|inmueble vendido|propiedad vendida|no se encontr[oó] el aviso)", re.I)


def abrir(url):
    if base.cffi:
        r = base.cffi.get(url, impersonate="chrome", headers={"Accept-Language": base.HEADERS["Accept-Language"]}, timeout=60)
    else:
        r = base.httpx.get(url, headers=base.HEADERS, timeout=60, follow_redirects=True)
    return r.status_code, str(r.url), r.text


def numeros(texto):
    return {re.sub(r"\D", "", n) for n in re.findall(r"(?<![\d.,])(?:\d{1,3}(?:[.,\u00a0 ]\d{3})+|\d{4,})(?![\d])", texto)}


def revisar(inm, abrir_fn=abrir):
    try:
        estado, final, html = abrir_fn(inm["url"])
    except Exception:
        return "no_verificable"
    if estado in (404, 410):
        return "no_disponible"
    if estado != 200:
        return "no_verificable"
    ruta = lambda u: re.sub(r"[?#].*", "", u).rstrip("/")
    if ruta(final) != ruta(inm["url"]) and re.search(r"/(buscar|busqueda|search)|/$", final + "/"):
        return "no_disponible"
    if RETIRADO.search(html):
        return "no_disponible"
    precios = {str(int(float(inm[c]))) for c in ("precio", "precio_usd") if inm.get(c)}
    if precios & numeros(html):
        return "ok"
    titulo = [w for w in re.findall(r"[a-záéíóúñ]{5,}", (inm.get("titulo") or "").lower())][:4]
    return "precio_cambio" if titulo and all(w in html.lower() for w in titulo) else "no_verificable"


MOTIVOS = {
    "no_disponible": "El aviso ya no está publicado: probablemente se vendió.",
    "precio_cambio": "El precio del aviso cambió o no coincide: revisa el precio actual.",
    "no_verificable": "No se pudo abrir el aviso para confirmarlo automáticamente: confírmalo tú con el enlace.",
}


def ejecutar(db, dias=3, abrir_fn=abrir):
    comprar = db.select_all("analisis", select="inmueble_id,riesgos", veredicto="eq.Comprar")
    if not comprar:
        return {"revisados": 0}
    ids = [a["inmueble_id"] for a in comprar]
    inmuebles = {}
    for k in range(0, len(ids), 150):
        for i in db.select("inmuebles", select="id,url,titulo,precio,precio_usd,confirmado,confirmacion", id=f"in.({','.join(ids[k:k + 150])})"):
            inmuebles[i["id"]] = i
    reciente = datetime.now(timezone.utc) - timedelta(days=dias)
    conteo = {}
    for a in comprar:
        inm = inmuebles.get(a["inmueble_id"])
        if not inm:
            continue
        previo = inm.get("confirmado") and datetime.fromisoformat(str(inm["confirmado"]).replace("Z", "+00:00")) > reciente
        resultado = inm["confirmacion"] if previo else revisar(inm, abrir_fn)
        if not previo:
            db.update("inmuebles", {"confirmado": datetime.now(timezone.utc).isoformat(), "confirmacion": resultado,
                                    **({"activo": False} if resultado == "no_disponible" else {})}, id=f"eq.{inm['id']}")
            time.sleep(0.5)
        if resultado != "ok":
            riesgos = [r for r in (a.get("riesgos") or []) if r not in MOTIVOS.values()] + [MOTIVOS[resultado]]
            db.update("analisis", {"veredicto": "Revisar a mano", "riesgos": riesgos}, inmueble_id=f"eq.{inm['id']}")
        conteo[resultado] = conteo.get(resultado, 0) + 1
    return conteo
