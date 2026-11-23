from datetime import datetime, timedelta, timezone

from .. import temporal as tmp
from ..valoracion import calcular_zonas, indice_zonas, analizar
from . import temporal as agente_temporal

CAMPOS = "id,url,tipo,operacion,estado,departamento,provincia,distrito,area_m2,dormitorios,banos,lat,lng,precio_usd,mantenimiento_usd,fecha_entrega,activo,duplicado_de,sospechoso,primera_vez,ultima_vez"


def cargar(db):
    return db.select_all("inmuebles", select=CAMPOS, activo="eq.true")


def actualizar_zonas(db, inmuebles):
    filas = calcular_zonas(inmuebles)
    db.upsert("zonas_stats", filas, on_conflict="departamento,provincia,distrito,tipo,operacion,segmento")
    return indice_zonas(filas)


def ejecutar(db, p, todo=False):
    inmuebles = cargar(db)
    indice = actualizar_zonas(db, inmuebles)
    previos = {a["inmueble_id"]: a for a in db.select_all("analisis", select="inmueble_id,fecha,precio_usd")}
    vence = datetime.now(timezone.utc) - timedelta(days=7)
    per = p.get("per_distrito") or {}
    temporal = agente_temporal.cargar(db)
    salida, arbitrajes = [], []
    for inm in inmuebles:
        if inm.get("duplicado_de") or not inm.get("precio_usd") or inm.get("sospechoso"):
            continue
        if inm["operacion"] == "alquiler":
            if inm.get("tipo") in ("departamento", "casa", None):
                est = tmp.estimar(inm, temporal["indice"], p)
                if est:
                    regla, _ = tmp.regulacion(temporal["reglas"], inm)
                    arbitrajes.append({**tmp.arbitraje(inm, est, p, regla), "fecha": datetime.now(timezone.utc).isoformat()})
            continue
        prev = previos.get(inm["id"])
        if not todo and prev and float(prev["precio_usd"] or 0) == float(inm["precio_usd"]) and datetime.fromisoformat(prev["fecha"].replace("Z", "+00:00")) > vence:
            continue
        a = analizar(inm, indice, per, p, temporal=temporal)
        a["fecha"] = datetime.now(timezone.utc).isoformat()
        salida.append(a)
    db.upsert("analisis", salida, on_conflict="inmueble_id")
    db.upsert("arbitraje", arbitrajes, on_conflict="inmueble_id")
    return {"inmuebles": len(inmuebles), "analizados": len(salida), "arbitrajes": len(arbitrajes), "zonas": len(indice),
            "estrategia_temporal": sum(1 for a in salida if a["estrategia"] == "temporal")}
