import statistics
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .. import config, llm
from ..collectors import navent, ia
from ..valoracion import norm

PROMPT_SELECTORES = """Esta es una página de listado de inmuebles de un portal peruano (plataforma Navent) que cambió su diseño.
Los selectores CSS actuales ya no encuentran avisos: {actuales}
Propón selectores CSS nuevos con las mismas claves: tarjeta, enlace (nombre del ATRIBUTO de la tarjeta con la ruta del aviso, o "href"),
precio, mantenimiento, ubicacion, direccion, caracteristicas, descripcion.

HTML (recortado):
{html}"""


def reparar_selectores(db, fuente, html, url):
    if fuente["tipo"] != "navent":
        return ia.extraer(html, url)
    if not llm.disponible():
        return []
    sopa = BeautifulSoup(html, "html.parser")
    for e in sopa(["script", "style", "svg", "noscript"]):
        e.decompose()
    muestra = str(sopa.body or sopa)[:60000]
    try:
        nuevos = llm.pedir_json(PROMPT_SELECTORES.format(actuales=navent.SELECTORES, html=muestra))
        items = navent.parsear(html, url, nuevos)
    except Exception:
        items = []
    validos = [i for i in items if i.get("precio")]
    if len(validos) >= 5:
        cfg = {**(fuente.get("config") or {}), "selectores": nuevos, "reparado": datetime.now(timezone.utc).isoformat()}
        db.update("fuentes", {"config": cfg}, id=f"eq.{fuente['id']}")
        fuente["config"] = cfg
        return items
    return ia.extraer(html, url)


def calibrar(db, p):
    zonas = db.select_all("zonas_stats", select="departamento,provincia,distrito,tipo,operacion,n,mediana_m2_usd", segmento="eq.*")
    por_clave = {}
    for z in zonas:
        if z["provincia"] == "*" and z["n"] >= 10:
            por_clave[(z["departamento"], z["tipo"], z["operacion"])] = z["mediana_m2_usd"]
    rendimientos = {}
    for (dep, tipo, op), m2 in por_clave.items():
        venta = por_clave.get((dep, tipo, "venta"))
        if op == "alquiler" and venta:
            rendimientos.setdefault(dep, []).append(m2 * 12 / venta)
    rd = {dep: round(min(0.12, max(0.03, statistics.median(v))), 4) for dep, v in rendimientos.items()}

    alquileres = db.select_all("inmuebles", select="primera_vez,ultima_vez,activo", operacion="eq.alquiler", activo="eq.false")
    dias = [(datetime.fromisoformat(a["ultima_vez"].replace("Z", "+00:00")) - datetime.fromisoformat(a["primera_vez"].replace("Z", "+00:00"))).days for a in alquileres]
    dias = [d for d in dias if 0 < d < 365]
    params = [{"clave": "rentabilidad_por_departamento", "valor": rd}]
    if len(dias) >= 50:
        params.append({"clave": "vacancia", "valor": round(min(0.25, max(0.04, statistics.median(dias) / 365)), 4)})
    per = p.get("per_distrito") or {}
    ratios = []
    filas = {(z["distrito"], z["operacion"]): z for z in db.select_all("zonas_stats", select="distrito,operacion,n,mediana_m2_usd", departamento="eq.lima", tipo="eq.departamento", segmento="eq.usado")}
    for dist, valor_per in per.items():
        v, a = filas.get((dist, "venta")), filas.get((dist, "alquiler"))
        if v and a and v["n"] >= 20 and a["n"] >= 10 and valor_per:
            ratios.append((1 / valor_per) / (a["mediana_m2_usd"] * 12 / v["mediana_m2_usd"]))
    if len(ratios) >= 4:
        params.append({"clave": "ajuste_renta", "valor": round(min(1.1, max(0.7, statistics.median(ratios))), 3)})
    db.upsert("parametros", params, on_conflict="clave")
    return {"rentabilidad_por_departamento": rd, "datos_vacancia": len(dias), "ajuste_renta": params[-1]["valor"] if len(ratios) >= 4 else None}


def crear_issue(titulo, cuerpo, etiquetas=("mejora",)):
    if not (config.GITHUB_TOKEN and config.GITHUB_REPO):
        print(titulo, cuerpo, sep="\n")
        return
    api = f"https://api.github.com/repos/{config.GITHUB_REPO}/issues"
    h = {"Authorization": f"Bearer {config.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    abiertos = httpx.get(api, headers=h, params={"state": "open", "labels": ",".join(etiquetas)}, timeout=30).json()
    if any(i.get("title") == titulo for i in abiertos if isinstance(i, dict)):
        return
    httpx.post(api, headers=h, json={"title": titulo, "body": cuerpo, "labels": list(etiquetas)}, timeout=30).raise_for_status()


def revisar_salud(db):
    problemas = [f for f in db.select("fuentes", select="id,nombre,ultimo_error,fallos_seguidos,activo", activo="eq.true") if f["fallos_seguidos"] >= 3]
    for f in problemas:
        crear_issue(
            f"Recolector caído: {f['nombre']}",
            f"La fuente `{f['id']}` falló {f['fallos_seguidos']} veces seguidas.\n\nÚltimo error:\n```\n{f['ultimo_error']}\n```\n\n"
            "@claude revisa el recolector de esta fuente, corrige el código y abre un PR con pruebas.",
        )
    ejecuciones = db.select("ejecuciones", select="agente,ok,detalle,inicio", order="inicio.desc", limit="60")
    fallidas = [e for e in ejecuciones if not e["ok"]]
    if len(fallidas) >= 5:
        crear_issue("Varios agentes están fallando", "Últimos errores:\n```\n" + "\n".join(str(e["detalle"])[:300] for e in fallidas[:10]) + "\n```\n\n@claude encuentra la causa y abre un PR con la corrección.")
    return {"fuentes_con_problemas": [f["id"] for f in problemas], "ejecuciones_fallidas": len(fallidas)}


def ejecutar(db, p):
    return {"calibracion": calibrar(db, p), "salud": revisar_salud(db)}
