import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import config, reporte
from .collectors import base, ia, runner
from .db import DB
from .valoracion import analizar, indice_zonas
from .agents import temporal as agente_temporal

app = FastAPI(title="Analizador inmobiliario Perú", version="1.0")
db = DB()


def clave(x_api_key: str = Header(default="")):
    if config.API_KEY and x_api_key != config.API_KEY:
        raise HTTPException(401, "Clave inválida")


class Datos(BaseModel):
    precio: float
    moneda: str = "USD"
    area_m2: Optional[float] = None
    tipo: str = "departamento"
    estado: str = "terminado"
    departamento: str
    provincia: Optional[str] = None
    distrito: Optional[str] = None
    mantenimiento_usd: Optional[float] = None
    fecha_entrega: Optional[str] = None
    titulo: Optional[str] = None


class Pedido(BaseModel):
    url: Optional[str] = None
    datos: Optional[Datos] = None
    renta_mensual_usd: Optional[float] = None
    cuota_inicial: Optional[float] = None
    tasa_hipoteca: Optional[float] = None
    plazo_hipoteca: Optional[int] = None
    gestion_temporal: Optional[float] = None
    guardar: bool = True


def _indice():
    return indice_zonas(db.select_all("zonas_stats", select="*"))


@app.post("/analizar", dependencies=[Depends(clave)])
def analizar_inmueble(pedido: Pedido):
    p = db.parametros()
    for k in ("cuota_inicial", "tasa_hipoteca", "plazo_hipoteca", "gestion_temporal"):
        if getattr(pedido, k) is not None:
            p[k] = getattr(pedido, k)
    if pedido.url:
        try:
            crudos = ia.extraer(base.descargar(pedido.url), pedido.url)
        except Exception as e:
            raise HTTPException(422, f"No se pudo leer el aviso: {e}")
        if not crudos:
            raise HTTPException(422, "No se encontraron datos del inmueble en la página")
        inm = runner.normalizar({**crudos[0], "url": pedido.url}, "manual", p["tipo_cambio"])
    elif pedido.datos:
        d = pedido.datos.model_dump()
        inm = runner.normalizar({**d, "url": f"manual:{uuid.uuid4()}", "operacion": "venta"}, "manual", p["tipo_cambio"])
    else:
        raise HTTPException(400, "Envía url o datos")
    if not inm.get("precio_usd"):
        raise HTTPException(422, "Falta el precio")
    inm["operacion"] = "venta"
    if pedido.guardar:
        inm = {**inm, **runner.guardar(db, [inm])[0]}
    a = analizar(inm, _indice(), p.get("per_distrito") or {}, p, pedido.renta_mensual_usd, temporal=agente_temporal.cargar(db))
    if pedido.guardar and inm.get("id"):
        db.upsert("analisis", a, on_conflict="inmueble_id")
    return {"inmueble": inm, "analisis": a}


@app.get("/oportunidades", dependencies=[Depends(clave)])
def oportunidades(departamento: str = None, distrito: str = None, tipo: str = None, estado: str = None,
                  horizonte: str = "total", min_puntaje: float = 0, precio_max: float = None, limite: int = 50):
    if horizonte not in ("corto", "mediano", "largo", "total"):
        raise HTTPException(400, "horizonte: corto | mediano | largo | total")
    q = {
        "select": "*,inmuebles!inner(url,titulo,tipo,estado,departamento,provincia,distrito,area_m2,dormitorios,activo,sospechoso)",
        "inmuebles.activo": "eq.true",
        "inmuebles.sospechoso": "is.null",
        f"puntaje_{horizonte}": f"gte.{min_puntaje}",
        "order": f"puntaje_{horizonte}.desc",
        "limit": str(min(limite, 500)),
    }
    for campo, valor in (("departamento", departamento), ("distrito", distrito)):
        if valor:
            q[f"inmuebles.{campo}"] = f"ilike.*{valor}*"
    for campo, valor in (("tipo", tipo), ("estado", estado)):
        if valor:
            q[f"inmuebles.{campo}"] = f"eq.{valor}"
    if precio_max:
        q["precio_usd"] = f"lte.{precio_max}"
    return db.select("analisis", **q)


@app.get("/inmuebles/{id}", dependencies=[Depends(clave)])
def inmueble(id: str):
    inm = db.select("inmuebles", select="*", id=f"eq.{id}")
    if not inm:
        raise HTTPException(404, "No existe")
    a = db.select("analisis", select="*", inmueble_id=f"eq.{id}")
    hist = db.select("precios_historial", select="fecha,precio_usd", inmueble_id=f"eq.{id}", order="fecha")
    return {"inmueble": inm[0], "analisis": a[0] if a else None, "historial_precios": hist}


@app.get("/inmuebles/{id}/reporte", response_class=HTMLResponse)
def reporte_html(id: str, k: str = ""):
    clave(k)
    datos = inmueble(id)
    if not datos["analisis"]:
        raise HTTPException(404, "Aún sin análisis")
    return reporte.html(datos["inmueble"], datos["analisis"])


@app.get("/arbitraje", dependencies=[Depends(clave)])
def arbitraje(departamento: str = None, distrito: str = None, min_puntaje: float = 0, limite: int = 50):
    q = {"select": "*,inmuebles!inner(url,titulo,departamento,provincia,distrito,area_m2,dormitorios,activo)", "inmuebles.activo": "eq.true",
         "puntaje": f"gte.{min_puntaje}", "order": "puntaje.desc", "limit": str(min(limite, 500))}
    for campo, valor in (("departamento", departamento), ("distrito", distrito)):
        if valor:
            q[f"inmuebles.{campo}"] = f"ilike.*{valor}*"
    return db.select("arbitraje", **q)


@app.get("/mercado-temporal", dependencies=[Depends(clave)])
def mercado_temporal(departamento: str = None):
    q = {"select": "departamento,provincia,distrito,adr_usd,ocupacion,ingreso_anual_usd,anuncios,fuente,url,periodo,fecha", "fuente": "neq.airroi_inmueble", "order": "ingreso_anual_usd.desc"}
    if departamento:
        q["departamento"] = f"ilike.*{departamento}*"
    return {"mercado": db.select_all("mercado_temporal", **q), "regulacion": db.select_all("regulacion_temporal", select="*")}


@app.get("/zonas", dependencies=[Depends(clave)])
def zonas(departamento: str = None, operacion: str = "venta", minimo: int = 5):
    q = {"select": "*", "operacion": f"eq.{operacion}", "n": f"gte.{minimo}", "order": "mediana_m2_usd.desc"}
    if departamento:
        q["departamento"] = f"ilike.*{departamento}*"
    return db.select_all("zonas_stats", **q)


@app.get("/salud")
def salud():
    return {
        "fuentes": db.select("fuentes", select="id,nombre,activo,ultimo_ok,fallos_seguidos,ultimo_error"),
        "ultimas_ejecuciones": db.select("ejecuciones", select="agente,ok,inicio", order="inicio.desc", limit="20"),
    }
