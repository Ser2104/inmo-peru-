import re
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from . import config


def _searxng(consulta, n):
    r = httpx.get(f"{config.SEARXNG_URL.rstrip('/')}/search", params={"q": consulta, "format": "json", "language": "es-PE"}, timeout=40)
    r.raise_for_status()
    return [{"titulo": x.get("title"), "url": x.get("url"), "resumen": x.get("content")} for x in r.json().get("results", [])[:n]]


def _duckduckgo(consulta, n):
    from .collectors.base import HEADERS
    r = httpx.post("https://html.duckduckgo.com/html/", data={"q": consulta, "kl": "pe-es"}, headers=HEADERS, timeout=40)
    r.raise_for_status()
    salida = []
    for res in BeautifulSoup(r.text, "html.parser").select(".result")[:n]:
        a = res.select_one(".result__a")
        if not a:
            continue
        url = a.get("href", "")
        if "uddg=" in url:
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
        resumen = res.select_one(".result__snippet")
        salida.append({"titulo": a.get_text(" ", strip=True), "url": url, "resumen": resumen.get_text(" ", strip=True) if resumen else ""})
    return salida


def buscar_web(consulta, n=8):
    for motor in (_searxng, _duckduckgo):
        try:
            res = [x for x in motor(consulta, n) if x.get("url", "").startswith("http")]
            if res:
                return res
        except (httpx.HTTPError, ValueError):
            continue
    return []


def texto_pagina(url, limite=4000):
    from .collectors.base import descargar
    try:
        html = descargar(url, intentos=1, pausa=(0.2, 0.5))
    except Exception:
        return ""
    if html.startswith("<pdf>"):
        return html[5:limite + 5]
    sopa = BeautifulSoup(html, "html.parser")
    for e in sopa(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        e.decompose()
    return re.sub(r"\s+", " ", sopa.get_text(" "))[:limite]
