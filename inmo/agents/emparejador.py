import re
from datetime import date, datetime, timezone

from .. import llm
from ..collectors import base
from ..valoracion import norm

LOTE = 20

PROMPT = """Eres el asistente comercial de un proveedor peruano. Esto es lo que tiene y ofrece:
\"\"\"{perfil}\"\"\"
Sus equipos: {activos}
{zona}
Revisa estas convocatorias y decide, una por una, si este proveedor podría ganarlas y cumplirlas con lo que tiene.
Encaja SOLO si lo que piden como servicio o bien principal es algo que él puede dar directamente (por ejemplo, si tiene camionetas:
alquiler de camionetas, movilidad, transporte de personal). NO encaja si piden comprar vehículos (adquisición), una obra o servicio
que solo menciona vehículos de pasada, otro tipo de vehículo que no tiene (volquete, bus, maquinaria) o algo de otro rubro.
Ante la duda, no encaja.

Devuelve una lista JSON con un objeto por convocatoria: id, encaja (true/false), puntaje (0-100: qué tan bien calza),
razon (máx. 140 caracteres, en español simple: qué de lo suyo usaría), que_piden (máx. 100 caracteres: qué, cuántos, dónde y por cuánto tiempo, si se sabe).
Compara también cantidades: si piden más unidades de las que tiene, baja el puntaje y dilo en la razón.

CONVOCATORIAS:
{lista}"""

PROMPT_BASES = """Estas son las bases de una convocatoria del Estado peruano. El proveedor tiene esto:
\"\"\"{perfil}\"\"\"
Sus equipos: {activos}
{empresa}
Sus costos: {costos}

Extrae un objeto JSON con:
fecha_limite (AAAA-MM-DD para presentar ofertas, o null), cantidad, tipo_requerido (qué vehículo o equipo exacto piden),
antiguedad_maxima (años, o null), con_conductor (true/false/null), plazo (duración del servicio), lugar (dónde se presta),
monto_referencial (número en soles, o null), requisitos_clave (máx. 6 textos cortos),
cumple (true/false: si con lo que tiene podría cumplir), por_que (máx. 160 caracteres),
sin_empresa (true si las bases permiten postular como persona natural con RUC, false si exigen persona jurídica o una autorización
que solo dan a empresas, null si no lo dicen), sin_empresa_por_que (máx. 160 caracteres),
para_postular (lista de lo que debe tener o tramitar antes, con costo si lo sabes: RUC activo y habido, RNP de bienes/servicios,
autorización MTC, licencias, SOAT, GPS, pólizas, experiencia mínima, garantías...),
costos (lista de objetos {{concepto, soles}} con lo que le costaría cumplir TODO el contrato: combustible, conductores, mantenimiento,
seguros/SOAT, GPS, trámites, garantías o retención, impuestos; usa sus costos si los dio, si no usa precios típicos del Perú),
costos_estimados (true si usaste precios típicos y no los suyos), ingreso_soles (monto que cobraría), ganancia_soles, margen (0 a 1).
Si las bases no dan un dato, usa null. No inventes requisitos que no aparezcan.

BASES:
{texto}"""


def items_texto(o):
    return "; ".join(f"{i.get('cantidad') or '?'} {i.get('unidad') or ''} {i.get('clase') or i.get('descripcion') or ''}".strip() for i in (o.get("items") or [])[:8]) or "—"


def activos_texto(p):
    return "; ".join(f"{a.get('cantidad') or 1} × {a.get('que')}{(' (' + a['detalle'] + ')') if a.get('detalle') else ''}" for a in (p.get("activos") or [])) or "ver descripción"


PROMPT_PALABRAS = """Un proveedor peruano tiene esto: \"\"\"{perfil}\"\"\" Equipos: {activos}.
Escribe una lista JSON de 30 a 60 palabras o frases cortas (en minúsculas, sin tildes) que aparecerían en una convocatoria
que él podría ganar: sinónimos, tipos de vehículo o equipo, servicios y formas en que el Estado lo escribe (ej. "unidad vehicular").
Sé amplio: es mejor incluir de más que dejar fuera una convocatoria buena."""


def palabras(db, p):
    clave = f"palabras_perfil_{p['id']}_{p['version']}"
    guardado = db.select("parametros", select="valor", clave=f"eq.{clave}")
    if guardado:
        return guardado[0]["valor"]
    lista = llm.pedir_json(PROMPT_PALABRAS.format(perfil=p["descripcion"], activos=activos_texto(p)))
    lista = [norm(str(x)) for x in (lista if isinstance(lista, list) else []) if str(x).strip()]
    if lista:
        db.upsert("parametros", {"clave": clave, "valor": lista}, on_conflict="clave")
    return lista


def perfil(db, id_="principal"):
    filas = db.select("perfiles", select="*", id=f"eq.{id_}")
    return filas[0] if filas else None


def pendientes(db, p):
    hechas = {c["oportunidad_id"] for c in db.select_all("coincidencias", select="oportunidad_id", perfil_id=f"eq.{p['id']}", version=f"eq.{p['version']}")}
    hoy = date.today().isoformat()
    filas = db.select_all("oportunidades", select="id,titulo,descripcion,entidad,departamento,provincia,distrito,monto_usd,fecha_limite,fecha_publicacion,categoria,metodo,items")
    deps = set(p.get("departamentos") or [])
    return [o for o in filas if o["id"] not in hechas and (not o.get("fecha_limite") or o["fecha_limite"] >= hoy)
            and (not deps or o.get("departamento") in deps)]


def evaluar(db, maximo=4000):
    p = perfil(db)
    if not p or not llm.disponible():
        return {"omitido": "sin perfil o sin IA"}
    zona = f"Solo trabaja en: {', '.join(p['departamentos'])}." if p.get("departamentos") else "Trabaja en todo el Perú."
    lista = pendientes(db, p)[:maximo]
    try:
        claves = palabras(db, p)
    except RuntimeError:
        claves = []
    if claves:
        texto_de = lambda o: norm(f"{o.get('titulo') or ''} {o.get('descripcion') or ''} {items_texto(o)}")
        fuera = [o for o in lista if not any(k in texto_de(o) for k in claves)]
        lista = [o for o in lista if o not in fuera]
        ahora = datetime.now(timezone.utc).isoformat()
        filas = [{"oportunidad_id": o["id"], "perfil_id": p["id"], "version": p["version"], "encaja": False, "puntaje": 0,
                  "razon": "No menciona nada relacionado con lo que ofreces.", "que_piden": "", "bases_leidas": False, "actualizado": ahora} for o in fuera]
        for k in range(0, len(filas), 500):
            db.upsert("coincidencias", filas[k:k + 500], on_conflict="oportunidad_id,perfil_id")
    encajan = 0
    for k in range(0, len(lista), LOTE):
        lote = lista[k:k + LOTE]
        texto = "\n".join(f"- id={o['id']} | {o.get('titulo') or ''} | {str(o.get('descripcion') or '')[:400]} | pide: {o.get('entidad') or '—'} | "
                          f"lugar: {', '.join(x for x in (o.get('distrito'), o.get('departamento')) if x)} | monto US$ {o.get('monto_usd') or '—'} | ítems: {items_texto(o)}" for o in lote)
        try:
            datos = llm.pedir_json(PROMPT.format(perfil=p["descripcion"], activos=activos_texto(p), zona=zona, lista=texto))
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
    return {"evaluadas_con_ia": len(lista), "descartadas_sin_ia": len(fuera) if claves else 0, "encajan": encajan}


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
            req = llm.pedir_json(PROMPT_BASES.format(perfil=p["descripcion"], activos=activos_texto(p), texto=texto[:30000],
                                                     empresa="Tiene empresa (persona jurídica)." if p.get("tiene_empresa") else "NO tiene empresa: es persona natural.",
                                                     costos=p.get("costos") or "no los indicó"))
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
