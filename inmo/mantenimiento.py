import gzip
import json
from pathlib import Path

from . import config, llm
from .collectors import bcrp
from .notificar import telegram

TABLAS = ["fuentes", "inmuebles", "precios_historial", "series_macro", "zonas_stats", "analisis", "alertas", "parametros"]


def respaldo(db, carpeta="respaldo"):
    Path(carpeta).mkdir(exist_ok=True)
    conteo = {}
    for t in TABLAS:
        filas = db.select_all(t, select="*")
        with gzip.open(Path(carpeta) / f"{t}.json.gz", "wt", encoding="utf-8") as f:
            json.dump(filas, f, default=str, ensure_ascii=False)
        conteo[t] = len(filas)
    return conteo


def restaurar(db, carpeta="respaldo"):
    claves = {"fuentes": "id", "inmuebles": "id", "precios_historial": "inmueble_id,fecha", "series_macro": "codigo,periodo",
              "zonas_stats": "departamento,provincia,distrito,tipo,operacion,segmento", "analisis": "inmueble_id", "alertas": "inmueble_id", "parametros": "clave"}
    conteo = {}
    for t in TABLAS:
        ruta = Path(carpeta) / f"{t}.json.gz"
        if ruta.exists():
            with gzip.open(ruta, "rt", encoding="utf-8") as f:
                filas = json.load(f)
            db.upsert(t, filas, on_conflict=claves[t])
            conteo[t] = len(filas)
    return conteo


PORTALES = [("Urbania", "https://urbania.pe/"), ("Adondevivir", "https://www.adondevivir.com/"), ("Properati", "https://www.properati.com.pe/"),
            ("Nexo", "https://nexoinmobiliario.pe/"), ("BBVA adjudicados", "https://www.bbva.pe/personas/productos/inversiones/irbsa.html")]


def _abre(url):
    from .collectors.base import descargar
    try:
        return bool(descargar(url, intentos=1, pausa=(0, 0)))
    except RuntimeError:
        return False


def _exigir(condicion, mensaje):
    if not condicion:
        raise RuntimeError(mensaje)


def diagnostico(db):
    filas = []

    def check(nombre, funcion):
        try:
            detalle = funcion()
            filas.append(("✅", nombre, detalle or ""))
        except Exception as e:
            filas.append(("❌", nombre, str(e)[:200]))

    check("Variables de Supabase", lambda: _exigir(config.SUPABASE_URL and config.SUPABASE_KEY, "faltan SUPABASE_URL / SUPABASE_SERVICE_KEY"))
    check("Conexión a la base", lambda: f"{len(db.select('fuentes', select='id'))} fuentes")
    for t in TABLAS + ["ejecuciones"]:
        check(f"Tabla {t}", lambda t=t: db.select(t, select="*", limit="1") and None)
    check("Funciones de mantenimiento", lambda: f"{db.rpc('tamano_db') / 1e6:.1f} MB usados")
    check("IA", lambda: _exigir(llm.disponible(), "falta GEMINI_API_KEY o ANTHROPIC_API_KEY") or (llm.pedir_json('Devuelve {"ok": true}', intentos=1) and "responde"))
    check("IA con búsqueda en internet", lambda: llm.pedir_json('Busca el tipo de cambio del dólar en Perú hoy y devuelve {"tc": número}', buscar=True, intentos=1) and "responde")
    check("BCRP", lambda: f"{len(bcrp._serie(bcrp.TIPO_CAMBIO, '2026-01-01', '2026-12-31'))} datos de tipo de cambio")
    check("Portales", lambda: ", ".join(f"{n}: {'ok' if _abre(u) else 'bloqueado'}" for n, u in PORTALES))
    check("Telegram", lambda: _exigir(telegram("Prueba del analizador inmobiliario ✅"), "no configurado") or "mensaje enviado")
    for icono, nombre, detalle in filas:
        print(icono, nombre, detalle)
    return {"ok": all(f[0] == "✅" for f in filas), "fallos": [f[1] for f in filas if f[0] == "❌"]}
