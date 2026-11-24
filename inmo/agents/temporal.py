import random
from datetime import datetime, timedelta, timezone

import httpx

from .. import config, llm, temporal as tmp
from ..valoracion import norm

ZONAS = [
    ("Lima", "Lima", "Miraflores"), ("Lima", "Lima", "Barranco"), ("Lima", "Lima", "San Isidro"), ("Lima", "Lima", "Santiago de Surco"),
    ("Lima", "Lima", "San Borja"), ("Lima", "Lima", "Lince"), ("Lima", "Lima", "Jesús María"), ("Lima", "Lima", "Magdalena del Mar"),
    ("Lima", "Lima", "San Miguel"), ("Lima", "Lima", "Cercado de Lima"), ("Lima", "Lima", "Chorrillos"), ("Lima", "Lima", "Surquillo"),
    ("Lima", "Lima", "Punta Hermosa"), ("Lima", "Lima", "San Bartolo"), ("Lima", "Cañete", "Asia"), ("Callao", "Callao", "La Punta"),
    ("Cusco", "Cusco", "Cusco"), ("Cusco", "Urubamba", "Urubamba"), ("Cusco", "Urubamba", "Machupicchu"), ("Arequipa", "Arequipa", "Arequipa"),
    ("Arequipa", "Arequipa", "Yanahuara"), ("Arequipa", "Arequipa", "Cayma"), ("Piura", "Talara", "Máncora"), ("Piura", "Piura", "Piura"),
    ("Ica", "Pisco", "Paracas"), ("Ica", "Ica", "Ica"), ("La Libertad", "Trujillo", "Trujillo"), ("La Libertad", "Trujillo", "Huanchaco"),
    ("Áncash", "Huaraz", "Huaraz"), ("Puno", "Puno", "Puno"), ("Loreto", "Maynas", "Iquitos"), ("San Martín", "San Martín", "Tarapoto"),
    ("Lambayeque", "Chiclayo", "Chiclayo"), ("Tumbes", "Contralmirante Villar", "Zorritos"), ("Tacna", "Tacna", "Tacna"),
    ("Junín", "Huancayo", "Huancayo"), ("Cajamarca", "Cajamarca", "Cajamarca"), ("Madre de Dios", "Tambopata", "Puerto Maldonado"),
]

PROMPT = """Busca datos recientes (2025-2026) del mercado de alquiler por días (Airbnb, Booking, Vrbo) en {distrito}, {provincia}, {departamento}, Perú.
Usa páginas públicas de AirDNA, Airbtics, AirROI, bnbcalc u otras fuentes de datos de alquiler temporal, y noticias.
Devuelve una lista JSON: un objeto por fuente con: fuente (nombre), url, periodo, adr (tarifa promedio por noche, número), moneda_adr (USD|PEN),
ocupacion (0 a 1), ingreso_anual (número), moneda_ingreso (USD|PEN), anuncios (número de anuncios activos), dormitorios (si el dato es para un tamaño específico, si no null).
Además agrega UN objeto final con: tipo "regulacion", estado (permitido|restringido|prohibido|desconocido) y nota, sobre si la municipalidad de {distrito}
prohíbe o restringe el alquiler vacacional o rotativo. No inventes: usa null si no hay dato."""


def _usd(valor, moneda, tc):
    if valor in (None, ""):
        return None
    v = float(valor)
    return v / tc if str(moneda).upper() in ("PEN", "S/", "SOLES") else v


def guardar(db, zona, datos, tc):
    dep, prov, dist = zona
    filas, regla = [], None
    for d in datos if isinstance(datos, list) else []:
        if not isinstance(d, dict):
            continue
        if d.get("tipo") == "regulacion":
            if d.get("estado") in ("permitido", "restringido", "prohibido"):
                regla = {"departamento": norm(dep), "distrito": norm(dist), "estado": d["estado"], "nota": (d.get("nota") or "")[:500],
                         "fuente": "buscador_ia", "actualizado": datetime.now(timezone.utc).isoformat()}
            continue
        try:
            adr = _usd(d.get("adr"), d.get("moneda_adr"), tc)
            occ = float(d["ocupacion"]) if d.get("ocupacion") not in (None, "") else None
            ingreso = _usd(d.get("ingreso_anual"), d.get("moneda_ingreso"), tc)
        except (TypeError, ValueError):
            continue
        if occ and occ > 1:
            occ /= 100
        if not adr and ingreso and occ:
            adr = ingreso / (365 * occ)
        if not occ and ingreso and adr:
            occ = ingreso / (365 * adr)
        if not adr or not occ or not (8 <= adr <= 1500) or not (0.05 <= occ <= 0.95):
            continue
        fuente = (d.get("fuente") or "web")[:60]
        filas.append({
            "clave": f"{norm(dep)}|{norm(prov)}|{norm(dist)}|{norm(fuente)}|{d.get('dormitorios') or '*'}",
            "departamento": dep, "provincia": prov, "distrito": dist, "adr_usd": round(adr, 2), "ocupacion": round(occ, 3),
            "ingreso_anual_usd": round(ingreso, 2) if ingreso else round(adr * 365 * occ, 2),
            "anuncios": int(d["anuncios"]) if str(d.get("anuncios") or "").isdigit() else None,
            "dormitorios": d.get("dormitorios") if isinstance(d.get("dormitorios"), int) else None,
            "fuente": fuente, "url": (d.get("url") or "")[:500], "periodo": str(d.get("periodo") or "")[:40],
            "fecha": datetime.now(timezone.utc).isoformat(),
        })
    db.upsert("mercado_temporal", filas, on_conflict="clave")
    if regla:
        previa = db.select("regulacion_temporal", select="fuente", departamento=f"eq.{regla['departamento']}", distrito=f"eq.{regla['distrito']}")
        if not previa or previa[0].get("fuente") == "buscador_ia":
            db.upsert("regulacion_temporal", regla, on_conflict="departamento,distrito")
    return len(filas), regla["estado"] if regla else None


def elegir_zonas(db, cantidad):
    existentes = {}
    for f in db.select_all("mercado_temporal", select="departamento,distrito,fecha"):
        k = (norm(f["departamento"]), norm(f["distrito"]))
        existentes[k] = max(existentes.get(k, ""), f["fecha"])
    viejo = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    sin_datos = [z for z in ZONAS if (norm(z[0]), norm(z[2])) not in existentes]
    vencidas = [z for z in ZONAS if existentes.get((norm(z[0]), norm(z[2])), viejo) < viejo]
    resto = [z for z in ZONAS if z not in sin_datos and z not in vencidas]
    random.shuffle(resto)
    return (sin_datos + vencidas + resto)[:cantidad]


def airroi_inmuebles(db, limite):
    if not config.AIRROI_API_KEY:
        return 0
    hechos = {f["clave"] for f in db.select_all("mercado_temporal", select="clave", fuente="eq.airroi_inmueble")}
    candidatos = db.select("analisis", select="inmueble_id,puntaje_total", puntaje_total="not.is.null", order="puntaje_total.desc", limit=str(limite * 3))
    ids = [c["inmueble_id"] for c in candidatos if f"airroi:{c['inmueble_id']}" not in hechos][:limite]
    if not ids:
        return 0
    inmuebles = db.select("inmuebles", select="id,lat,lng,direccion,distrito,departamento,provincia,dormitorios,banos,area_m2", id=f"in.({','.join(ids)})")
    n = 0
    for inm in inmuebles:
        try:
            est = tmp.airroi_estimar(inm)
        except httpx.HTTPError:
            continue
        if est:
            db.upsert("mercado_temporal", {"clave": f"airroi:{inm['id']}", "departamento": inm.get("departamento"), "provincia": inm.get("provincia"),
                                           "distrito": inm.get("distrito"), "adr_usd": est["adr_usd"], "ocupacion": est["ocupacion"],
                                           "ingreso_anual_usd": round(est["adr_usd"] * 365 * est["ocupacion"], 2), "fuente": "airroi_inmueble"}, on_conflict="clave")
            n += 1
    return n


def ejecutar(db, p, cantidad=None):
    cantidad = cantidad or (len(ZONAS) if config.OPENAI_API_KEY else 6)
    resumen = {"zonas": [], "airroi": 0}
    if llm.disponible():
        for zona in elegir_zonas(db, cantidad):
            try:
                datos = llm.pedir_json(PROMPT.format(departamento=zona[0], provincia=zona[1], distrito=zona[2]), buscar=True)
                n, regla = guardar(db, zona, datos, p["tipo_cambio"])
                resumen["zonas"].append({"zona": zona[2], "datos": n, "regulacion": regla})
            except Exception as e:
                resumen["zonas"].append({"zona": zona[2], "error": str(e)[:200]})
    resumen["airroi"] = airroi_inmuebles(db, config.AIRROI_MAX_LLAMADAS)
    return resumen


def cargar(db):
    filas = db.select_all("mercado_temporal", select="*")
    airroi = {f["clave"].split(":", 1)[1]: {"adr_usd": f["adr_usd"], "ocupacion": f["ocupacion"]} for f in filas if f.get("fuente") == "airroi_inmueble"}
    reglas = {(norm(r["departamento"]), norm(r["distrito"])): r for r in db.select_all("regulacion_temporal", select="*")}
    return {"indice": tmp.indice_mercado(filas), "reglas": reglas, "airroi": airroi}
