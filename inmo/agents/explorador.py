import random
import re
from datetime import datetime, timezone

from .. import config, llm
from ..collectors import base, ia, runner
from ..valoracion import norm

CATEGORIAS = {
    "constructoras_pequenas": "webs propias de constructoras, inmobiliarias pequeñas y promotores independientes con proyectos o edificios multifamiliares en venta en {lugar}",
    "foros": "foros y comunidades (SkyscraperCity, Reddit, grupos públicos, blogs) donde se mencionen proyectos inmobiliarios nuevos o en construcción en {lugar}",
    "noticias": "noticias de diarios nacionales y regionales sobre lanzamientos de proyectos inmobiliarios, condominios, lotizaciones o habilitaciones urbanas en {lugar}",
    "remates": "remates judiciales (REMAJU), subastas de SUNAT o SBN y remates de cajas municipales, cooperativas y bancos de inmuebles en {lugar}",
    "adjudicados": "inmuebles adjudicados en venta de bancos (BCP, BBVA, Interbank, Scotiabank, BanBif, Pichincha) y cajas municipales en {lugar}",
    "estatales": "proyectos de vivienda con Crédito Mivivienda, Mivivienda Verde o Techo Propio en {lugar}",
    "licencias": "licencias de edificación o habilitación urbana aprobadas recientemente por municipalidades de {lugar} para edificios o condominios",
    "terrenos": "terrenos, lotes y casas para demoler en venta, con buen precio, en {lugar}",
    "corredores": "corredores inmobiliarios independientes, RE/MAX, Century 21, Babilonia, Infocasas, LaEncontré, OLX o Mercado Libre con avisos en {lugar}",
}

PROMPT = """Busca en internet {que}.
Prioriza lo publicado en los últimos 60 días y lo que NO aparece en grandes portales como Urbania o Adondevivir.
Devuelve una lista JSON (máximo 20) de objetos con: nombre (del proyecto o inmueble), url (página del proyecto o aviso; si no hay, la del foro o noticia),
mencionado_en (url donde lo encontraste), departamento, provincia, distrito, tipo (departamento|casa|local|oficina|terreno|edificio),
estado_obra (terminado|en_planos|preventa|remate), constructora, precio (número o null), moneda (USD|PEN|null), area_m2, resumen (máx. 200 caracteres).
No inventes datos: usa null si no aparece."""

PROMPT_COMPLETAR = """Busca en internet la información de venta de este inmueble o proyecto en Perú y complétala.
Nombre: {nombre}
Lugar: {distrito}, {provincia}, {departamento}
Constructora: {constructora}
Pista: {resumen}
Encuentra la página oficial o un aviso con precio. Devuelve una lista JSON de unidades en venta con: url, titulo, tipo, operacion, estado,
precio, moneda, area_m2, dormitorios, banos, departamento, provincia, distrito, direccion, fecha_entrega, constructora, descripcion.
Si no encuentras precio, devuelve []."""


def clave(p):
    nombre = norm(p.get("nombre"))
    if nombre and len(nombre) > 3:
        return f"{nombre}|{norm(p.get('distrito'))}"
    return norm(p.get("url") or p.get("mencionado_en") or "")


def cobertura(db):
    conteo = {norm(d): 0 for d in config.DEPARTAMENTOS}
    for f in db.select_all("inmuebles", select="departamento", activo="eq.true", operacion="eq.venta"):
        d = norm(f.get("departamento"))
        if d in conteo:
            conteo[d] += 1
    return conteo


def elegir(db, p, cantidad=6):
    conteo = cobertura(db)
    nombres = {norm(d): d for d in config.DEPARTAMENTOS}
    peso = {d: 1 / (1 + n) ** 0.5 for d, n in conteo.items()}
    deps = random.choices(list(peso), weights=list(peso.values()), k=cantidad * 2)
    deps = list(dict.fromkeys(deps))[:cantidad]
    stats = p.get("explorador_stats") or {}
    elegidos = []
    for d in deps:
        if random.random() < 0.25:
            cat = random.choice(list(CATEGORIAS))
        else:
            cat = max(CATEGORIAS, key=lambda c: (stats.get(c, {}).get("utiles", 0) + 1) / (stats.get(c, {}).get("usos", 0) + 2) + random.random() * 0.05)
        elegidos.append((nombres[d], cat))
    return elegidos


def guardar_pistas(db, pistas, categoria, departamento):
    filas = {}
    for x in pistas if isinstance(pistas, list) else []:
        if not isinstance(x, dict) or not (x.get("nombre") or x.get("url")):
            continue
        x["departamento"] = x.get("departamento") or departamento
        k = clave(x)
        if not k:
            continue
        precio = base.numero(x.get("precio"))
        filas[k] = {
            "clave": k, "categoria": categoria,
            **{c: (str(x[c])[:500] if x.get(c) is not None else None) for c in ("nombre", "url", "mencionado_en", "departamento", "provincia", "distrito", "tipo", "estado_obra", "constructora", "moneda", "resumen")},
            "precio": precio, "area_m2": base.numero(x.get("area_m2")),
        }
    existentes = {f["clave"] for f in db.select_all("pistas", select="clave")}
    nuevas = [f for k, f in filas.items() if k not in existentes]
    db.upsert("pistas", nuevas, on_conflict="clave")
    return len(nuevas)


def explorar(db, p, cantidad=None):
    cantidad = cantidad or (25 if config.OPENAI_API_KEY else 6)
    if not llm.disponible():
        return {"omitido": "sin clave de IA"}
    stats = p.get("explorador_stats") or {}
    resumen = []
    for dep, cat in elegir(db, p, cantidad):
        lugar = f"el departamento de {dep}, Perú (incluye sus provincias y distritos)"
        try:
            datos = llm.pedir_json(PROMPT.format(que=CATEGORIAS[cat].format(lugar=lugar)), buscar=True)
            nuevas = guardar_pistas(db, datos, cat, dep)
        except Exception as e:
            resumen.append({"departamento": dep, "categoria": cat, "error": str(e)[:200]})
            continue
        s = stats.setdefault(cat, {"usos": 0, "utiles": 0})
        s["usos"] += 1
        s["utiles"] += min(nuevas, 5) / 5
        resumen.append({"departamento": dep, "categoria": cat, "pistas_nuevas": nuevas})
    db.upsert("parametros", {"clave": "explorador_stats", "valor": stats}, on_conflict="clave")
    return {"busquedas": resumen}


def _a_inmuebles(items, pista, tc):
    salida = []
    for x in items:
        x = dict(x)
        for c in ("departamento", "provincia", "distrito", "constructora", "tipo"):
            x[c] = x.get(c) or pista.get(c)
        x["estado"] = x.get("estado") or pista.get("estado_obra")
        x["operacion"] = x.get("operacion") or "venta"
        fila = runner.normalizar(x, "explorador", tc)
        if base.valido(fila):
            salida.append(fila)
    return salida


def verificar(db, p, limite=None):
    limite = limite or (150 if config.OPENAI_API_KEY else 25)
    tc = p["tipo_cambio"]
    pendientes = db.select("pistas", select="*", estado="in.(nueva,incompleta)", intentos="lt.3", order="creado.desc", limit=str(limite))
    ok = 0
    for pista in pendientes:
        filas = []
        for url in [pista.get("url"), pista.get("mencionado_en")]:
            if filas or not url or not url.startswith("http"):
                continue
            try:
                filas = _a_inmuebles(ia.extraer(base.descargar(url, intentos=2), url), pista, tc)
            except Exception:
                filas = []
        if not filas and pista.get("precio") and pista.get("url"):
            filas = _a_inmuebles([{"url": pista["url"], "titulo": pista.get("nombre"), "precio": pista["precio"], "moneda": pista.get("moneda"),
                                   "area_m2": pista.get("area_m2"), "descripcion": pista.get("resumen")}], pista, tc)
        if not filas and llm.disponible() and pista.get("nombre"):
            try:
                filas = _a_inmuebles(llm.pedir_json(PROMPT_COMPLETAR.format(**{k: pista.get(k) or "" for k in ("nombre", "distrito", "provincia", "departamento", "constructora", "resumen")}), buscar=True), pista, tc)
            except Exception:
                filas = []
        cambios = {"intentos": pista["intentos"] + 1, "actualizado": datetime.now(timezone.utc).isoformat()}
        if filas:
            guardadas = runner.guardar(db, filas)
            cambios.update(estado="verificada", inmueble_id=guardadas[0]["id"])
            ok += 1
        else:
            cambios["estado"] = "descartada" if pista["intentos"] + 1 >= 3 else "incompleta"
        db.update("pistas", cambios, id=f"eq.{pista['id']}")
    return {"revisadas": len(pendientes), "verificadas": ok}


def aprender_fuentes(db):
    conteo = {}
    for f in db.select_all("inmuebles", select="url", fuente="eq.explorador", activo="eq.true"):
        m = re.match(r"https?://([^/#]+)", f["url"] or "")
        if m:
            dominio = m.group(1).lower().removeprefix("www.")
            conteo[dominio] = conteo.get(dominio, 0) + 1
    actuales = {f["id"] for f in db.select("fuentes", select="id")}
    nuevas = []
    for dominio, n in conteo.items():
        fid = re.sub(r"[^a-z0-9]+", "-", dominio).strip("-")
        if n >= 3 and fid not in actuales:
            db.upsert("fuentes", {"id": fid, "nombre": dominio, "tipo": "ia", "urls": [f"https://{dominio}/"], "config": {"descubierta": True}}, on_conflict="id")
            nuevas.append(fid)
    return {"fuentes_nuevas": nuevas}


def ejecutar(db, p):
    return {"explorar": explorar(db, p), "verificar": verificar(db, p), "aprender": aprender_fuentes(db)}
