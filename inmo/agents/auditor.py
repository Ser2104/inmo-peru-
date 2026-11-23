import math
from datetime import datetime, timedelta, timezone

from ..valoracion import norm, indice_zonas, calcular_zonas, buscar_zona


def huella(i):
    area = round(float(i.get("area_m2") or 0))
    precio = round(math.log(float(i["precio_usd"])) / math.log(1.01))
    return (norm(i.get("distrito")), i.get("tipo"), i["operacion"], area, i.get("dormitorios"), precio)


def duplicados(inmuebles):
    grupos = {}
    for i in inmuebles:
        if i.get("precio_usd") and i.get("area_m2"):
            grupos.setdefault(huella(i), []).append(i)
    marcas = {}
    for g in grupos.values():
        if len(g) > 1:
            g.sort(key=lambda x: x["primera_vez"])
            for otro in g[1:]:
                marcas[otro["id"]] = g[0]["id"]
    return marcas


def sospechosos(inmuebles, indice):
    marcas = {}
    for i in inmuebles:
        motivo = None
        precio, area = float(i.get("precio_usd") or 0), float(i.get("area_m2") or 0)
        if area and (area < 15 or area > 50000):
            motivo = f"área rara ({area} m²)"
        elif i["operacion"] == "venta" and precio < 5000:
            motivo = "precio de venta demasiado bajo"
        elif i["operacion"] == "alquiler" and precio > 30000:
            motivo = "alquiler demasiado alto (¿es venta?)"
        elif area:
            z, _ = buscar_zona(indice, i, i["operacion"], 10)
            if z:
                m2 = precio / area
                if m2 < z["mediana_m2_usd"] * 0.25 or m2 > z["mediana_m2_usd"] * 4:
                    motivo = f"precio por m² fuera de rango (zona: {z['mediana_m2_usd']:.0f} US$/m²)"
        if motivo:
            marcas[i["id"]] = motivo
    return marcas


def ejecutar(db, dias_vencido=21):
    inmuebles = db.select_all("inmuebles", select="id,operacion,tipo,departamento,provincia,distrito,area_m2,dormitorios,precio_usd,primera_vez,ultima_vez,activo,duplicado_de,sospechoso", activo="eq.true")
    limite = datetime.now(timezone.utc) - timedelta(days=dias_vencido)
    vencidos = [i["id"] for i in inmuebles if datetime.fromisoformat(i["ultima_vez"].replace("Z", "+00:00")) < limite]
    for k in range(0, len(vencidos), 200):
        db.update("inmuebles", {"activo": False}, id=f"in.({','.join(vencidos[k:k + 200])})")
    vivos = [i for i in inmuebles if i["id"] not in set(vencidos)]
    dups = duplicados(vivos)
    for id_, original in dups.items():
        db.update("inmuebles", {"duplicado_de": original}, id=f"eq.{id_}")
    indice = indice_zonas(calcular_zonas([i for i in vivos if i["id"] not in dups]))
    raros = sospechosos(vivos, indice)
    for id_, motivo in raros.items():
        db.update("inmuebles", {"sospechoso": motivo}, id=f"eq.{id_}")
    return {"revisados": len(inmuebles), "vencidos": len(vencidos), "duplicados": len(dups), "sospechosos": len(raros)}
