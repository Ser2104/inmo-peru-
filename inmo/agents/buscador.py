import re
from datetime import date
from urllib.parse import urlparse

from .. import config, llm
from ..collectors import base, ia, runner

PROMPT = """Eres un buscador de oportunidades inmobiliarias en Perú. Busca en internet, en el departamento de {dep},
avisos y proyectos publicados en los últimos 30 días:
- proyectos nuevos, preventas y lanzamientos de constructoras e inmobiliarias
- remates y adjudicados de bancos (BCP, BBVA, Interbank, Scotiabank, cajas municipales) y del Poder Judicial (REMAJU)
- terrenos, casas, locales y departamentos en venta con buen precio
Incluye todas las provincias, no solo la capital.

Devuelve una lista JSON (máximo 25) de objetos con: url, nombre, clase (aviso|proyecto|listado|constructora).
"listado" = página con muchos avisos; "constructora" = web de una empresa con varios proyectos."""

DOMINIOS_IGNORAR = ("facebook.com", "instagram.com", "tiktok.com", "youtube.com", "google.", "wikipedia.org", "x.com", "twitter.com")


def _rotacion(hoy=None, por_dia=5):
    hoy = hoy or date.today()
    deps = config.DEPARTAMENTOS
    inicio = (hoy.toordinal() * por_dia) % len(deps)
    return [deps[(inicio + k) % len(deps)] for k in range(por_dia)]


def _id_fuente(url):
    return re.sub(r"[^a-z0-9]+", "-", urlparse(url).netloc.lower().removeprefix("www.")).strip("-")


def ejecutar(db, p, departamentos=None):
    if not llm.disponible():
        return {"omitido": "sin clave de IA"}
    fuentes = {f["id"] for f in db.select("fuentes", select="id")}
    resumen = {"departamentos": [], "nuevas_fuentes": [], "guardados": 0, "errores": []}
    for dep in departamentos or _rotacion():
        resumen["departamentos"].append(dep)
        try:
            hallazgos = llm.pedir_json(PROMPT.format(dep=dep), buscar=True)
        except RuntimeError as e:
            resumen["errores"].append(f"{dep}: {e}")
            continue
        for h in hallazgos if isinstance(hallazgos, list) else []:
            url = (h or {}).get("url") or ""
            if not url.startswith("http") or any(d in url for d in DOMINIOS_IGNORAR):
                continue
            fid = _id_fuente(url)
            try:
                html = base.descargar(url, intentos=2)
                items = ia.extraer(html, url)
            except Exception as e:
                resumen["errores"].append(f"{url}: {e}")
                continue
            filas = [i for i in (runner.normalizar({**x, "departamento": x.get("departamento") or dep}, "manual", p["tipo_cambio"]) for x in items) if base.valido(i)]
            if h.get("clase") in ("listado", "constructora") and fid not in fuentes and len(filas) >= 2:
                db.upsert("fuentes", {"id": fid, "nombre": h.get("nombre") or fid, "tipo": "ia", "urls": [url]}, on_conflict="id")
                fuentes.add(fid)
                resumen["nuevas_fuentes"].append(fid)
            for f in filas:
                f["fuente"] = fid if fid in fuentes else "manual"
            resumen["guardados"] += len(runner.guardar(db, filas))
    return resumen
