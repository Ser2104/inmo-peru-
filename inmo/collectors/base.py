import random
import re
import time
from datetime import datetime

import httpx

try:
    from curl_cffi import requests as cffi
except ImportError:
    cffi = None

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36",
    "Accept-Language": "es-PE,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}


def _texto_pdf(contenido):
    from io import BytesIO
    from pypdf import PdfReader
    paginas = PdfReader(BytesIO(contenido)).pages
    return "\n".join((p.extract_text() or "") for p in paginas[:80])


def descargar(url, intentos=3, pausa=(1.5, 4.0)):
    ultimo = None
    for n in range(intentos):
        try:
            if cffi:
                r = cffi.get(url, impersonate="chrome", headers={"Accept-Language": HEADERS["Accept-Language"]}, timeout=60)
            else:
                r = httpx.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
            if r.status_code == 200:
                time.sleep(random.uniform(*pausa))
                tipo = r.headers.get("content-type", "")
                if "pdf" in tipo or url.lower().split("?")[0].endswith(".pdf"):
                    return "<pdf>" + _texto_pdf(r.content)
                return r.text
            ultimo = f"HTTP {r.status_code}"
            if r.status_code == 404:
                break
        except Exception as e:
            ultimo = str(e)
        time.sleep(2 ** n * 3)
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo}")


def numero(texto):
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    t = re.sub(r"[^\d.,]", "", str(texto))
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        partes = t.split(",")
        t = t.replace(",", "") if len(partes[-1]) == 3 else t.replace(",", ".")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[-1]) == 3):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def precio(texto):
    if not texto:
        return None, None
    t = str(texto).upper()
    usd = re.search(r"(USD|US\$|\$)\s*([\d.,]+)", t)
    pen = re.search(r"S/\.?\s*([\d.,]+)", t)
    if usd:
        return numero(usd.group(2)), "USD"
    if pen:
        return numero(pen.group(1)), "PEN"
    return numero(t), None


def a_usd(monto, moneda, tc):
    if monto is None:
        return None
    return round(monto / tc, 2) if moneda == "PEN" else monto


TIPOS = {
    "departamento": ["departamento", "depa", "dpto", "flat", "duplex", "dúplex", "penthouse"],
    "casa": ["casa", "chalet", "casa de playa"],
    "local": ["local", "tienda", "comercial"],
    "oficina": ["oficina"],
    "terreno": ["terreno", "lote"],
    "edificio": ["edificio"],
    "deposito": ["depósito", "deposito", "baulera"],
    "estacionamiento": ["estacionamiento", "cochera", "parking"],
    "aires": ["aires", "azotea"],
    "industrial": ["local industrial", "almacén", "almacen", "galpón", "galpon", "nave industrial", "planta industrial"],
}
NO_EVALUABLES = ("deposito", "estacionamiento", "aires", "otros")


def tipo_desde(texto):
    t = (texto or "").lower()
    hallados = [(t.find(p), -len(p), tipo) for tipo, palabras in TIPOS.items() for p in palabras if p in t]
    return min(hallados)[2] if hallados else None


def titulo_desde_url(url):
    m = re.search(r"/(?:clasificado|proyecto)/[a-z]+-([a-z0-9-]+)", url or "")
    if not m:
        return None
    texto = re.sub(r"(-\d+)+(\.html)?$", "", m.group(1)).replace("-", " ").strip()
    return texto[:1].upper() + texto[1:] if texto else None


def operacion_desde(texto):
    t = (texto or "").lower()
    if "alquiler" in t or "alquila" in t or "/mes" in t or "rent" in t:
        return "alquiler"
    return "venta"


def estado_desde(texto):
    t = (texto or "").lower()
    if "remate" in t or "subasta" in t or "adjudicad" in t:
        return "remate"
    if "preventa" in t or "pre venta" in t or "pre-venta" in t:
        return "preventa"
    if "en planos" in t or "en construcción" in t or "en construccion" in t or "entrega" in t:
        return "en_planos"
    return "terminado"


def ubicacion(texto):
    partes = [p.strip() for p in re.split(r",", texto or "") if p.strip()]
    if not partes:
        return {}
    if len(partes) >= 3:
        return {"distrito": partes[-3], "provincia": partes[-2], "departamento": partes[-1], "direccion": ", ".join(partes[:-3]) or None}
    if len(partes) == 2:
        return {"distrito": partes[0], "provincia": partes[1], "departamento": partes[1]}
    return {"distrito": partes[0]}


MESES = {m: n for n, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre"], 1)}


def fecha(texto):
    t = str(texto or "").lower().replace("septiembre", "setiembre")
    m = re.search(r"(20\d{2})-(\d{1,2})(?:-(\d{1,2}))?", t)
    if m:
        a, mes, d = int(m[1]), int(m[2]), int(m[3] or 1)
    else:
        anio = re.search(r"20\d{2}", t)
        if not anio:
            return None
        a, mes, d = int(anio.group()), next((n for k, n in MESES.items() if k in t), 12 if re.search(r"fin|diciembre|2do|segundo", t) else 6), 1
    try:
        return datetime(a, mes, d).date().isoformat()
    except ValueError:
        return datetime(a, min(max(mes, 1), 12), 1).date().isoformat()


def limpiar(item, tc):
    item = {k: v for k, v in item.items() if v not in (None, "", [])}
    for campo in ("area_m2", "precio", "precio_usd", "mantenimiento_usd", "mantenimiento"):
        if item.get(campo) is not None and not isinstance(item[campo], (int, float)):
            item[campo] = numero(item[campo])
    if item.get("precio") is not None and not item.get("precio_usd"):
        item["precio_usd"] = a_usd(item["precio"], item.get("moneda"), tc)
    if item.get("mantenimiento") is not None:
        item["mantenimiento_usd"] = a_usd(item.pop("mantenimiento"), item.get("moneda_mantenimiento", "PEN"), tc)
    item.pop("moneda_mantenimiento", None)
    for campo in ("dormitorios", "banos", "estacionamientos"):
        if item.get(campo) is not None:
            m = re.search(r"\d+", str(item[campo]))
            item[campo] = int(m.group()) if m else None
    return item


def telefonos(texto):
    t = texto or ""
    for patron in (r"wa\.me/\+?(\d{9,13})", r"whatsapp\.com/send/?\?phone=\+?(\d{9,13})", r"\+?51[\s.-]?(9\d{2})[\s.-]?(\d{3})[\s.-]?(\d{3})", r"(?<!\d)(9\d{2})[\s.-]?(\d{3})[\s.-]?(\d{3})(?!\d)"):
        m = re.search(patron, t)
        if m:
            numero = "".join(m.groups())
            return numero if numero.startswith("51") else "51" + numero
    return None


def valido(item):
    return bool(str(item.get("url") or "").startswith("http") and item.get("precio_usd") and item["precio_usd"] > 100 and item.get("operacion"))
