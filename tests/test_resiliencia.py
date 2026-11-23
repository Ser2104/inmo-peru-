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
