import hashlib
import math
import time

import json
from functools import lru_cache
from pathlib import Path

import httpx

from ..valoracion import norm

NOMINATIM = "https://nominatim.openstreetmap.org/search"
AGENTE = "inmo-peru/1.0 (github.com/Ser2104/inmo-peru)"
LIMITE_PERU = (-18.4, -81.4, 0.1, -68.6)
POBLADO = "poblado|"
MAX_KM_DIRECCION = 8


@lru_cache
def capitales():
    return json.loads((Path(__file__).resolve().parent.parent / "data" / "capitales.json").read_text())


def capital(inm):
    dep, prov, dist = (norm(inm.get(k)) for k in ("departamento", "provincia", "distrito"))
    c = capitales()
    if f"{dep}|{prov}|{dist}" in c:
        return tuple(c[f"{dep}|{prov}|{dist}"])
    opciones = [v for k, v in c.items() if k.startswith(f"{dep}|") and k.endswith(f"|{dist}")] if dist else []
    if len(opciones) == 1:
        return tuple(opciones[0])
    if not dist and prov and f"{dep}|{prov}|{prov}" in c:
        return tuple(c[f"{dep}|{prov}|{prov}"])
    return None


def km(a, b):
    return 6371 * math.acos(min(1, math.sin(math.radians(a[0])) * math.sin(math.radians(b[0])) + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(a[1] - b[1]))))


def dentro_peru(lat, lng):
    s, o, n, e = LIMITE_PERU
    return s <= lat <= n and o <= lng <= e


def consultar(texto, esperar=1.1):
    poblado = texto.startswith(POBLADO)
    params = {"q": texto.removeprefix(POBLADO), "format": "json", "limit": 1, "countrycodes": "pe"}
    if poblado:
        params["featureType"] = "settlement"
    r = httpx.get(NOMINATIM, params=params, headers={"User-Agent": AGENTE}, timeout=30)
    time.sleep(esperar)
    r.raise_for_status()
    datos = r.json()
    if not datos:
        return None
    lat, lng = float(datos[0]["lat"]), float(datos[0]["lon"])
    return (lat, lng) if dentro_peru(lat, lng) else None


def desplazar(lat, lng, semilla, metros=350):
    h = hashlib.md5(semilla.encode()).digest()
    angulo = h[0] / 255 * 2 * math.pi
    r = metros * (0.3 + 0.7 * h[1] / 255)
    return lat + r / 111_000 * math.cos(angulo), lng + r / (111_000 * math.cos(math.radians(lat))) * math.sin(angulo)


class Ubicador:
    def __init__(self, db, consultar_fn=None):
        self.db, self.consultar = db, consultar_fn or (lambda texto: consultar(texto))
        self.cache = {f["consulta"]: (f["lat"], f["lng"]) for f in db.select_all("geocache", select="consulta,lat,lng")}
        self.nuevas = 0

    def buscar(self, texto):
        clave = norm(texto)
        if clave in self.cache:
            return self.cache[clave] if self.cache[clave][0] is not None else None
        try:
            punto = self.consultar(texto)
        except httpx.HTTPError:
            return None
        self.cache[clave] = punto or (None, None)
        self.db.upsert("geocache", {"consulta": clave, "lat": punto[0] if punto else None, "lng": punto[1] if punto else None}, on_conflict="consulta")
        self.nuevas += 1
        return punto

    def centro(self, inm):
        punto = capital(inm)
        if punto:
            return punto
        lugar = ", ".join(x for x in (inm.get("distrito"), inm.get("provincia"), inm.get("departamento")) if x)
        opciones = [f"{POBLADO}{lugar}, Perú" if lugar else None, f"{POBLADO}{inm.get('distrito')}, {inm.get('departamento')}, Perú" if inm.get("distrito") else None,
                    f"{lugar}, Perú" if lugar else None, f"{POBLADO}{inm.get('departamento')}, Perú" if inm.get("departamento") else None]
        for texto in opciones:
            if texto:
                punto = self.buscar(texto)
                if punto:
                    return punto
        return None

    def ubicar(self, inm):
        centro = self.centro(inm)
        lugar = ", ".join(x for x in (inm.get("distrito"), inm.get("provincia"), inm.get("departamento")) if x)
        if inm.get("direccion") and lugar:
            punto = self.buscar(f"{inm['direccion']}, {lugar}, Perú")
            if punto and (not centro or km(punto, centro) <= MAX_KM_DIRECCION):
                return (*punto, "direccion")
        return (*desplazar(*centro, inm["id"]), "distrito") if centro else None


def guardar_lote(db, lote):
    if not lote:
        return 0
    if hasattr(db, "rpc_ubicar"):
        return db.rpc_ubicar(lote)
    db.rpc("ubicar_lote", filas=lote)
    return len(lote)


def ejecutar(db, limite_direcciones=700):
    u = Ubicador(db)
    pendientes = db.select_all("inmuebles", select="id,direccion,distrito,provincia,departamento,lat,lng", activo="eq.true", ubicacion_precision="is.null")
    rapidos, lote = 0, []
    for inm in pendientes:
        if inm.get("lat") and inm.get("lng") and dentro_peru(inm["lat"], inm["lng"]):
            lote.append({"id": inm["id"], "lat": inm["lat"], "lng": inm["lng"], "ubicacion_precision": "exacta"})
        else:
            r = u.ubicar({**inm, "direccion": None})
            if r:
                lote.append({"id": inm["id"], "lat": r[0], "lng": r[1], "ubicacion_precision": r[2]})
        if len(lote) >= 500:
            rapidos += guardar_lote(db, lote)
            lote = []
    rapidos += guardar_lote(db, lote)
    afinados = 0
    por_afinar = db.select("inmuebles", select="id,direccion,distrito,provincia,departamento", activo="eq.true", ubicacion_precision="eq.distrito", direccion="not.is.null", limit=str(limite_direcciones * 2))
    for inm in por_afinar:
        if u.nuevas >= limite_direcciones:
            break
        lugar = ", ".join(x for x in (inm.get("distrito"), inm.get("provincia"), inm.get("departamento")) if x)
        punto = u.buscar(f"{inm['direccion']}, {lugar}, Perú") if lugar else None
        centro = u.centro(inm)
        if punto and (not centro or km(punto, centro) <= MAX_KM_DIRECCION):
            db.update("inmuebles", {"lat": punto[0], "lng": punto[1], "ubicacion_precision": "direccion"}, id=f"eq.{inm['id']}")
            afinados += 1
    return {"ubicados_por_distrito": rapidos, "afinados_por_direccion": afinados, "consultas_nuevas": u.nuevas}


def reubicar(db, tabla="inmuebles"):
    u = Ubicador(db)
    filas = db.select_all(tabla, select="id,distrito,provincia,departamento,lat,lng" + (",ubicacion_precision" if tabla == "inmuebles" else ""), activo="eq.true") if tabla == "inmuebles" else db.select_all(tabla, select="id,distrito,provincia,departamento,lat,lng")
    movidos, lote = 0, []
    for f in filas:
        if f.get("lat") is None or f.get("ubicacion_precision") == "exacta":
            continue
        centro = u.centro(f)
        if not centro:
            continue
        if f.get("ubicacion_precision") == "direccion" and km((f["lat"], f["lng"]), centro) <= MAX_KM_DIRECCION:
            continue
        lat, lng = desplazar(*centro, f["id"])
        if tabla == "inmuebles":
            lote.append({"id": f["id"], "lat": lat, "lng": lng, "ubicacion_precision": "distrito"})
            if len(lote) >= 500:
                guardar_lote(db, lote)
                lote = []
        else:
            db.update(tabla, {"lat": lat, "lng": lng}, id=f"eq.{f['id']}")
        movidos += 1
    guardar_lote(db, lote)
    return {"reubicados": movidos, "consultas_nuevas": u.nuevas}
