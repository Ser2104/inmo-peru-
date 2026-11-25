import math
import time

import httpx

OVERPASS = "https://overpass-api.de/api/interpreter"
RADIO = 500

CATEGORIAS = {
    "universidad": lambda t: t.get("amenity") in ("university", "college"),
    "colegio": lambda t: t.get("amenity") in ("school", "kindergarten"),
    "hospital": lambda t: t.get("amenity") in ("hospital", "clinic", "doctors"),
    "mercado": lambda t: t.get("amenity") == "marketplace" or t.get("shop") in ("mall", "supermarket", "department_store"),
    "oficina": lambda t: "office" in t,
    "paradero": lambda t: t.get("highway") == "bus_stop" or t.get("public_transport") in ("platform", "station"),
    "turismo": lambda t: t.get("tourism") in ("attraction", "museum", "viewpoint"),
    "tienda": lambda t: "shop" in t,
    "cafe": lambda t: t.get("amenity") == "cafe",
    "restaurante": lambda t: t.get("amenity") in ("restaurant", "fast_food", "food_court"),
    "farmacia": lambda t: t.get("amenity") == "pharmacy" or t.get("shop") == "chemist",
    "gimnasio": lambda t: t.get("leisure") == "fitness_centre",
    "lavanderia": lambda t: t.get("shop") in ("laundry", "dry_cleaning"),
    "bodega": lambda t: t.get("shop") in ("convenience", "kiosk", "general"),
    "estacionamiento": lambda t: t.get("amenity") == "parking",
    "fotocopiadora": lambda t: t.get("shop") in ("copyshop", "stationery"),
    "hospedaje": lambda t: t.get("tourism") in ("hotel", "hostel", "guest_house", "motel"),
    "salon": lambda t: t.get("shop") in ("hairdresser", "beauty"),
}

NOMBRES = {"universidad": "universidades o institutos", "colegio": "colegios", "hospital": "hospitales o clínicas", "mercado": "mercados o centros comerciales",
           "oficina": "oficinas", "paradero": "paraderos", "turismo": "atractivos turísticos", "tienda": "tiendas"}

RUBROS = {
    "cafeteria": ({"universidad": 5, "colegio": 1, "oficina": 1, "hospital": 2, "paradero": 0.3, "tienda": 0.1}, "cafe"),
    "restaurante": ({"oficina": 1, "universidad": 3, "hospital": 2, "mercado": 2, "paradero": 0.3, "tienda": 0.1, "turismo": 1}, "restaurante"),
    "comida_rapida": ({"universidad": 4, "colegio": 2, "mercado": 2, "paradero": 0.5, "tienda": 0.1}, "restaurante"),
    "bodega": ({"colegio": 1, "paradero": 0.3, "tienda": 0.05, "hospital": 0.5}, "bodega"),
    "minimarket": ({"colegio": 1, "paradero": 0.3, "tienda": 0.05, "universidad": 1}, "bodega"),
    "farmacia": ({"hospital": 4, "mercado": 1, "paradero": 0.3, "tienda": 0.1}, "farmacia"),
    "libreria": ({"universidad": 5, "colegio": 3, "oficina": 0.5}, "fotocopiadora"),
    "fotocopiadora": ({"universidad": 5, "colegio": 3, "oficina": 0.5}, "fotocopiadora"),
    "gimnasio": ({"oficina": 1, "universidad": 2, "tienda": 0.1, "paradero": 0.2}, "gimnasio"),
    "lavanderia": ({"universidad": 2, "hospedaje": 1, "tienda": 0.05, "paradero": 0.2}, "lavanderia"),
    "estacionamiento": ({"mercado": 3, "hospital": 3, "oficina": 1, "universidad": 2}, "estacionamiento"),
    "quiosco": ({"paradero": 1, "colegio": 2, "universidad": 2, "hospital": 2}, "bodega"),
    "hospedaje": ({"turismo": 3, "paradero": 0.3, "hospital": 1}, "hospedaje"),
    "salon_belleza": ({"tienda": 0.1, "oficina": 0.5, "paradero": 0.2}, "salon"),
    "otro": ({"tienda": 0.1, "paradero": 0.3, "oficina": 0.5, "universidad": 1, "hospital": 1, "mercado": 1}, None),
}

CONSULTA = """[out:json][timeout:60];
(nwr(around:{r},{lat},{lng})[amenity];nwr(around:{r},{lat},{lng})[shop];nwr(around:{r},{lat},{lng})[office];
 nwr(around:{r},{lat},{lng})[leisure=fitness_centre];nwr(around:{r},{lat},{lng})[highway=bus_stop];
 nwr(around:{r},{lat},{lng})[public_transport];nwr(around:{r},{lat},{lng})[tourism];);
out tags;"""


def contar(elementos):
    conteo = {c: 0 for c in CATEGORIAS}
    for e in elementos:
        t = e.get("tags") or {}
        for c, es in CATEGORIAS.items():
            if es(t):
                conteo[c] += 1
    return conteo


def consultar(lat, lng):
    for intento in range(3):
        r = httpx.post(OVERPASS, data={"data": CONSULTA.format(r=RADIO, lat=lat, lng=lng)}, headers={"User-Agent": "inmo-peru/1.0"}, timeout=90)
        if r.status_code == 200:
            return contar(r.json().get("elements", []))
        time.sleep(10 * (intento + 1))
    r.raise_for_status()


def puntaje(conteo, rubro):
    pesos, rival = RUBROS.get(rubro) or RUBROS["otro"]
    demanda = sum(w * conteo.get(c, 0) for c, w in pesos.items())
    competidores = conteo.get(rival, 0) if rival else 0
    actividad = 10 * (1 - math.exp(-demanda / 12))
    saturacion = competidores / max(1.0, demanda / 8)
    return round(max(0.0, actividad - min(5.0, 1.5 * max(0.0, saturacion - 1))), 1), demanda, competidores


def resumen(conteo, rubro):
    p, demanda, competidores = puntaje(conteo, rubro)
    pesos, rival = RUBROS.get(rubro) or RUBROS["otro"]
    cerca = [f"{conteo[c]} {NOMBRES.get(c, c)}" for c in sorted(pesos, key=lambda c: -pesos[c] * conteo.get(c, 0)) if conteo.get(c)][:4]
    mejores = sorted(((r, puntaje(conteo, r)[0]) for r in RUBROS if r != "otro"), key=lambda x: -x[1])[:3]
    return {"puntaje": p, "rubro": rubro, "cerca": cerca, "competidores": competidores, "mejores_rubros": mejores, "radio_m": RADIO}


class Entorno:
    def __init__(self, db, consultar_fn=None):
        self.db, self.consultar = db, consultar_fn or (lambda lat, lng: consultar(lat, lng))
        self.cache = {f["clave"]: f["conteos"] for f in db.select_all("entorno", select="clave,conteos")}
        self.nuevas = 0

    def conteos(self, lat, lng):
        clave = f"{round(lat, 3)}|{round(lng, 3)}"
        if clave not in self.cache:
            self.cache[clave] = self.consultar(round(lat, 3), round(lng, 3))
            self.db.upsert("entorno", {"clave": clave, "conteos": self.cache[clave]}, on_conflict="clave")
            self.nuevas += 1
            time.sleep(1)
        return self.cache[clave]
