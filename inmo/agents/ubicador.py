import hashlib
import math
import time

import httpx

from ..valoracion import norm

NOMINATIM = "https://nominatim.openstreetmap.org/search"
AGENTE = "inmo-peru/1.0 (github.com/Ser2104/inmo-peru)"
LIMITE_PERU = (-18.4, -81.4, 0.1, -68.6)


def dentro_peru(lat, lng):
    s, o, n, e = LIMITE_PERU
    return s <= lat <= n and o <= lng <= e


def consultar(texto, esperar=1.1):
    r = httpx.get(NOMINATIM, params={"q": texto, "format": "json", "limit": 1, "countrycodes": "pe"}, headers={"User-Agent": AGENTE}, timeout=30)
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

    def ubicar(self, inm):
        lugar = ", ".join(x for x in (inm.get("distrito"), inm.get("provincia"), inm.get("departamento")) if x)
        if inm.get("direccion") and lugar:
            punto = self.buscar(f"{inm['direccion']}, {lugar}, Perú")
            if punto:
                return (*punto, "direccion")
        for texto in (f"{lugar}, Perú" if lugar else None, f"{inm.get('distrito')}, Perú" if inm.get("distrito") else None, f"{inm.get('departamento')}, Perú" if inm.get("departamento") else None):
            if texto:
                punto = self.buscar(texto)
                if punto:
                    return (*desplazar(*punto, inm["id"]), "distrito")
        return None


def ejecutar(db, limite=800):
    pendientes = db.select("inmuebles", select="id,direccion,distrito,provincia,departamento,lat,lng", activo="eq.true", ubicacion_precision="is.null", limit=str(limite))
    u = Ubicador(db)
    ok = 0
    for inm in pendientes:
        if inm.get("lat") and inm.get("lng") and dentro_peru(inm["lat"], inm["lng"]):
            db.update("inmuebles", {"ubicacion_precision": "exacta"}, id=f"eq.{inm['id']}")
            ok += 1
            continue
        r = u.ubicar(inm)
        if r:
            db.update("inmuebles", {"lat": r[0], "lng": r[1], "ubicacion_precision": r[2]}, id=f"eq.{inm['id']}")
            ok += 1
        if u.nuevas >= 900:
            break
    return {"pendientes": len(pendientes), "ubicados": ok, "consultas_nuevas": u.nuevas}
