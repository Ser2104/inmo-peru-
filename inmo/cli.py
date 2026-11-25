import argparse
import json
import signal
import sys
import traceback
from datetime import date

from . import config, mantenimiento
from .db import DB
from .collectors import bcrp, runner
from .agents import analista, auditor, buscador, alertas, mejora, vigilante, explorador, temporal, ubicador, rastreador, concesiones, confirmador, oportunidades


class Tiempo(BaseException):
    pass


def _alarma(*_):
    raise Tiempo(f"superó {config.MINUTOS_POR_PASO} minutos")


def paso(db, nombre, funcion):
    signal.signal(signal.SIGALRM, _alarma)
    signal.alarm(config.MINUTOS_POR_PASO * 60)
    try:
        r = funcion()
        db.registrar(nombre, True, r)
        print(nombre, json.dumps(r, default=str, ensure_ascii=False)[:2000])
        return r
    except (Exception, Tiempo) as e:
        try:
            db.registrar(nombre, False, {"error": str(e), "traza": traceback.format_exc()[-1500:]})
        except Exception:
            pass
        print(nombre, "ERROR", e, file=sys.stderr)
    finally:
        signal.alarm(0)


def recolectar(db, p, completo):
    fuentes = db.select("fuentes", select="*", activo="eq.true", tipo="in.(navent,ia)")
    for f in fuentes:
        paso(db, f"recolector:{f['id']}", lambda f=f: runner.recolectar_fuente(db, f, p, completo, mejora.reparar_selectores))


def main():
    ap = argparse.ArgumentParser(description="Analizador inmobiliario Perú")
    ap.add_argument("tarea", choices=["ciclo", "completo", "bcrp", "buscar", "analizar", "auditar", "alertas", "mejorar",
                                      "vigilar", "respaldo", "restaurar", "diagnostico", "explorar", "verificar", "temporal", "ubicar", "renormalizar", "probar", "rastrear", "rapido", "concesiones", "confirmar", "reubicar", "barrer", "oportunidades"])
    ap.add_argument("--urls", nargs="*")
    ap.add_argument("--departamentos", nargs="*")
    ap.add_argument("--fuentes", nargs="*", default=[])
    a = ap.parse_args()
    db = DB()
    if a.tarea == "diagnostico":
        sys.exit(0 if mantenimiento.diagnostico(db)["ok"] else 1)
    if a.tarea == "barrer":
        p = db.parametros()
        for f in db.select("fuentes", select="*", id=f"in.({','.join(a.fuentes)})"):
            paso(db, f"barrido:{f['id']}", lambda f=f: runner.recolectar_fuente(db, f, p, completo=True, reparar=mejora.reparar_selectores, sin_limite=True))
        return
    if a.tarea == "reubicar":
        print(ubicador.reubicar(db), ubicador.reubicar(db, "concesiones"))
        return
    if a.tarea == "renormalizar":
        print(mantenimiento.renormalizar(db))
        return
    if a.tarea == "probar":
        mantenimiento.probar(a.urls or [])
        return
    if a.tarea == "respaldo":
        print(mantenimiento.respaldo(db))
        return
    if a.tarea == "restaurar":
        print(mantenimiento.restaurar(db))
        return
    p = db.parametros()

    lento = a.tarea == "completo"
    if a.tarea in ("bcrp", "completo"):
        paso(db, "bcrp", lambda: bcrp.actualizar(db, date.today().year))
        p = db.parametros()
    if a.tarea in ("ciclo", "completo"):
        recolectar(db, p, lento)
    if a.tarea in ("ciclo", "completo", "auditar"):
        paso(db, "auditor", lambda: auditor.ejecutar(db))
    if a.tarea in ("ciclo", "completo", "ubicar"):
        paso(db, "ubicador", lambda: ubicador.ejecutar(db))
    if a.tarea in ("ciclo", "completo", "analizar"):
        paso(db, "analista", lambda: analista.ejecutar(db, p, todo=a.tarea != "ciclo"))
    if a.tarea in ("ciclo", "completo", "analizar", "confirmar"):
        paso(db, "confirmador", lambda: confirmador.ejecutar(db))
    if a.tarea in ("ciclo", "completo", "alertas"):
        paso(db, "alertas", lambda: alertas.ejecutar(db, p))
    if a.tarea in ("temporal", "completo"):
        paso(db, "temporal", lambda: temporal.ejecutar(db, p))
    if a.tarea in ("buscar", "completo"):
        paso(db, "buscador", lambda: buscador.ejecutar(db, p, a.departamentos))
    if a.tarea in ("explorar", "completo"):
        paso(db, "explorador", lambda: explorador.ejecutar(db, p))
    if a.tarea in ("rastrear", "completo"):
        paso(db, "rastreador", lambda: rastreador.ejecutar(db, p))
    if a.tarea in ("ciclo", "verificar"):
        paso(db, "verificador", lambda: explorador.verificar(db, p))
        paso(db, "respuestas", lambda: explorador.procesar_respuestas(db, p))
    if a.tarea in ("oportunidades", "completo"):
        paso(db, "oportunidades", lambda: oportunidades.ejecutar(db, p, con_web="seace" not in a.fuentes))
    if a.tarea in ("concesiones", "completo"):
        paso(db, "concesiones", lambda: concesiones.ejecutar(db, p))
    if a.tarea in ("mejorar", "completo"):
        paso(db, "mejora", lambda: mejora.ejecutar(db, p))
    if a.tarea == "completo":
        paso(db, "analista", lambda: analista.ejecutar(db, db.parametros(), todo=True))
        paso(db, "confirmador", lambda: confirmador.ejecutar(db))
    if a.tarea in ("ciclo", "completo", "vigilar"):
        paso(db, "vigilante", lambda: vigilante.ejecutar(db, db.parametros()))

if __name__ == "__main__":
    main()
