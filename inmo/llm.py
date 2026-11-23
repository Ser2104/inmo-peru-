import json
import re
import time

import httpx

from . import config


def _json(texto):
    texto = texto.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    if m:
        texto = m.group(1)
    inicio = min([i for i in (texto.find("["), texto.find("{")) if i >= 0], default=0)
    return json.loads(texto[inicio:])


MODELOS_GEMINI = ["gemini-flash-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite"]


def _gemini(prompt, buscar):
    cuerpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if buscar:
        cuerpo["tools"] = [{"google_search": {}}]
    else:
        cuerpo["generationConfig"] = {"responseMimeType": "application/json"}
    modelos = list(dict.fromkeys([m for m in [config.GEMINI_MODEL] if m] + MODELOS_GEMINI))
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        r = httpx.post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=cuerpo, timeout=180)
        if r.status_code in (404, 429, 500, 503) and modelo != modelos[-1]:
            continue
        r.raise_for_status()
        partes = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in partes if not p.get("thought"))


def _anthropic(prompt, buscar):
    cuerpo = {"model": config.ANTHROPIC_MODEL, "max_tokens": 8000, "messages": [{"role": "user", "content": prompt}]}
    if buscar:
        cuerpo["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 8}]
    r = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
        json=cuerpo,
        timeout=300,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"] if b["type"] == "text")


PROVEEDORES = {"gemini": (_gemini, lambda: config.GEMINI_API_KEY), "anthropic": (_anthropic, lambda: config.ANTHROPIC_API_KEY)}


def _orden():
    primero = config.LLM_PROVIDER if config.LLM_PROVIDER in PROVEEDORES else "gemini"
    return [primero] + [p for p in PROVEEDORES if p != primero]


def disponible():
    return any(PROVEEDORES[p][1]() for p in PROVEEDORES)


def pedir_json(prompt, buscar=False, intentos=3):
    errores = []
    for nombre in _orden():
        llamar, clave = PROVEEDORES[nombre]
        if not clave():
            continue
        for n in range(intentos):
            try:
                return _json(llamar(prompt + "\n\nResponde solo con JSON válido.", buscar))
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
                errores.append(f"{nombre}: {e}")
                cuota = isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403)
                if cuota:
                    break
                time.sleep(min(60, 5 * 2 ** n))
    raise RuntimeError("Ninguna IA respondió: " + " | ".join(errores[-4:]))
