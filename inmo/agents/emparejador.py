import re
from datetime import date, datetime, timezone

from .. import llm
from ..collectors import base

LOTE = 20

PROMPT = """Eres el asistente comercial de un proveedor peruano. Esto es lo que tiene y ofrece:
\"\"\"{perfil}\"\"\"
{zona}
Revisa estas convocatorias y decide, una por una, si este proveedor podría ganarlas y cumplirlas con lo que tiene.
Encaja SOLO si lo que piden como servicio o bien principal es algo que él puede dar directamente (por ejemplo, si tiene camionetas:
alquiler de camionetas, movilidad, transporte de personal). NO encaja si piden comprar vehículos (adquisición), una obra o servicio
que solo menciona vehículos de pasada, otro tipo de vehículo que no tiene (volquete, bus, maquinaria) o algo de otro rubro.
Ante la duda, no encaja.

Devuelve una lista JSON con un objeto por convocatoria: id, encaja (true/false), puntaje (0-100: qué tan bien calza),
razon (máx. 140 caracteres, en español simple), que_piden (máx. 100 caracteres: qué, cuántos, dónde y por cuánto tiempo, si se sabe).

CONVOCATORIAS:
{lista}"""

PROMPT_BASES = """Estas son las bases de una convocatoria del Estado peruano. El proveedor tiene esto:
\"\"\"{perfil}\"\"\"
Extrae un objeto JSON con: fecha_limite (AAAA-MM-DD para presentar ofertas, o null), cantidad (de unidades o servicios),
tipo_requerido (qué vehículo o equipo exacto piden), antiguedad_maxima (años, o null), con_conductor (true/false/null),
plazo (duración del servicio), lugar (dónde se presta), monto_referencial (número o null), requisitos_clave (lista de máx. 6 textos cortos:
RNP, experiencia, SOAT, GPS, seguros, garantías...), cumple (true/false: si con lo que tiene podría cumplir), por_que (máx. 160 caracteres).

BASES:
{texto}"""


def perfil(db, id_="principal"):
    filas = db.select("perfiles", select="*", id=f"eq.{id_}")
    return filas[0] if filas else None


def pendientes(db, p):
    hechas = {c["oportunidad_id"] for c in db.select_all("coincidencias", select="oportunidad_id", perfil_id=f"eq.{p['id']}", version=f"eq.{p['version']}")}
    hoy = date.today().isoformat()
    filas = db.select_all("oportunidades", select="id,titulo,descripcion,entidad,departamento,provincia,distrito,monto_usd,fecha_limite,fecha_publicacion,categoria,metodo")
    deps = set(p.get("departamentos") or [])
    return [o for o in filas if o["id"] not in hechas and (not o.get("fecha_limite") or o["fecha_limite"] >= hoy)
            and (not deps or o.get("departamento") in deps)]


def evaluar(db, maximo=4000):
    p = perfil(db)
    if not p or not llm.disponible():
        return {"omitido": "sin perfil o sin IA"}
    zona = f"Solo trabaja en: {', '.join(p['departamentos'])}." if p.get("departamentos") else "Trabaja en todo el Perú."
    lista = pendientes(db, p)[:maximo]
    encajan = 0
    for k in range(0, len(lista), LOTE):
        lote = lista[k:k + LOTE]
        texto = "\n".join(f"- id={o['id']} | {o.get('titulo') or ''} | {str(o.get('descripcion') or '')[:400]} | pide: {o.get('entidad') or '—'} | "
                          f"lugar: {', '.join(x for x in (o.get('distrito'), o.get('departamento')) if x)} | monto US$ {o.get('monto_usd') or '—'}" for o in lote)
        try:
            datos = llm.pedir_json(PROMPT.format(perfil=p["descripcion"], zona=zona, lista=texto))
        except RuntimeError:
            continue
        por_id = {str(d.get("id")): d for d in datos if isinstance(d, dict)} if isinstance(datos, list) else {}
        filas = []
        for o in lote:
            d = por_id.get(o["id"])
            if not d:
                continue
            encaja = bool(d.get("encaja"))
            encajan += encaja
            filas.append({"oportunidad_id": o["id"], "perfil_id": p["id"], "version": p["version"], "encaja": encaja,
                          "puntaje": int(base.numero(d.get("puntaje")) or 0), "razon": str(d.get("razon") or "")[:200],
                          "que_piden": str(d.get("que_piden") or "")[:160], "bases_leidas": False,
                          "actualizado": datetime.now(timezone.utc).isoformat()})
        db.upsert("coincidencias", filas, on_conflict="oportunidad_id,perfil_id")
    return {"evaluadas": len(lista), "encajan": encajan}


def leer_bases(db, descargar=None, limite=60):
    p = perfil(db)
    if not p or not llm.disponible():
        return {"omitido": "sin perfil o sin IA"}
    descargar = descargar or (lambda url: base.descargar(url, intentos=2))
    candidatas = db.select("coincidencias", select="oportunidad_id,puntaje", perfil_id=f"eq.{p['id']}", encaja="eq.true",
                           bases_leidas="eq.false", order="puntaje.desc", limit=str(limite))
    leidas = 0
    for c in candidatas:
        o = (db.select("oportunidades", select="id,url,fecha_limite", id=f"eq.{c['oportunidad_id']}") or [None])[0]
        if not o or not str(o.get("url") or "").startswith("http"):
            continue
        try:
            texto = descargar(o["url"])
            texto = texto[5:] if texto.startswith("<pdf>") else re.sub(r"<[^>]+>", " ", texto)
            req = llm.pedir_json(PROMPT_BASES.format(perfil=p["descripcion"], texto=texto[:30000]))
        except Exception:
            db.update("coincidencias", {"bases_leidas": True}, oportunidad_id=f"eq.{c['oportunidad_id']}", perfil_id=f"eq.{p['id']}")
            continue
        req = req if isinstance(req, dict) else {}
        cambios = {"requisitos": req, "bases_leidas": True}
        if req.get("cumple") is False:
            cambios.update(encaja=False, razon=str(req.get("por_que") or "Las bases piden algo que no tienes.")[:200])
        db.update("coincidencias", cambios, oportunidad_id=f"eq.{c['oportunidad_id']}", perfil_id=f"eq.{p['id']}")
        limite_f = base.fecha(req.get("fecha_limite")) if req.get("fecha_limite") else None
        if limite_f and not o.get("fecha_limite"):
            db.update("oportunidades", {"fecha_limite": limite_f}, id=f"eq.{o['id']}")
        leidas += 1
    return {"bases_leidas": leidas}


def ejecutar(db):
    return {"evaluar": evaluar(db), "bases": leer_bases(db)}
