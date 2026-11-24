import os

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
API_KEY = os.getenv("INMO_API_KEY", "")
API_URL = os.getenv("INMO_API_URL", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER") or ("openai" if os.getenv("OPENAI_API_KEY") else "gemini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")

AIRROI_API_KEY = os.getenv("AIRROI_API_KEY", "")
AIRROI_MAX_LLAMADAS = int(os.getenv("AIRROI_MAX_LLAMADAS", "100"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPOSITORY", "")

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")
BUSQUEDA_GOOGLE = os.getenv("BUSQUEDA_GOOGLE", "auto")

MAX_PAGINAS = int(os.getenv("MAX_PAGINAS", "40"))
MINUTOS_POR_PASO = int(os.getenv("MINUTOS_POR_PASO", "90"))

PARAMETROS_BASE = {
    "tipo_cambio": 3.45,
    "uit_soles": 5500,
    "alcabala": 0.03,
    "alcabala_uit_exentas": 10,
    "gastos_notariales": 0.01,
    "impuesto_renta_alquiler": 0.05,
    "predial_anual": 0.004,
    "reparaciones_anual": 0.005,
    "seguro_anual": 0.001,
    "vacancia": 0.083,
    "administracion": 0.0,
    "comision_venta": 0.03,
    "inflacion_alquiler": 0.025,
    "plusvalia_default": 0.03,
    "rentabilidad_bruta_default": 0.055,
    "tasa_descuento": 0.07,
    "cuota_inicial": 1.0,
    "tasa_hipoteca": 0.075,
    "plazo_hipoteca": 20,
    "ajuste_renta": 1.0,
    "min_comparables": 5,
    "umbral_alerta": 7.5,
    "descuento_negociacion": 0.07,
    "pago_inicial_preventa": 0.2,
    "comision_plataforma": 0.03,
    "gestion_temporal": 0.20,
    "estadia_promedio": 3,
    "limpieza_neta_usd": 6,
    "servicios_temporal_usd": 70,
    "amoblado_usd_m2": 110,
    "amoblado_minimo_usd": 4500,
    "reposicion_amoblado": 0.12,
    "rampa_temporal": 0.75,
    "ocupacion_temporal_default": 0.45,
    "prima_riesgo_temporal": 0.01,
    "impuesto_ganancia_capital": 0.05,
}

DEPARTAMENTOS = [
    "Amazonas", "Áncash", "Apurímac", "Arequipa", "Ayacucho", "Cajamarca", "Callao", "Cusco",
    "Huancavelica", "Huánuco", "Ica", "Junín", "La Libertad", "Lambayeque", "Lima", "Loreto",
    "Madre de Dios", "Moquegua", "Pasco", "Piura", "Puno", "San Martín", "Tacna", "Tumbes", "Ucayali",
]
