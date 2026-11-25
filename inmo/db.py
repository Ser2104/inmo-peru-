import json
import time
from datetime import datetime, timezone

import httpx

from . import config


def _con_reintentos(funcion, *args, intentos=5, **kwargs):
    for n in range(intentos):
        try:
            r = funcion(*args, **kwargs)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r
        except (httpx.UnsupportedProtocol, httpx.InvalidURL):
            raise
        except (httpx.TransportError, httpx.TimeoutException):
            if n == intentos - 1:
                raise
        time.sleep(min(60, 2 ** n * 2))
    r.raise_for_status()
    return r


class DB:
    def __init__(self, url=None, key=None):
        url = url or config.SUPABASE_URL
        key = key or config.SUPABASE_KEY
        self.http = httpx.Client(
            base_url=f"{url}/rest/v1",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            timeout=60,
        )

    def select(self, tabla, **params):
        return _con_reintentos(self.http.get, f"/{tabla}", params=params).json()

    CLAVE_ORDEN = {"inmuebles": "id", "oportunidades": "id", "analisis": "inmueble_id", "arbitraje": "inmueble_id", "concesiones": "id"}

    def select_all(self, tabla, pagina=1000, **params):
        clave = self.CLAVE_ORDEN.get(tabla)
        if clave and "order" not in params and clave in str(params.get("select", clave)).split(",") + ["*"] or (clave and params.get("select") == "*"):
            filas, ultimo = [], None
            while True:
                extra = {"order": f"{clave}.asc", "limit": str(pagina)}
                if ultimo:
                    extra[clave] = f"gt.{ultimo}"
                lote = _con_reintentos(self.http.get, f"/{tabla}", params={**params, **extra}).json()
                filas += lote
                if len(lote) < pagina:
                    return filas
                ultimo = lote[-1][clave]
        filas, inicio = [], 0
        while True:
            lote = _con_reintentos(self.http.get, f"/{tabla}", params=params, headers={"Range": f"{inicio}-{inicio + pagina - 1}"}).json()
            filas += lote
            if len(lote) < pagina:
                return filas
            inicio += pagina

    def upsert(self, tabla, filas, on_conflict=None, devolver=False):
        if not filas:
            return []
        filas = filas if isinstance(filas, list) else [filas]
        params = {"on_conflict": on_conflict} if on_conflict else {}
        pref = "resolution=merge-duplicates," + ("return=representation" if devolver else "return=minimal")
        salida = []
        for i in range(0, len(filas), 500):
            r = _con_reintentos(self.http.post, f"/{tabla}", params=params, content=json.dumps(filas[i:i + 500], default=str), headers={"Prefer": pref})
            if devolver:
                salida += r.json()
        return salida

    def delete(self, tabla, **filtros):
        _con_reintentos(self.http.delete, f"/{tabla}", params=filtros)

    def update(self, tabla, valores, **filtros):
        _con_reintentos(self.http.patch, f"/{tabla}", params=filtros, content=json.dumps(valores, default=str))

    def rpc(self, funcion, **args):
        r = _con_reintentos(self.http.post, f"/rpc/{funcion}", content=json.dumps(args, default=str))
        return r.json() if r.content else None

    def parametros(self):
        p = dict(config.PARAMETROS_BASE)
        for fila in self.select("parametros", select="clave,valor"):
            p[fila["clave"]] = fila["valor"]
        return p

    def registrar(self, agente, ok, detalle):
        fin = datetime.now(timezone.utc).isoformat()
        self.upsert("ejecuciones", {"agente": agente, "ok": ok, "detalle": detalle, "fin": fin})
