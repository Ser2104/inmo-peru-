import json
from functools import lru_cache
from pathlib import Path

ALIAS = {
    "surco": "santiago de surco", "magdalena": "magdalena del mar", "cercado de lima": "lima", "lima cercado": "lima",
    "cercado": "lima", "sjl": "san juan de lurigancho", "smp": "san martin de porres", "sjm": "san juan de miraflores",
    "vmt": "villa maria del triunfo", "ves": "villa el salvador", "la punta callao": "la punta", "bellavista callao": "bellavista",
    "jose luis bustamante y rivero": "jose luis bustamante y rivero", "bustamante y rivero": "jose luis bustamante y rivero",
    "cusco cercado": "cusco", "machu picchu": "machupicchu",
}


def _norm(t):
    from .valoracion import norm
    return norm(t)


@lru_cache(maxsize=1)
def tablas():
    filas = json.loads((Path(__file__).parent / "data" / "distritos.json").read_text(encoding="utf-8"))
    distritos, provincias, departamentos = {}, {}, {}
    for dep, prov, dist in filas:
        distritos.setdefault(_norm(dist), []).append((dep, prov, dist))
        provincias.setdefault(_norm(prov), set()).add(dep)
        departamentos[_norm(dep)] = dep
    departamentos["lima metropolitana"] = "Lima"
    return distritos, provincias, departamentos


def resolver(*textos):
    distritos, provincias, departamentos = tablas()
    partes = []
    for t in textos:
        for p in str(t or "").replace(" - ", ",").replace("|", ",").split(","):
            n = _norm(p)
            if n:
                partes.append((p.strip(), ALIAS.get(n, n)))
    deps_vistos = {departamentos[n] for _, n in partes if n in departamentos}
    for _, n in partes:
        deps_vistos |= provincias.get(n, set()) if len(provincias.get(n, set())) == 1 else set()
    provs_vistas = {n for _, n in partes if n in provincias}
    for k in range(len(partes) - 1, -1, -1):
        original, n = partes[k]
        opciones = distritos.get(n)
        if not opciones:
            continue
        otras = [m for j, (_, m) in enumerate(partes) if j != k]
        if n in departamentos and n in provincias and any(m in distritos for m in otras if m not in departamentos):
            continue
        mejor = sorted(opciones, key=lambda o: (
            -(_norm(o[0]) in {_norm(d) for d in deps_vistos}),
            -(_norm(o[1]) in provs_vistas),
            -(_norm(o[0]) == "lima"),
            -(_norm(o[1]) == _norm(o[2])),
        ))[0]
        barrio = ", ".join(p for p, m in partes[:k] if m not in distritos and m not in provincias and m not in departamentos)
        return {"departamento": mejor[0], "provincia": mejor[1], "distrito": mejor[2], "barrio": barrio or None}
    if deps_vistos:
        return {"departamento": sorted(deps_vistos)[0]}
    return {}
