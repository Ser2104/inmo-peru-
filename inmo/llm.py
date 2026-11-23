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
    cuerpo = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}
    if buscar:
        cuerpo["tools"] = [{"google_search": {}}]
    else:
        cuerpo["generationConfig"]["responseMimeType"] = "application/json"
    modelos = list(dict.fromkeys([m for m in [config.GEMINI_MODEL] if m] + MODELOS_GEMINI))
    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        r = httpx.post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=cuerpo, timeout=180)
        if r.status_code == 400 and "thinking" in r.text.lower():
            cuerpo["generationConfig"].pop("thinkingConfig", None)
            r = httpx.post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY}, json=cuerpo, timeout=180)
        if r.status_code in (404, 429, 500, 503) and modelo != modelos[-1]:
            continue
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(f"{r.status_code} en {modelo}: {r.text[:300]}", request=r.request, response=r)
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


_SIN_BUSQUEDA_NATIVA = set()

PROMPT_CONSULTAS = """Para cumplir esta tarea necesitas buscar en internet. Escribe de 3 a 5 búsquedas cortas y distintas (como las escribirías en Google),
en español, específicas para Perú. Devuelve una lista JSON de textos.

TAREA:
{tarea}"""

PROMPT_RESPONDER = """{tarea}

Usa SOLO la información de estos resultados de búsqueda y páginas (no inventes, usa null si falta un dato; las url deben salir de aquí):
{contexto}"""


def _buscar_gratis(prompt, intentos):
    from . import busqueda
    consultas = pedir_json(PROMPT_CONSULTAS.format(tarea=prompt[:3000]), intentos=intentos)
    resultados, vistos = [], set()
    for c in [str(x) for x in (consultas if isinstance(consultas, list) else [])][:5]:
        for r in busqueda.buscar_web(c):
            if r["url"] not in vistos:
                vistos.add(r["url"])
                resultados.append(r)
    if not resultados:
        raise RuntimeError("La búsqueda gratis no devolvió resultados")
    partes = [f"- {r['titulo']} | {r['url']} | {r.get('resumen') or ''}" for r in resultados[:25]]
    for r in resultados[:5]:
        texto = busqueda.texto_pagina(r["url"])
        if texto:
            partes.append(f"\nPÁGINA {r['url']}:\n{texto}")
    return pedir_json(PROMPT_RESPONDER.format(tarea=prompt, contexto="\n".join(partes)[:60000]), intentos=intentos)


def pedir_json(prompt, buscar=False, intentos=3):
    if buscar:
        nativa = config.BUSQUEDA_GOOGLE != "no" and not _SIN_BUSQUEDA_NATIVA
        if nativa:
            try:
                return _pedir(prompt, True, 1 if config.BUSQUEDA_GOOGLE == "auto" else intentos)
            except RuntimeError as e:
                if "429" in str(e) or "403" in str(e) or "quota" in str(e).lower():
                    _SIN_BUSQUEDA_NATIVA.add(True)
        return _buscar_gratis(prompt, intentos)
    return _pedir(prompt, False, intentos)


def _pedir(prompt, buscar, intentos):
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
                codigo = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
                if codigo in (401, 403):
                    break
                time.sleep(min(120, (30 if codigo == 503 else 5) * 2 ** n))
    raise RuntimeError("Ninguna IA respondió: " + " | ".join(errores[-4:]))
