import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import precio, numero, ubicacion, tipo_desde, operacion_desde, estado_desde, titulo_desde_url

SELECTORES = {
    "tarjeta": "[data-qa^='posting'], [data-to-posting]",
    "enlace": "data-to-posting",
    "precio": "[data-qa='POSTING_CARD_PRICE']",
    "mantenimiento": "[data-qa='expensas'], [data-qa='POSTING_CARD_EXPENSES']",
    "ubicacion": "[data-qa='POSTING_CARD_LOCATION']",
    "direccion": "[class*='postingAddress'], [class*='location-address']",
    "caracteristicas": "[data-qa='POSTING_CARD_FEATURES']",
    "descripcion": "[data-qa='POSTING_CARD_DESCRIPTION']",
}


def caracteristicas(texto):
    t = (texto or "").lower()
    salida = {}
    rango = re.search(r"([\d.,]+)\s*a\s*([\d.,]+)\s*m²", t)
    if rango:
        salida["area_m2"] = numero(rango.group(1))
    rango_d = re.search(r"(\d+)\s*a\s*\d+\s*(dorm|hab)", t)
    if rango_d:
        salida["dormitorios"] = int(rango_d.group(1))
    m = None if rango else re.search(r"([\d.,]+)\s*m²?\s*(cub|tech|const)", t) or re.search(r"([\d.,]+)\s*m²?\s*tot", t) or re.search(r"([\d.,]+)\s*m²", t)
    if m:
        salida["area_m2"] = numero(m.group(1))
    for campo, patron in [("dormitorios", r"(?<!a )(\d+)\s*(dorm|hab)"), ("banos", r"(\d+)\s*bañ"), ("estacionamientos", r"(\d+)\s*(estac|coch)")]:
        m = re.search(patron, t)
        if m:
            salida[campo] = int(m.group(1))
    return salida


def coordenadas(html):
    salida = {}
    for trozo in html.split('"postingId":"')[1:]:
        id_ = re.match(r"(\d+)", trozo)
        geo = re.search(r'"geolocation":\{"latitude":(-?\d+\.\d+),"longitude":(-?\d+\.\d+)', trozo.split('"postingId":"')[0])
        if id_ and geo:
            salida.setdefault(id_.group(1), (float(geo.group(1)), float(geo.group(2))))
    return salida


def antiguedades(html):
    plano = html.replace('\\"', '"')
    salida = {}
    for trozo in plano.split('"postingId":"')[1:]:
        id_ = re.match(r"(\d+)", trozo)
        m = re.search(r'"CFT5":\{[^}]*?"value":"(\d{1,3})"', trozo.split('"postingId":"')[0])
        if id_ and m:
            salida.setdefault(id_.group(1), int(m.group(1)))
    return salida


def parsear(html, base_url, selectores=None):
    s = {**SELECTORES, **(selectores or {})}
    coords = coordenadas(html)
    anios = antiguedades(html)
    sopa = BeautifulSoup(html, "html.parser")
    items, vistos = [], set()
    for card in sopa.select(s["tarjeta"]):
        ruta = card.get(s["enlace"]) or (card.find("a", href=True) or {}).get("href")
        if not ruta or ruta in vistos:
            continue
        vistos.add(ruta)
        url = urljoin(base_url, ruta).split("?")[0]
        texto = lambda sel: " ".join(e.get_text(" ", strip=True) for e in card.select(sel)) if sel else ""
        monto, moneda = precio(texto(s["precio"]))
        mant, mon_mant = precio(texto(s["mantenimiento"]))
        desc = texto(s["descripcion"])
        todo = card.get_text(" ", strip=True)
        item = {
            "url": url,
            "titulo": (card.find(["h2", "h3"]) or card).get_text(" ", strip=True)[:200],
            "precio": monto,
            "moneda": moneda,
            "mantenimiento": mant,
            "moneda_mantenimiento": mon_mant or "PEN",
            "descripcion": desc[:2000],
            **ubicacion(texto(s["ubicacion"])),
            **caracteristicas(texto(s["caracteristicas"]) or todo),
        }
        direccion = texto(s["direccion"])
        if direccion:
            item["direccion"] = direccion
        if not re.search(r"[a-záéíóúñ]{4}", re.sub(r"(?i)usd|s/", "", item["titulo"])):
            item["titulo"] = titulo_desde_url(url) or item["titulo"]
        pista = f"{url} {item['titulo']} {desc}"
        slug = re.search(r"/(?:clasificado|proyecto)/[a-z]+-(?:proyecto-|venta-de-|alquiler-de-)?([a-z-]+?)-(?:en|lima|\d)", url)
        item["tipo"] = tipo_desde(slug.group(1).replace("-", " ")) if slug and tipo_desde(slug.group(1).replace("-", " ")) else tipo_desde(pista)
        item["operacion"] = "alquiler" if re.search(r"/(clasificado|proyecto)/al|alquiler", url) else "venta" if re.search(r"/(clasificado|proyecto)/(ve|em)", url) else operacion_desde(pista)
        if item["operacion"] == "venta" and monto and moneda == "USD" and monto < 6000 and "venta" not in pista.lower():
            item["operacion"] = "alquiler"
        item["estado"] = estado_desde(pista)
        id_ = re.search(r"-(\d{6,})(?:\.html)?$", url)
        if id_ and id_.group(1) in coords:
            item["lat"], item["lng"] = coords[id_.group(1)]
        if id_ and id_.group(1) in anios:
            item["antiguedad_anios"] = anios[id_.group(1)]
        items.append(item)
    return items
