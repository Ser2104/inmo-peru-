import uuid
from datetime import datetime, timezone

from inmo.config import PARAMETROS_BASE

CLAVES = {"inmuebles": ["url"], "precios_historial": ["inmueble_id", "fecha"], "analisis": ["inmueble_id"], "alertas": ["inmueble_id"],
          "parametros": ["clave"], "fuentes": ["id"], "zonas_stats": ["departamento", "provincia", "distrito", "tipo", "operacion", "segmento"],
          "series_macro": ["codigo", "periodo"], "ejecuciones": [None], "pistas": ["clave"], "mercado_temporal": ["clave"], "regulacion_temporal": ["departamento", "distrito"], "arbitraje": ["inmueble_id"], "geocache": ["consulta"], "rastreo": ["url"], "concesiones": ["clave"], "entorno": ["clave"], "oportunidades": ["clave"]}


def _cumple(fila, campo, cond):
    v = fila.get(campo)
    op, _, val = cond.partition(".")
    if op == "eq":
        return str(v).lower() == val.lower()
    if op == "lt":
        return v is not None and float(v) < float(val)
    if op == "in":
        return str(v) in val.strip("()").split(",")
    if op in ("gte", "gt"):
        if v is None:
            return False
        try:
            a, b = float(v), float(val)
        except (TypeError, ValueError):
            a, b = str(v), val
        return a >= b if op == "gte" else a > b
    if op == "is":
        return v is None
    if cond == "not.is.null":
        return v is not None
    return True


class FakeDB:
    def __init__(self):
        self.t = {k: [] for k in CLAVES}

    def _filtrar(self, tabla, params):
        filas = self.t[tabla]
        for k, cond in params.items():
            if k in ("select", "order", "limit", "on_conflict"):
                continue
            filas = [f for f in filas if _cumple(f, k, cond)]
        return [dict(f) for f in filas]

    def select(self, tabla, **p):
        return self._filtrar(tabla, p)

    select_all = select

    def upsert(self, tabla, filas, on_conflict=None, devolver=False):
        filas = filas if isinstance(filas, list) else [filas]
        salida = []
        for f in filas:
            clave = CLAVES[tabla]
            existente = None if clave == [None] else next((e for e in self.t[tabla] if all(e.get(c) == f.get(c) for c in clave)), None)
            if existente:
                existente.update(f)
            else:
                existente = dict(f)
                if tabla in ("inmuebles", "pistas", "concesiones"):
                    existente.setdefault("id", str(uuid.uuid4()))
                    existente.setdefault("primera_vez", datetime.now(timezone.utc).isoformat())
                if tabla == "concesiones":
                    existente.setdefault("revisado", False)
                    existente.setdefault("contacto_estado", "pendiente")
                if tabla == "pistas":
                    existente.setdefault("estado", "nueva")
                    existente.setdefault("intentos", 0)
                    existente.setdefault("creado", datetime.now(timezone.utc).isoformat())
                self.t[tabla].append(existente)
            salida.append(dict(existente))
        return salida

    def update(self, tabla, valores, **filtros):
        for f in self.t[tabla]:
            if all(_cumple(f, k, c) for k, c in filtros.items()):
                f.update(valores)

    def parametros(self):
        p = dict(PARAMETROS_BASE)
        p.update({f["clave"]: f["valor"] for f in self.t["parametros"]})
        return p

    def registrar(self, agente, ok, detalle):
        ahora = datetime.now(timezone.utc).isoformat()
        self.t["ejecuciones"].append({"agente": agente, "ok": ok, "detalle": detalle, "inicio": ahora, "fin": ahora})

    tamano = 10_000_000

    def rpc(self, funcion, **args):
        return self.tamano if funcion == "tamano_db" else {"limpiado": True}
