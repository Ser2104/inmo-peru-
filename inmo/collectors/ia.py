import re
import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .. import llm

PROMPT = """Extrae TODOS los inmuebles o proyectos inmobiliarios en venta o alquiler de este contenido de una página web peruana.
URL de la página: {url}

Devuelve una lista JSON. Cada elemento con estas claves (null si no aparece, no inventes):
url (enlace absoluto al aviso; si la página es un solo aviso usa la URL de la página), titulo,
tipo (departamento|casa|local|oficina|terreno|edificio), operacion (venta|alquiler),
estado (terminado|en_planos|preventa|remate), precio (número), moneda (USD|PEN),
mantenimiento (número mensual), area_m2, dormitorios, banos, estacionamientos,
departamento, provincia, distrito, direccion, fecha_entrega (AAAA-MM-DD), constructora, telefono (WhatsApp o teléfono de contacto del aviso), descripcion (máx 300 caracteres).
Si un proyecto tiene varias unidades con precio "desde", crea un elemento por tipología con su precio y área.

CONTENIDO:
{contenido}"""


PRECIO = re.compile(r"(S/\.?\s?\d|US\$\s?\d|USD\s?\d|\$\s?\d{2,}|\d[\d.,]*\s?(soles|d[oó]lares))", re.I)
DATO = re.compile(r"(S/\.?\s?\d|US\$\s?\d|USD\s?\d|\$\s?\d{2,}|\d+\s?m(²|2)\b|\d\s?dorm|\d\s?hab|precio|desde)", re.I)
ENLACE_UTIL = re.compile(r"(\d{3,}|proyecto|depa|departament|casa|lote|terreno|venta|inmueble|flat|tipolog|unidad|modelo)", re.I)
VENTANA, TOPE = 700, 14000


def enfocar(texto, tope=TOPE):
    tramos = []
    for m in DATO.finditer(texto):
        a, b = max(0, m.start() - VENTANA), m.end() + VENTANA
        if tramos and a <= tramos[-1][1]:
            tramos[-1][1] = max(tramos[-1][1], b)
        else:
            tramos.append([a, b])
    salida = " … ".join(texto[a:b] for a, b in tramos)
    return salida[:tope]


def _reducir(html, base_url, limite=45000):
    if html.startswith("<pdf>"):
        return " ".join(html[5:].split())[:limite]
    sopa = BeautifulSoup(html, "html.parser")
    for e in sopa(["script", "style", "noscript", "svg", "iframe", "header", "footer"]):
        e.decompose()
    for a in sopa.find_all("a", href=True):
        if ENLACE_UTIL.search(a["href"]):
            a.insert_after(f" [{urljoin(base_url, a['href'])}] ")
    texto = " ".join(sopa.get_text(" ", strip=True).split())
    return texto[:limite]


def json_ld(html, base_url):
    sopa = BeautifulSoup(html, "html.parser")
    items = []
    for s in sopa.find_all("script", type="application/ld+json"):
        try:
            datos = json.loads(s.string or "")
        except json.JSONDecodeError:
            continue
        for d in datos if isinstance(datos, list) else datos.get("@graph", [datos]):
            oferta = d.get("offers") or {}
            oferta = oferta[0] if isinstance(oferta, list) and oferta else oferta
            if not isinstance(oferta, dict) or not oferta.get("price"):
                continue
            dir_ = d.get("address") or {}
            area = (d.get("floorSize") or {}).get("value") if isinstance(d.get("floorSize"), dict) else None
            items.append({
                "url": urljoin(base_url, d.get("url") or base_url),
                "titulo": d.get("name"),
                "precio": float(oferta["price"]),
                "moneda": "PEN" if str(oferta.get("priceCurrency", "")).upper() in ("PEN", "S/") else "USD",
                "area_m2": float(area) if area else None,
                "dormitorios": d.get("numberOfRooms") if isinstance(d.get("numberOfRooms"), int) else None,
                "distrito": dir_.get("addressLocality") if isinstance(dir_, dict) else None,
                "departamento": dir_.get("addressRegion") if isinstance(dir_, dict) else None,
                "descripcion": (d.get("description") or "")[:300],
            })
    return items


def enlaces_pdf(html, base_url, limite=30):
    if html.startswith("<pdf>"):
        return []
    sopa = BeautifulSoup(html, "html.parser")
    urls = [urljoin(base_url, a["href"]) for a in sopa.find_all("a", href=True) if ".pdf" in a["href"].lower()]
    return list(dict.fromkeys(urls))[:limite]


def extraer(html, url):
    from . import estructurado
    items = [] if html.startswith("<pdf>") else json_ld(html, url)
    if len(items) < 3 and not html.startswith("<pdf>"):
        items = estructurado.parsear(html, url) or items
    if items or not llm.disponible():
        return items
    texto = _reducir(html, url, 300000)
    if not PRECIO.search(texto):
        return []
    contenido = enfocar(texto)
    datos = llm.pedir_json(PROMPT.format(url=url, contenido=contenido))
    salida = [d for d in (datos if isinstance(datos, list) else datos.get("inmuebles", [])) if isinstance(d, dict)]
    for d in salida:
        if not d.get("url") or not str(d["url"]).startswith("http"):
            d["url"] = f"{url}#{d.get('titulo') or ''}-{d.get('precio') or ''}-{d.get('area_m2') or ''}"
    return salida
