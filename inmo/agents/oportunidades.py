import io
import json
import random
import re
import zipfile
from datetime import date, timedelta

import httpx

from .. import config, llm, ubigeo
from ..collectors import base
from ..valoracion import norm
from .ubicador import capital, capitales


RUBROS = {
    "maquinaria": r"maquinari|excavadora|retroexcavadora|cargador frontal|motoniveladora|rodillo|tractor|grua|gr[uú]a|montacarga|compactadora|minicargador|perforadora",
    "camiones y transporte": r"volquete|cami[oó]n|cisterna|transporte de carga|flete|traslado de|furg[oó]n|tracto|semitrailer|camioneta|bus\b|movilidad",
    "madera y aserradero": r"madera|aserr|tabl[oó]n|triplay|carpinter",
    "talleres y mantenimiento": r"taller|mantenimiento (preventivo|correctivo)? ?de (veh[ií]culo|maquinari|equipo|motor)|reparaci[oó]n de|soldadura|torner|mec[aá]nic",
    "construcción y obras": r"construcci[oó]n|obra|edificaci|pavimenta|asfalt|agregado|cemento|fierro|ladrillo|movimiento de tierra",
    "agua y saneamiento": r"agua potable|desag[uü]e|alcantarill|saneamiento|bombeo|pozo",
    "combustible y energía": r"combustible|petr[oó]leo|diesel|gasolina|grupo electr[oó]geno|energ[ií]a|el[eé]ctric",
    "alimentos": r"aliment|raci[oó]n|v[ií]veres|comedor|desayuno|catering|refrigerio",
    "limpieza y seguridad": r"limpieza|vigilancia|seguridad|fumigaci|residuos s[oó]lidos|recojo de basura",
    "tecnología": r"software|computador|laptop|servidor|internet|telecomunic|c[aá]mara|sistema inform",
    "salud": r"medicament|m[eé]dic|hospital|insumos m[eé]dicos|laboratorio|odont",
    "consultoría y estudios": r"consultor|expediente t[eé]cnico|estudio de|supervisi[oó]n|asesor",
    "vestuario y útiles": r"uniforme|vestuario|calzado|[uú]tiles|papeler",
}

PROMPT = """Busca en internet {que} en {lugar}, publicados en los últimos 60 días y todavía vigentes.
Devuelve una lista JSON (máximo 20) de objetos con: titulo (qué piden), descripcion (máx. 300 caracteres), entidad (empresa o institución que lo pide),
url (página del anuncio), departamento, provincia, distrito, monto (número o null), moneda (USD|PEN|null), fecha_limite (AAAA-MM-DD o null),
telefono, correo. Solo pedidos reales de empresas o instituciones que necesiten contratar un servicio, alquilar equipo o comprar algo. No inventes datos."""
BUSQUEDAS = [
    "empresas mineras, constructoras y agroindustrias que buscan proveedores o alquiler de maquinaria pesada, volquetes y camiones",
    "convocatorias de empresas privadas que requieren servicios de taller mecánico, mantenimiento de flota, soldadura o metalmecánica",
    "empresas que solicitan proveedores de madera, aserradero, carpintería o encofrado",
    "convocatorias de proveedores locales de empresas mineras y petroleras (servicios de transporte, alimentación, limpieza, mantenimiento)",
    "anuncios de 'se requiere' o 'se necesita' alquiler de equipos, camiones, cisternas o maquinaria",
]


def rubro(texto):
    t = norm(texto)
    for nombre, patron in RUBROS.items():
        if re.search(patron, t, re.I):
            return nombre
    return "otros"


def _lugar(textos):
    lugar = ubigeo.resolver(*textos)
    punto = capital(lugar) if lugar.get("distrito") else None
    if not punto and lugar.get("departamento"):
        dep = norm(lugar["departamento"])
        punto = next((tuple(v) for k, v in capitales().items() if k.startswith(f"{dep}|")), None)
    return lugar, punto


def desde_release(rel, tc):
    tender = rel.get("tender") or {}
    if not tender.get("title") and not tender.get("description"):
        return None
    comprador = next((p for p in rel.get("parties", []) if "buyer" in (p.get("roles") or [])), {}) or rel.get("buyer") or {}
    direccion = comprador.get("address") or {}
    contacto = comprador.get("contactPoint") or {}
    valor = tender.get("value") or {}
    monto = valor.get("amount")
    codigo = tender.get("title") or ""
    descripcion = (tender.get("description") or "").strip("¿? ")[:1000]
    titulo = (descripcion or codigo)[:300]
    clases = " ".join(str((i.get("classification") or {}).get("description") or "") for i in tender.get("items") or [])
    lugar, punto = _lugar([direccion.get("locality"), direccion.get("region"), direccion.get("streetAddress"), comprador.get("name")])
    if not lugar.get("distrito"):
        lugar2, punto2 = _lugar(re.findall(r"(?:DISTRITO|PROVINCIA|DEPARTAMENTO|REGI[OÓ]N) (?:DE )?([A-ZÁÉÍÓÚÑ ]+?)(?:[,.;]| PROVINCIA| DEPARTAMENTO|$)", descripcion.upper())[::-1] + re.findall(r"(?:DISTRITAL|PROVINCIAL|REGIONAL|GOBIERNO REGIONAL) DE ([A-ZÁÉÍÓÚÑ ]+)", str(comprador.get("name") or "").upper()))
        if lugar2.get("distrito") or not lugar.get("departamento"):
            lugar, punto = lugar2, punto2
    docs = [d.get("url") for d in tender.get("documents") or [] if str(d.get("url") or "").startswith("http")]
    return {
        "clave": rel.get("ocid") or rel.get("id"), "fuente": "seace",
        "titulo": titulo, "descripcion": descripcion, "rubro": rubro(f"{titulo} {clases}"),
        "categoria": {"goods": "bienes", "services": "servicios", "works": "obras"}.get(tender.get("mainProcurementCategory"), tender.get("mainProcurementCategory")),
        "entidad": comprador.get("name"), "telefono": contacto.get("telephone"), "correo": contacto.get("email"),
        "web": contacto.get("url") or comprador.get("url"),
        "departamento": lugar.get("departamento"), "provincia": lugar.get("provincia"), "distrito": lugar.get("distrito"),
        "lat": punto[0] if punto else None, "lng": punto[1] if punto else None,
        "monto_usd": round(monto / tc, 2) if monto and valor.get("currency") == "PEN" else monto,
        "fecha_publicacion": (tender.get("datePublished") or rel.get("date") or "")[:10] or None,
        "fecha_limite": None,
        "url": docs[0] if docs else f"https://contratacionesabiertas.oece.gob.pe/proceso/{rel.get('ocid')}",
        "metodo": " · ".join(x for x in (tender.get("procurementMethodDetails"), codigo) if x),
    }


class Navegador:
    def get(self, url, params=None):
        if base.cffi:
            return base.cffi.get(url, params=params, impersonate="chrome", headers={"Accept": "application/json", "Accept-Language": "es-PE,es;q=0.9"}, timeout=90)
        return httpx.get(url, params=params, headers=base.HEADERS, timeout=90)


ARCHIVO = "https://contratacionesabiertas.oece.gob.pe/api/v1/file/seace_v3/json/{y}/{m:02d}/"


def paquetes(contenido):
    if contenido[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            for nombre in z.namelist():
                if nombre.endswith(".json"):
                    yield json.loads(z.read(nombre))
    else:
        yield json.loads(contenido)


def releases(paquete):
    for x in paquete.get("records") or paquete.get("releases") or []:
        if "compiledRelease" in x:
            yield x["compiledRelease"]
        elif "releases" in x and x["releases"] and isinstance(x["releases"][-1], dict) and "tender" in x["releases"][-1]:
            yield x["releases"][-1]
        else:
            yield x


def abierta(rel, hoy):
    t = rel.get("tender") or {}
    if t.get("procurementMethod") == "direct" or rel.get("awards"):
        return False
    estados = {str(i.get("statusDetails") or "").upper() for i in t.get("items") or []}
    if "CONVOCADO" not in estados:
        return False
    publicada = (t.get("datePublished") or rel.get("date") or "")[:10]
    return publicada >= (date.fromisoformat(hoy) - timedelta(days=30)).isoformat()


def seace(db, p, http=None):
    http = http or Navegador()
    hoy = date.today()
    periodos = [(hoy.year, hoy.month)]
    if hoy.day <= 15:
        anterior = hoy.replace(day=1) - timedelta(days=1)
        periodos.append((anterior.year, anterior.month))
    vistos = {f["clave"] for f in db.select_all("oportunidades", select="clave", fuente="eq.seace")}
    resumen = {"leidas": 0, "abiertas": 0, "nuevas": 0}
    for y, m in periodos:
        r = http.get(ARCHIVO.format(y=y, m=m))
        r.raise_for_status()
        filas = {}
        for paquete in paquetes(r.content):
            for rel in releases(paquete):
                resumen["leidas"] += 1
                if not abierta(rel, hoy.isoformat()):
                    continue
                fila = desde_release(rel, p["tipo_cambio"])
                if fila:
                    filas[fila["clave"]] = fila
        lista = list(filas.values())
        for k in range(0, len(lista), 500):
            db.upsert("oportunidades", lista[k:k + 500], on_conflict="clave")
        resumen["abiertas"] += len(lista)
        resumen["nuevas"] += sum(1 for f in lista if f["clave"] not in vistos)
    return resumen


def web(db, p, departamentos=None):
    if not llm.disponible():
        return {"omitido": "sin IA"}
    hechas = 0
    if not departamentos:
        conteo = {d: 0 for d in config.DEPARTAMENTOS}
        for f in db.select_all("oportunidades", select="departamento", fuente="eq.web"):
            if f.get("departamento") in conteo:
                conteo[f["departamento"]] += 1
        departamentos = sorted(conteo, key=lambda d: (conteo[d], random.random()))[:8]
    for dep in departamentos:
        for que in BUSQUEDAS:
            try:
                datos = llm.pedir_json(PROMPT.format(que=que, lugar=f"{dep}, Perú"), buscar=True)
            except Exception:
                continue
            filas = []
            for x in datos if isinstance(datos, list) else []:
                if not isinstance(x, dict) or not str(x.get("url") or "").startswith("http") or not x.get("titulo"):
                    continue
                lugar, punto = _lugar([x.get("distrito"), x.get("provincia"), x.get("departamento") or dep])
                monto = base.numero(x.get("monto"))
                filas.append({
                    "clave": norm(x["url"])[:300], "fuente": "web", "titulo": str(x["titulo"])[:300], "descripcion": str(x.get("descripcion") or "")[:1000],
                    "rubro": rubro(f"{x['titulo']} {x.get('descripcion') or ''}"), "entidad": x.get("entidad"),
                    "telefono": base.telefonos(str(x.get("telefono") or "")) or x.get("telefono"), "correo": x.get("correo"),
                    "departamento": lugar.get("departamento") or dep, "provincia": lugar.get("provincia"), "distrito": lugar.get("distrito"),
                    "lat": punto[0] if punto else None, "lng": punto[1] if punto else None,
                    "monto_usd": round(monto / p["tipo_cambio"], 2) if monto and (x.get("moneda") or "PEN") == "PEN" else monto,
                    "fecha_limite": base.fecha(x.get("fecha_limite")), "url": x["url"],
                })
            if filas:
                db.upsert("oportunidades", list({f["clave"]: f for f in filas}.values()), on_conflict="clave")
                hechas += len(filas)
    return {"web": hechas}


def ejecutar(db, p, con_web=True):
    try:
        r = {"seace": seace(db, p)}
    except Exception as e:
        r = {"seace": f"no disponible: {str(e)[:120]}"}
    if con_web:
        r["web"] = web(db, p)
    return r
