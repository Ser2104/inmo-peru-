import httpx

from inmo import config, llm, db as dbmod


def test_ia_cambia_de_proveedor(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "x")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "y")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    peticion = httpx.Request("POST", "https://g")

    def gemini_caido(prompt, buscar):
        raise httpx.HTTPStatusError("cuota", request=peticion, response=httpx.Response(429, request=peticion))

    monkeypatch.setitem(llm.PROVEEDORES, "gemini", (gemini_caido, lambda: "x"))
    monkeypatch.setitem(llm.PROVEEDORES, "anthropic", (lambda p, b: '```json\n[{"ok": 1}]\n```', lambda: "y"))
    assert llm.pedir_json("hola") == [{"ok": 1}]


def test_base_reintenta(monkeypatch):
    monkeypatch.setattr(dbmod.time, "sleep", lambda s: None)
    respuestas = [httpx.Response(503), httpx.Response(200, json=[{"a": 1}])]
    peticion = httpx.Request("GET", "https://s")
    for r in respuestas:
        r.request = peticion
    llamadas = iter(respuestas)
    assert dbmod._con_reintentos(lambda *a, **k: next(llamadas)).json() == [{"a": 1}]


def test_gemini_salta_modelos_retirados(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    usados = []

    def post(url, **k):
        modelo = url.split("/models/")[1].split(":")[0]
        usados.append(modelo)
        req = httpx.Request("POST", url)
        if modelo == "gemini-2.5-flash":
            return httpx.Response(404, request=req)
        return httpx.Response(200, request=req, json={"candidates": [{"content": {"parts": [{"text": "pienso", "thought": True}, {"text": "[1]"}]}}]})

    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm._gemini("x", False) == "[1]"
    assert usados == ["gemini-2.5-flash", "gemini-flash-latest"]


def test_proveedor_compatible_openai_va_primero(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "k")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "https://api.luminal.test/v1")
    monkeypatch.setattr(config, "OPENAI_MODEL", "modelo")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "g")

    def post(url, **k):
        req = httpx.Request("POST", url)
        assert url == "https://api.luminal.test/v1/chat/completions" and k["json"]["model"] == "modelo"
        return httpx.Response(200, request=req, json={"choices": [{"message": {"content": '{"ok": 1}'}}]})

    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm._pedir("x", False, 1) == {"ok": 1}
