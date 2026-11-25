import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from ..collectors import base, ia, runner

AGENTE = "inmo-peru"
PALABRAS = re.compile(r"proyecto|departament|depa|casa|lote|terreno|venta|vende|inmueble|propiedad|preventa|condominio|edificio|residencial|local|oficina|remate|adjudicad|flat|duplex|alquiler", re.I)
EXCLUIR = re.compile(r"blog|noticia|nosotros|contacto|politica|privacidad|terminos|trabaja|login|carrito|/tag/|/category/|/author/|\.(jpg|jpeg|png|gif|webp|svg|css|js)$", re.I)
GRANDES = {"urbania.pe", "adondevivir.com", "properati.com.pe", "nexoinmobiliario.pe", "facebook.com", "instagram.com", "youtube.com", "tiktok.com"}


def dominio(url):
    url = url if "://" in url else f"https://{url}"
    return urlparse(url).netloc.lower().removeprefix("www.")


def _robots(raiz):
    rp = RobotFileParser()
    try:
        rp.parse(base.descargar(f"{raiz}/robots.txt", intentos=1, pausa=(0.2, 0.5)).splitlines())
    except Exception:
        rp.parse([])
    return rp


def leer_sitemap(url, profundidad=0, limite=3000):
    try:
        xml = base.descargar(url, intentos=1, pausa=(0.2, 0.5))
    except Exception:
        return []
    sopa = BeautifulSoup(xml, "html.parser")
    locs = [l.get_text(strip=True) for l in sopa.find_all("loc")]
    if sopa.find("sitemapindex") and profundidad < 2:
        salida = []
        for sub in [l for l in locs if PALABRAS.search(l) or "page" in l or "post" in l][:15] or locs[:15]:
            salida += leer_sitemap(sub, profundidad + 1, limite)
            if len(salida) >= limite:
                break
        return salida[:limite]
    return locs[:limite]


def paginas_candidatas(sitio):
    raiz = f"https://{dominio(sitio)}"
    rp = _robots(raiz)
    sitemaps = rp.site_maps() or [f"{raiz}/sitemap.xml", f"{raiz}/sitemap_index.xml", f"{raiz}/wp-sitemap.xml"]
    urls = []
    for sm in sitemaps:
        urls += leer_sitemap(sm)
        if urls:
            break
    if not urls:
        try:
            html = base.descargar(raiz, intentos=1, pausa=(0.2, 0.5))
            urls = [a["href"] if a["href"].startswith("http") else raiz + "/" + a["href"].lstrip("/") for a in BeautifulSoup(html, "html.parser").find_all("a", href=True)]
        except Exception:
            urls = []
    propias = [u.split("#")[0] for u in urls if dominio(u) == dominio(raiz)]
    return [u for u in dict.fromkeys(propias) if PALABRAS.search(u) and not EXCLUIR.search(u) and rp.can_fetch(AGENTE, u)]


def sitios(db):
    registrados = db.select_all("sitios", select="dominio,origen,paginas", estado="eq.inmobiliaria")
    primero = [s["dominio"] for s in sorted(registrados, key=lambda s: (s["origen"] != "usuario", s["paginas"]))]
    fuentes = [u for f in db.select("fuentes", select="urls,tipo,activo", tipo="eq.ia", activo="eq.true") for u in f["urls"]]
    pistas = [p["url"] for p in db.select_all("pistas", select="url", estado="eq.verificada") if p.get("url")]
    otros = sorted({dominio(u) for u in fuentes + pistas if u and u.startswith("http")} - set(primero))
    return [d for d in primero + otros if d and d not in GRANDES and not any(d.endswith("." + g) for g in GRANDES)]


SITEMAPS_PORTALES = {"nexoinmobiliario": "https://nexoinmobiliario.pe/sitemap-proyectos.xml"}


def portal_completo(db, p, fuente, sitemap, limite=150):
    vistos = {f["url"] for f in db.select_all("rastreo", select="url", dominio=f"eq.{dominio(sitemap)}")}
    nuevas = [u for u in leer_sitemap(sitemap, limite=20000) if u not in vistos][:limite]
    total = 0
    for url in nuevas:
        try:
            items = ia.extraer(base.descargar(url, intentos=1), url)
        except Exception:
            items = []
        crudos, usadas = [], set()
        for n, x in enumerate(items):
            u = x.get("url") or url
            if u in usadas:
                u = f"{u.split('#')[0]}#t{n}"
            usadas.add(u)
            crudos.append({**x, "url": u})
        filas = [f for f in (runner.normalizar(x, fuente, p["tipo_cambio"]) for x in crudos) if base.valido(f)]
        if filas:
            total += len(runner.guardar(db, filas))
        db.upsert("rastreo", {"url": url, "dominio": dominio(url), "visto": datetime.now(timezone.utc).isoformat(), "avisos": len(filas)}, on_conflict="url")
    return {"paginas": len(nuevas), "inmuebles": total}


def ejecutar(db, p, por_sitio=None, max_sitios=None):
    from .. import config
    por_sitio = por_sitio or (30 if config.OPENAI_API_KEY else 15)
    max_sitios = max_sitios or (60 if config.OPENAI_API_KEY else 25)
    vistos = {f["url"] for f in db.select_all("rastreo", select="url")}
    resumen = {"sitios": 0, "paginas_nuevas": 0, "inmuebles": 0}
    for sitio in sitios(db)[:max_sitios]:
        nuevas = [u for u in paginas_candidatas(sitio) if u not in vistos][:por_sitio]
        resumen["sitios"] += 1
        avisos_sitio = 0
        for url in nuevas:
            try:
                items = ia.extraer(base.descargar(url, intentos=1), url)
            except Exception:
                items = []
            filas = [f for f in (runner.normalizar({**x, "url": x.get("url") or url}, "explorador", p["tipo_cambio"]) for x in items) if base.valido(f)]
            if filas:
                resumen["inmuebles"] += len(runner.guardar(db, filas))
            db.upsert("rastreo", {"url": url, "dominio": dominio(url), "visto": datetime.now(timezone.utc).isoformat(), "avisos": len(filas)}, on_conflict="url")
            vistos.add(url)
            resumen["paginas_nuevas"] += 1
            avisos_sitio += len(filas)
        previo = (db.select("sitios", select="paginas,avisos", dominio=f"eq.{sitio}") or [None])[0]
        if previo and nuevas:
            db.update("sitios", {"paginas": previo["paginas"] + len(nuevas), "avisos": previo["avisos"] + avisos_sitio}, dominio=f"eq.{sitio}")
    for fuente, sitemap in SITEMAPS_PORTALES.items():
        try:
            resumen[fuente] = portal_completo(db, p, fuente, sitemap)
        except Exception as e:
            resumen[fuente] = f"error: {str(e)[:120]}"
    return resumen
