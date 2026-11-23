import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import precio, numero, ubicacion, tipo_desde, operacion_desde, estado_desde

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
    m = re.search(r"([\d.,]+)\s*m²?\s*(cub|tech|const)", t) or re.search(r"([\d.,]+)\s*m²?\s*tot", t) or re.search(r"([\d.,]+)\s*m²", t)
    if m:
        salida["area_m2"] = numero(m.group(1))
    for campo, patron in [("dormitorios", r"(\d+)\s*(dorm|hab)"), ("banos", r"(\d+)\s*bañ"), ("estacionamientos", r"(\d+)\s*(estac|coch)")]:
        m = re.search(patron, t)
        if m:
            salida[campo] = int(m.group(1))
    return salida


def parsear(html, base_url, selectores=None):
    s = {**SELECTORES, **(selectores or {})}
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
        pista = f"{url} {item['titulo']} {desc}"
        item["tipo"] = tipo_desde(pista)
        item["operacion"] = "alquiler" if re.search(r"/alcla|alquiler", url) else operacion_desde(pista)
        if item["operacion"] == "venta" and monto and moneda == "USD" and monto < 6000 and "venta" not in pista.lower():
            item["operacion"] = "alquiler"
        item["estado"] = estado_desde(pista)
        items.append(item)
    return items
