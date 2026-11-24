import random
from datetime import date, datetime, timezone

from .. import config, llm, negocios, ubigeo
from ..busqueda import texto_pagina
from ..collectors import base
from ..valoracion import norm
from .ubicador import Ubicador

TIPOS = {
    "traspaso": "traspasos de negocios en marcha (restaurantes, cafeterías, bodegas, minimarkets, gimnasios, lavanderías, farmacias, hospedajes, salones) que se venden en {lugar}: avisos en OLX, Mercado Libre, Urbania, Adondevivir, Facebook Marketplace público, corredores y webs de traspasos",
    "local": "convocatorias, bases o avisos para la concesión de cafeterías, comedores, quioscos, fotocopiadoras, playas de estacionamiento o locales comerciales en universidades, institutos, colegios, hospitales, EsSalud, municipalidades, mercados, aeropuertos, terminales y centros comerciales de {lugar}; incluye SEACE y webs .gob.pe y .edu.pe",
    "estado": "proyectos en concesión, asociaciones público-privadas (APP), iniciativas privadas, usufructos y subastas de inmuebles del Estado de ProInversión, la SBN, el gobierno regional y las municipalidades de {lugar}",
}
CAMPOS = """nombre, rubro ({rubros}), entidad (quién lo ofrece), url, mencionado_en, departamento, provincia, distrito, direccion, area_m2,
inversion (precio del traspaso o inversión requerida), canon_mensual (alquiler o canon a pagar al mes), ventas_mensuales, utilidad_mensual (solo si la declaran),
plazo_meses (duración del contrato o concesión), fecha_limite (AAAA-MM-DD para postular), etapa (para proyectos del Estado), moneda (USD|PEN), telefono,
descripcion (máx. 300 caracteres)""".format(rubros=negocios.RUBROS)
PROMPT = """Busca en internet {que}. Prioriza lo vigente: publicado en los últimos 90 días o con fecha límite futura.
Devuelve una lista JSON (máximo 20) de objetos con: """ + CAMPOS + """.
No inventes datos: usa null si no aparece."""
PROMPT_DETALLE = """Esta es información sobre "{nombre}" ({tipo}) en {distrito}, {departamento}, Perú.
Devuelve un objeto JSON con: """ + CAMPOS + """.
Usa null en lo que no aparezca; no inventes.

TEXTO:
{texto}"""
MONTOS = {"inversion": "inversion_usd", "canon_mensual": "canon_mensual_usd", "ventas_mensuales": "ventas_mensuales_usd", "utilidad_mensual": "utilidad_declarada_usd"}
TEXTOS = ("nombre", "rubro", "entidad", "url", "mencionado_en", "direccion", "etapa", "descripcion")


def _fecha(x):
    try:
        return date.fromisoformat(str(x)[:10]).isoformat()
    except ValueError:
        return None


def normalizar(x, tipo, departamento, tc):
    moneda = (x.get("moneda") or ("USD" if tipo == "estado" else "PEN")).upper()
    fila = {c: str(x[c])[:500] for c in TEXTOS if x.get(c)}
    for origen, destino in MONTOS.items():
        v = base.numero(x.get(origen))
        if v is not None:
            fila[destino] = round(v / tc if moneda == "PEN" else v, 2)
    for c in ("area_m2", "plazo_meses"):
        v = base.numero(x.get(c))
        if v:
            fila[c] = int(v) if c == "plazo_meses" else v
    if _fecha(x.get("fecha_limite")):
        fila["fecha_limite"] = _fecha(x.get("fecha_limite"))
    if x.get("rubro") and norm(x["rubro"]).replace(" ", "_") in negocios.MARGEN:
        fila["rubro"] = norm(x["rubro"]).replace(" ", "_")
    lugar = ubigeo.resolver(x.get("distrito"), x.get("provincia"), x.get("departamento") or departamento)
    fila.update({k: lugar.get(k) or x.get(k) for k in ("departamento", "provincia", "distrito") if lugar.get(k) or x.get(k)})
    fila["departamento"] = fila.get("departamento") or departamento
    tel = base.telefonos(str(x.get("telefono") or ""))
    if tel:
        fila["telefono"] = tel
    return fila


def clave(tipo, fila):
    nombre = norm(fila.get("nombre"))
    return f"{tipo}|{nombre}|{norm(fila.get('distrito'))}" if len(nombre) > 3 else f"{tipo}|{norm(fila.get('url') or fila.get('mencionado_en') or '')}"


def guardar(db, items, tipo, departamento, tc):
    existentes = {f["clave"]: f["id"] for f in db.select_all("concesiones", select="clave,id")}
    nuevas, ahora = 0, datetime.now(timezone.utc).isoformat()
    for x in items if isinstance(items, list) else []:
        if not isinstance(x, dict) or not (x.get("nombre") or x.get("url")):
            continue
        fila = normalizar(x, tipo, departamento, tc)
        if not any(str(fila.get(c) or "").startswith("http") for c in ("url", "mencionado_en")) and not fila.get("telefono"):
            continue
        k = clave(tipo, fila)
        if k.endswith("|"):
            continue
        if k in existentes:
            db.update("concesiones", {**fila, "visto": ahora}, id=f"eq.{existentes[k]}")
        else:
            existentes[k] = db.upsert("concesiones", {**fila, "clave": k, "tipo": tipo}, on_conflict="clave", devolver=True)[0]["id"]
            nuevas += 1
    return nuevas


def buscar(db, p, cantidad=None):
    if not llm.disponible():
        return {"omitido": "sin IA"}
    cantidad = cantidad or (30 if config.OPENAI_API_KEY else 6)
    conteo = {d: 0 for d in config.DEPARTAMENTOS}
    for f in db.select_all("concesiones", select="departamento"):
        if f.get("departamento") in conteo:
            conteo[f["departamento"]] += 1
    pares = list(dict.fromkeys(random.choices([(d, t) for d in conteo for t in TIPOS], weights=[1 / (1 + conteo[d]) ** 0.5 for d in conteo for _ in TIPOS], k=cantidad * 2)))[:cantidad]
    if not any(t == "estado" for _, t in pares):
        pares.append(("Lima", "estado"))
    resumen = []
    for dep, tipo in pares:
        try:
            datos = llm.pedir_json(PROMPT.format(que=TIPOS[tipo].format(lugar=f"el departamento de {dep}, Perú")), buscar=True)
            resumen.append({"departamento": dep, "tipo": tipo, "nuevas": guardar(db, datos, tipo, dep, p["tipo_cambio"])})
        except Exception as e:
            resumen.append({"departamento": dep, "tipo": tipo, "error": str(e)[:200]})
    return {"busquedas": resumen}


def _completar(db, c, texto, p, extra=None):
    datos = llm.pedir_json(PROMPT_DETALLE.format(texto=texto[:15000], **{k: c.get(k) or "" for k in ("nombre", "tipo", "distrito", "departamento")}))
    fila = normalizar(datos if isinstance(datos, dict) else {}, c["tipo"], c.get("departamento"), p["tipo_cambio"])
    fila = {k: v for k, v in fila.items() if v is not None and c.get(k) is None and k != "nombre"}
    tel = c.get("telefono") or base.telefonos(texto)
    db.update("concesiones", {**fila, **({"telefono": tel} if tel else {}), **(extra or {})}, id=f"eq.{c['id']}")


def completar(db, p, limite=40):
    if not llm.disponible():
        return {"omitido": "sin IA"}
    hechas = 0
    for c in db.select("concesiones", select="*", revisado="eq.false", limit=str(limite)):
        textos = [texto_pagina(u, 15000) for u in (c.get("url"), c.get("mencionado_en")) if u and u.startswith("http")]
        try:
            _completar(db, c, "\n\n".join(t for t in textos if t) or (c.get("descripcion") or ""), p, {"revisado": True})
            hechas += 1
        except RuntimeError:
            continue
    respuestas = 0
    for c in db.select("concesiones", select="*", contacto_estado="eq.respondido", limit="50"):
        try:
            _completar(db, {**c, **{k: None for k in MONTOS.values()}}, c.get("respuesta") or "", p, {"contacto_estado": "procesado"})
            respuestas += 1
        except RuntimeError:
            continue
    return {"completadas": hechas, "respuestas_procesadas": respuestas}


def analizar(db, p):
    ubicador = Ubicador(db)
    conteo = {}
    for c in db.select_all("concesiones", select="*"):
        r = negocios.veredicto(c, p)
        cambios = {k: r.get(k) for k in ("veredicto", "puntaje", "tir_anual", "van_usd", "payback_meses", "utilidad_mensual_usd", "riesgos")}
        cambios["detalle"] = {k: r[k] for k in ("van_pesimista_usd", "tir_pesimista", "tasa_exigida", "margen_usado") if k in r}
        if c.get("lat") is None:
            punto = ubicador.ubicar(c)
            if punto:
                cambios.update(lat=punto[0], lng=punto[1])
        db.update("concesiones", cambios, id=f"eq.{c['id']}")
        conteo[r["veredicto"]] = conteo.get(r["veredicto"], 0) + 1
    return conteo


def ejecutar(db, p):
    return {"buscar": buscar(db, p), "completar": completar(db, p), "analizar": analizar(db, p)}
