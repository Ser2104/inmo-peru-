import random
import re
import time
from datetime import datetime, timezone

from .. import config, llm
from ..busqueda import buscar_web, texto_pagina
from .rastreador import dominio

CIUDADES = {
    "Lima": ["Lima", "Miraflores", "San Isidro", "Surco", "San Borja", "La Molina", "Jesús María", "Lince", "Magdalena", "Pueblo Libre", "San Miguel", "Barranco",
             "Chorrillos", "Los Olivos", "Comas", "San Juan de Lurigancho", "Ate", "Surquillo", "Breña", "Huacho", "Cañete", "Lurín", "Punta Hermosa", "Chosica"],
    "Callao": ["Callao", "Bellavista", "La Perla"], "Arequipa": ["Arequipa", "Cayma", "Yanahuara", "Cerro Colorado", "José Luis Bustamante y Rivero", "Sachaca", "Camaná", "Mollendo"],
    "Cusco": ["Cusco", "Wanchaq", "San Sebastián", "San Jerónimo", "Santiago Cusco", "Urubamba", "Valle Sagrado"],
    "La Libertad": ["Trujillo", "Víctor Larco", "Huanchaco"], "Lambayeque": ["Chiclayo", "Lambayeque", "Pimentel"], "Piura": ["Piura", "Sullana", "Máncora", "Talara"],
    "Ica": ["Ica", "Chincha", "Pisco", "Paracas"], "Junín": ["Huancayo", "El Tambo", "Tarma"], "Áncash": ["Chimbote", "Huaraz", "Nuevo Chimbote"],
    "Cajamarca": ["Cajamarca", "Jaén"], "Puno": ["Puno", "Juliaca"], "Tacna": ["Tacna"], "Moquegua": ["Moquegua", "Ilo"], "San Martín": ["Tarapoto", "Moyobamba"],
    "Loreto": ["Iquitos"], "Ucayali": ["Pucallpa"], "Ayacucho": ["Ayacucho", "Huamanga"], "Huánuco": ["Huánuco"], "Tumbes": ["Tumbes", "Zorritos"],
    "Apurímac": ["Abancay", "Andahuaylas"], "Pasco": ["Cerro de Pasco"], "Madre de Dios": ["Puerto Maldonado"], "Amazonas": ["Chachapoyas", "Bagua"],
    "Huancavelica": ["Huancavelica"],
}
PLANTILLAS = [
    "departamentos en venta {c} constructora", "proyecto inmobiliario {c}", "preventa departamentos {c}", "inmobiliaria {c} proyectos en venta",
    "edificio multifamiliar {c} venta departamentos", "condominio {c} casas en venta", "lotes en venta {c} habilitación urbana",
    "departamentos {c} entrega inmediata", "flats en venta {c}", "nuevo proyecto de departamentos en {c} precios",
]
EXCLUIDOS = re.compile(r"(urbania|adondevivir|properati|nexoinmobiliario|infocasas|trovit|mitula|nuroa|doomos|olx|mercadolibre|facebook|instagram|tiktok|youtube|"
                       r"linkedin|twitter|x\.com|wikipedia|google|bing|yahoo|gob\.pe|edu\.pe|elcomercio|larepublica|rpp|gestion|peru21|infobae|andina|"
                       r"elperuano|correo|trome|exitosa|semanaeconomica|pinterest|tripadvisor|booking|airbnb|scribd|issuu|slideshare|blogspot|wordpress\.com|"
                       r"medium|reddit|skyscrapercity|computrabajo|bumeran|indeed|amazon|aliexpress)", re.I)
SENALES = re.compile(r"(departamento|dormitorio|m²|m2|preventa|proyecto|flat|duplex|lote|condominio|entrega|separa|cotiza|precio|desde s/|desde us\$|financiamiento)", re.I)

PROMPT = """Este es el texto de la página principal de {dominio}. ¿Es la web de una constructora, inmobiliaria o proyecto inmobiliario
que vende departamentos, casas, lotes o locales en Perú? Responde JSON: {{"inmobiliaria": true/false, "ciudad": "ciudad principal o null",
"motivo": "máx. 80 caracteres"}}. Portales de anuncios de terceros, noticias, bancos o blogs NO cuentan.

TEXTO:
{texto}"""


def consultas(db, cantidad, parte=0, partes=1):
    from .rastreador import mi_parte
    hechas = {f["consulta"] for f in db.select_all("busquedas_hechas", select="consulta")}
    todas = [(dep, c, p.format(c=c)) for dep, cs in CIUDADES.items() for c in cs for p in PLANTILLAS]
    todas = [x for x in todas if mi_parte(x[2], parte, partes)]
    pendientes = [x for x in todas if x[2] not in hechas]
    random.shuffle(pendientes)
    return pendientes[:cantidad] or random.sample(todas, min(cantidad, len(todas)))


def descubrir(db, cantidad=None, pausa=2.0, parte=0, partes=1):
    cantidad = cantidad or (120 if config.OPENAI_API_KEY else 40)
    conocidos = {f["dominio"] for f in db.select_all("sitios", select="dominio")}
    nuevos = 0
    for dep, ciudad, consulta in consultas(db, cantidad, parte, partes):
        resultados = buscar_web(consulta, n=10)
        filas = {}
        for r in resultados:
            d = dominio(r["url"])
            if not d or d in conocidos or EXCLUIDOS.search(d):
                continue
            if not SENALES.search(f"{r.get('titulo') or ''} {r.get('resumen') or ''}"):
                continue
            filas[d] = {"dominio": d, "url": f"https://{d}", "ciudad": ciudad, "departamento": dep, "origen": "buscador"}
        if filas:
            db.upsert("sitios", list(filas.values()), on_conflict="dominio")
            conocidos |= set(filas)
            nuevos += len(filas)
        db.upsert("busquedas_hechas", {"consulta": consulta, "resultados": len(resultados)}, on_conflict="consulta")
        time.sleep(pausa)
    return {"consultas": cantidad, "sitios_nuevos": nuevos}


def verificar(db, limite=150, parte=0, partes=1):
    from .rastreador import mi_parte
    hechos = {"inmobiliaria": 0, "descartado": 0}
    for s in [x for x in db.select("sitios", select="*", estado="eq.nuevo", limit=str(limite * partes)) if mi_parte(x["dominio"], parte, partes)][:limite]:
        texto = texto_pagina(s["url"], 5000)
        ahora = datetime.now(timezone.utc).isoformat()
        if not texto:
            db.update("sitios", {"estado": "descartado", "motivo": "no se pudo abrir", "revisado": ahora}, dominio=f"eq.{s['dominio']}")
            hechos["descartado"] += 1
            continue
        senales = len(SENALES.findall(texto))
        if s["origen"] == "usuario":
            ok, motivo, ciudad = True, "agregado por ti", s.get("ciudad")
        elif senales >= 15:
            ok, motivo, ciudad = True, "muchas señales de proyecto inmobiliario", s.get("ciudad")
        elif senales <= 2:
            ok, motivo, ciudad = False, "sin señales de proyecto inmobiliario", s.get("ciudad")
        elif llm.disponible():
            try:
                r = llm.pedir_json(PROMPT.format(dominio=s["dominio"], texto=texto[:4000]))
            except RuntimeError:
                continue
            ok, motivo, ciudad = bool(r.get("inmobiliaria")), str(r.get("motivo") or "")[:120], r.get("ciudad") or s.get("ciudad")
        else:
            ok, motivo, ciudad = len(SENALES.findall(texto)) >= 6, "por palabras clave", s.get("ciudad")
        estado = "inmobiliaria" if ok else "descartado"
        db.update("sitios", {"estado": estado, "motivo": motivo, "ciudad": ciudad, "revisado": ahora}, dominio=f"eq.{s['dominio']}")
        hechos[estado] += 1
    return hechos


def ejecutar(db):
    return {"descubrir": descubrir(db), "verificar": verificar(db)}
