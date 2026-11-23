import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx

from .. import config, llm
from ..notificar import telegram
from ..valoracion import norm
from .mejora import crear_issue

LIMITE_DB = int(500 * 1024 * 1024)


def _fecha(x):
    return datetime.fromisoformat(str(x).replace("Z", "+00:00")) if x else None


def revisar(db, ahora=None):
    ahora = ahora or datetime.now(timezone.utc)
    problemas = []

    def falla(gravedad, texto):
        problemas.append({"gravedad": gravedad, "texto": texto})

    for nombre, valor in [("SUPABASE_URL", config.SUPABASE_URL), ("SUPABASE_SERVICE_KEY", config.SUPABASE_KEY)]:
        if not valor:
            falla("critico", f"Falta el secreto {nombre}")
    if not llm.disponible():
        falla("alto", "No hay clave de IA (GEMINI_API_KEY o ANTHROPIC_API_KEY): el buscador y la autorreparación están apagados")
    if not config.TELEGRAM_TOKEN:
        falla("medio", "Sin TELEGRAM_TOKEN: las alertas solo se imprimen en los registros")

    ejec = db.select("ejecuciones", select="agente,ok,fin,detalle", order="inicio.desc", limit="300")
    ultimo_ok = max((_fecha(e["fin"]) for e in ejec if e["agente"] == "analista" and e["ok"] and e.get("fin")), default=None)
    if not ultimo_ok or ultimo_ok < ahora - timedelta(hours=8):
        falla("critico", f"El analista no termina bien desde {ultimo_ok or 'nunca'}")
    recientes = [e for e in ejec if e.get("fin") and _fecha(e["fin"]) > ahora - timedelta(hours=24)]
    malos = {}
    for e in recientes:
        if not e["ok"]:
            malos.setdefault(e["agente"], []).append(str((e.get("detalle") or {}).get("error", ""))[:200])
    for agente, errores in malos.items():
        falla("alto" if len(errores) >= 2 else "medio", f"{agente} falló {len(errores)} vez/veces en 24 h: {errores[0]}")

    for f in db.select("fuentes", select="id,nombre,tipo,activo,fallos_seguidos,ultimo_ok,ultimo_error,config", activo="eq.true"):
        if f["tipo"] not in ("navent", "ia"):
            continue
        cfg = f.get("config") or {}
        if f["fallos_seguidos"] >= 3:
            falla("alto", f"Fuente {f['nombre']} caída ({f['fallos_seguidos']} fallos, en pausa hasta {cfg.get('pausado_hasta', '—')}): {(f['ultimo_error'] or '')[:150]}")
        elif cfg.get("promedio_total") and cfg.get("ultimo_total", 0) < 0.4 * cfg["promedio_total"]:
            falla("medio", f"Fuente {f['nombre']} trajo {cfg.get('ultimo_total')} avisos; lo normal es ~{cfg['promedio_total']:.0f}. Puede haber cambiado la página")

    hace2 = (ahora - timedelta(hours=48)).isoformat()
    if not db.select("inmuebles", select="id", primera_vez=f"gte.{hace2}", limit="1"):
        falla("alto", "No entró ningún inmueble nuevo en 48 horas")

    tc = db.select("parametros", select="valor,actualizado", clave="eq.tipo_cambio")
    if not tc or _fecha(tc[0]["actualizado"]) < ahora - timedelta(days=4):
        falla("medio", "El tipo de cambio del BCRP no se actualiza hace más de 4 días (se usa el último valor)")
    else:
        valor = float(tc[0]["valor"])
        if not 2.5 < valor < 6:
            falla("alto", f"Tipo de cambio raro: {valor}")

    primera = db.select("ejecuciones", select="inicio", order="inicio.asc", limit="1")
    if primera and _fecha(primera[0]["inicio"]) < ahora - timedelta(days=14):
        vistos = {norm(f.get("departamento")) for f in db.select_all("inmuebles", select="departamento", activo="eq.true")}
        vacios = [d for d in config.DEPARTAMENTOS if norm(d) not in vistos]
        if vacios:
            falla("medio", f"Sin inmuebles en {len(vacios)} departamentos: {', '.join(vacios[:8])}. El explorador los priorizará")
    temporal = db.select("mercado_temporal", select="fecha", order="fecha.desc", limit="1")
    if not temporal or _fecha(temporal[0]["fecha"]) < ahora - timedelta(days=10):
        falla("medio", "Los datos de Airbnb no se actualizan hace más de 10 días: el análisis por días puede estar desfasado")
    atascadas = db.select("pistas", select="id", estado="eq.nueva", limit="300")
    if len(atascadas) >= 300:
        falla("medio", "Hay más de 300 pistas sin verificar: conviene correr el verificador más seguido")

    raros = db.select("analisis", select="inmueble_id", tir_10="gt.0.6", limit="50")
    if len(raros) >= 10:
        falla("medio", f"{len(raros)} análisis con TIR mayor a 60%: probable error de datos (precio o área mal leídos)")

    try:
        tamano = db.rpc("tamano_db")
        if tamano and tamano > 0.8 * LIMITE_DB:
            limpio = db.rpc("limpiar_antiguo")
            falla("alto" if tamano > 0.95 * LIMITE_DB else "medio", f"Base de datos al {tamano / LIMITE_DB:.0%} del límite gratis; se limpió: {limpio}")
    except httpx.HTTPError as e:
        falla("medio", f"No se pudo medir el tamaño de la base: {e}")

    api = config.API_URL
    if api:
        try:
            httpx.get(f"{api.rstrip('/')}/salud", timeout=60).raise_for_status()
        except httpx.HTTPError as e:
            falla("alto", f"La API no responde: {e}")
    return problemas


def ejecutar(db, p):
    problemas = revisar(db)
    huella = hashlib.sha1(json.dumps(sorted(x["texto"][:60] for x in problemas)).encode()).hexdigest()
    previo = p.get("vigilante_huella")
    if problemas and huella != previo:
        iconos = {"critico": "🚨", "alto": "⚠️", "medio": "ℹ️"}
        telegram("Vigilante del analizador inmobiliario\n\n" + "\n".join(f"{iconos[x['gravedad']]} {x['texto']}" for x in problemas))
        graves = [x for x in problemas if x["gravedad"] in ("critico", "alto")]
        if graves:
            crear_issue(
                f"Vigilante: {graves[0]['texto'][:70]}",
                "Problemas detectados:\n" + "\n".join(f"- **{x['gravedad']}**: {x['texto']}" for x in problemas)
                + "\n\n@claude investiga la causa en el código y en los registros de Actions, corrige lo que se pueda y abre un PR con pruebas.",
            )
    elif not problemas and previo:
        telegram("✅ Analizador inmobiliario: todo volvió a la normalidad")
    db.upsert("parametros", {"clave": "vigilante_huella", "valor": huella if problemas else ""}, on_conflict="clave")
    return {"problemas": problemas}
