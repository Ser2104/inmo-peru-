import json
import re
from urllib.parse import urljoin

from .base import numero, precio as leer_precio, ubicacion

BLOQUES = r'<script[^>]+(?:application/ld\+json|__NEXT_DATA__|application/json)[^>]*>(.*?)</script>'
CLAVES = {
    "precio": ("price", "precio", "amount", "priceamount", "valor"),
    "url": ("url", "link", "href", "permalink", "canonical", "slug", "path"),
    "area": ("floorsize", "area", "surface", "m2", "superficie", "totalarea", "coveredarea", "area_total", "areaconstruida"),
    "dorm": ("numberofrooms", "numberofbedrooms", "bedrooms", "dormitorios", "rooms", "habitaciones"),
    "banos": ("numberofbathroomstotal", "bathrooms", "banos", "baños"),
    "titulo": ("name", "title", "titulo"),
    "lat": ("latitude", "lat"),
    "lng": ("longitude", "lng", "lon"),
    "lugar": ("address", "location", "ubicacion", "addresslocality", "district", "distrito", "neighborhood"),
}


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return numero(v)


def _plano(d, pref="", salida=None, nivel=0):
    salida = {} if salida is None else salida
    if nivel > 3 or not isinstance(d, dict):
        return salida
    for k, v in d.items():
        clave = re.sub(r"[^a-z0-9ñ_]", "", k.lower())
        if isinstance(v, dict):
            _plano(v, clave, salida, nivel + 1)
        elif isinstance(v, (str, int, float)) and v != "":
            salida.setdefault(clave, v)
            salida.setdefault(pref + clave, v)
    return salida


NUMERICOS = ("area", "dorm", "banos", "lat", "lng")


def _campo(plano, nombre):
    claves = [k for k in plano if not re.search(r"image|photo|foto|logo|video|agent|broker|publisher", k)]
    for prueba in (lambda k, c: k == c, lambda k, c: k.startswith(c), lambda k, c: k.endswith(c)):
        for c in CLAVES[nombre]:
            for k in claves:
                if prueba(k, c) and (nombre not in NUMERICOS or numero(plano[k]) is not None):
                    return plano[k]
    return None


def _listas(x, salida):
    if isinstance(x, list):
        dicts = [e for e in x if isinstance(e, dict)]
        if len(dicts) >= 3:
            salida.append(dicts)
        for e in x:
            _listas(e, salida)
    elif isinstance(x, dict):
        for v in x.values():
            _listas(v, salida)
    return salida


def _item(d, base_url):
    if isinstance(d.get("item"), dict):
        d = d["item"]
    p = _plano(d)
    url, monto = _campo(p, "url"), _campo(p, "precio")
    if not url or monto is None:
        return None
    moneda = str(p.get("pricecurrency") or p.get("currency") or p.get("moneda") or "")
    valor, mon = (float(monto), None) if isinstance(monto, (int, float)) else leer_precio(str(monto))
    if not valor:
        return None
    url = urljoin(base_url, str(url))
    if not url.startswith("http"):
        return None
    lugar = _campo(p, "lugar")
    item = {"url": url.split("?")[0], "titulo": str(_campo(p, "titulo") or "")[:200], "precio": valor,
            "moneda": "USD" if "USD" in moneda.upper() or "$" == moneda or mon == "USD" else "PEN" if moneda or mon else mon,
            "area_m2": numero(_campo(p, "area")), "dormitorios": numero(_campo(p, "dorm")), "banos": numero(_campo(p, "banos")),
            "descripcion": str(p.get("description") or "")[:2000], "direccion": str(lugar)[:200] if lugar else None}
    if p.get("addresslocality"):
        item.update(distrito=str(p["addresslocality"]), departamento=str(p.get("addressregion") or p["addresslocality"]))
    elif isinstance(lugar, str) and "," in lugar:
        item.update({k: v for k, v in ubicacion(lugar).items() if v})
    lat, lng = _num(_campo(p, "lat")), _num(_campo(p, "lng"))
    if lat and lng and -19 < lat < 0 and -82 < lng < -68:
        item["lat"], item["lng"] = lat, lng
    for k in ("dormitorios", "banos"):
        item[k] = int(item[k]) if item[k] and item[k] < 50 else None
    return item


def parsear(html, base_url):
    mejores = []
    for bloque in re.findall(BLOQUES, html, re.S):
        try:
            datos = json.loads(bloque)
        except ValueError:
            continue
        for lista in _listas(datos, []):
            items = [i for i in (_item(d, base_url) for d in lista) if i]
            if len(items) > len(mejores) and len(items) >= len(lista) * 0.5:
                mejores = items
    return list({i["url"]: i for i in mejores}.values())


def muestras(html, maximo=4):
    salida = []
    for bloque in re.findall(BLOQUES, html, re.S):
        try:
            datos = json.loads(bloque)
        except ValueError:
            continue
        for lista in sorted(_listas(datos, []), key=len, reverse=True)[:maximo]:
            plano = _plano(lista[0].get("item", lista[0]) if isinstance(lista[0].get("item"), dict) else lista[0])
            salida.append({"n": len(lista), "campos": {k: str(v)[:60] for k, v in list(plano.items())[:70]}})
    return salida[:maximo]
