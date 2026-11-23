import httpx

API = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/{codigos}/json/{inicio}/{fin}"

PER_DISTRITO = {
    "PD41940PQ": "barranco", "PD41941PQ": "jesus maria", "PD41942PQ": "la molina", "PD41943PQ": "lince",
    "PD41944PQ": "magdalena del mar", "PD41945PQ": "miraflores", "PD41946PQ": "pueblo libre",
    "PD41947PQ": "san borja", "PD41948PQ": "san isidro", "PD41949PQ": "san miguel",
    "PD41950PQ": "santiago de surco", "PD41951PQ": "surquillo", "PD41952PQ": "promedio",
}
TRIMESTRALES = list(PER_DISTRITO) + ["PD37944PQ", "PD37941PQ", "PD38028PQ", "PD37940PQ"]
TIPO_CAMBIO = "PD04638PD"


def _serie(codigo, inicio, fin):
    r = httpx.get(API.format(codigos=codigo, inicio=inicio, fin=fin), timeout=60, follow_redirects=True)
    r.raise_for_status()
    datos = r.json()
    nombre = datos["config"]["series"][0]["name"]
    filas = []
    for periodo in datos.get("periods", []):
        try:
            filas.append({"codigo": codigo, "nombre": nombre, "periodo": periodo["name"], "valor": float(periodo["values"][0])})
        except (TypeError, ValueError, IndexError):
            pass
    return filas


def actualizar(db, anio):
    filas = []
    for codigo in TRIMESTRALES:
        filas += _serie(codigo, f"{anio - 6}-1", f"{anio}-4")
    tc = _serie(TIPO_CAMBIO, f"{anio}-01-01", f"{anio}-12-31")
    filas += tc
    db.upsert("series_macro", filas, on_conflict="codigo,periodo")

    params = []
    if tc:
        params.append({"clave": "tipo_cambio", "valor": tc[-1]["valor"]})
    indice = [f["valor"] for f in filas if f["codigo"] == "PD37940PQ"]
    if len(indice) >= 9:
        crecimiento = (indice[-1] / indice[-9]) ** 0.5 - 1
        params.append({"clave": "plusvalia_bcrp", "valor": round(0.5 * max(-0.03, min(crecimiento, 0.06)) + 0.5 * 0.03, 4)})
    per = {}
    for f in filas:
        if f["codigo"] in PER_DISTRITO:
            per[PER_DISTRITO[f["codigo"]]] = f["valor"]
    if per:
        params.append({"clave": "per_distrito", "valor": per})
    db.upsert("parametros", params, on_conflict="clave")
    return {"series": len(filas), "parametros": params}
