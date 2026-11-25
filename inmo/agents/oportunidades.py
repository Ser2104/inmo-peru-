import re
from datetime import datetime, timedelta, timezone

import httpx

from .. import config, llm, ubigeo
from ..collectors import base
from ..valoracion import norm
from .ubicador import capital, capitales

API = "https://contratacionesabiertas.oece.gob.pe/api/v1/releasesAfter"

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
    titulo = (tender.get("title") or tender.get("description") or "")[:300]
    descripcion = (tender.get("description") or "")[:1000]
    lugar, punto = _lugar([direccion.get("locality"), direccion.get("region"), direccion.get("streetAddress"), comprador.get("name")])
    docs = [d.get("url") for d in tender.get("documents") or [] if str(d.get("url") or "").startswith("http")]
    return {
        "clave": rel.get("ocid") or rel.get("id"), "fuente": "seace",
        "titulo": titulo, "descripcion": descripcion, "rubro": rubro(f"{titulo} {descripcion}"),
        "categoria": {"goods": "bienes", "services": "servicios", "works": "obras"}.get(tender.get("mainProcurementCategory"), tender.get("mainProcurementCategory")),
        "entidad": comprador.get("name"), "telefono": contacto.get("telephone"), "correo": contacto.get("email"),
        "web": contacto.get("url") or comprador.get("url"),
        "departamento": lugar.get("departamento"), "provincia": lugar.get("provincia"), "distrito": lugar.get("distrito"),
        "lat": punto[0] if punto else None, "lng": punto[1] if punto else None,
        "monto_usd": round(monto / tc, 2) if monto and valor.get("currency") == "PEN" else monto,
        "fecha_publicacion": (rel.get("date") or "")[:10] or None,
        "fecha_limite": ((tender.get("tenderPeriod") or {}).get("endDate") or "")[:10] or None,
        "url": docs[0] if docs else f"https://contratacionesabiertas.oece.gob.pe/proceso/{rel.get('ocid')}",
        "metodo": tender.get("procurementMethodDetails"),
    }


class Navegador:
    def get(self, url, params=None):
        if base.cffi:
            return base.cffi.get(url, params=params, impersonate="chrome", headers={"Accept": "application/json", "Accept-Language": "es-PE,es;q=0.9"}, timeout=90)
        return httpx.get(url, params=params, headers=base.HEADERS, timeout=90)


def seace(db, p, dias=21, maximo_paginas=400, http=None):
    http = http or Navegador()
    limite = (datetime.now(timezone.utc) - timedelta(days=dias)).date().isoformat()
    vistos = {f["clave"] for f in db.select_all("oportunidades", select="clave", fuente="eq.seace")}
    url, params, nuevas, paginas, repetidas = API, {"format": "json", "order": "desc"}, 0, 0, 0
    while url and paginas < maximo_paginas:
        r = http.get(url, params=params)
        r.raise_for_status()
        datos = r.json()
        paginas += 1
        filas, viejo = [], False
        for rel in datos.get("releases", []):
            if (rel.get("date") or "")[:10] < limite:
                viejo = True
                continue
            if "tender" not in (rel.get("tag") or ["tender"]) and not rel.get("tender"):
                continue
            fila = desde_release(rel, p["tipo_cambio"])
            if fila:
                repetidas += fila["clave"] in vistos
                filas.append(fila)
        if filas:
            unicas = list({f["clave"]: f for f in filas}.values())
            db.upsert("oportunidades", unicas, on_conflict="clave")
            nuevas += sum(1 for f in unicas if f["clave"] not in vistos)
            vistos.update(f["clave"] for f in unicas)
        if viejo:
            break
        url, params = (datos.get("links") or {}).get("next"), None
    return {"paginas": paginas, "nuevas": nuevas, "repetidas": repetidas}


def web(db, p, departamentos=None):
    if not llm.disponible():
        return {"omitido": "sin IA"}
    hechas = 0
    for dep in departamentos or config.DEPARTAMENTOS:
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
    r = {"seace": seace(db, p)}
    if con_web:
        r["web"] = web(db, p)
    return r
