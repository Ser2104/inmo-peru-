from inmo import llm
from inmo.agents import descubridor
from tests.fake_db import FakeDB


def test_descubre_filtra_portales_y_verifica(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(descubridor, "consultas", lambda db, n, *a: [("Cusco", "Cusco", "departamentos en venta Cusco constructora")])
    monkeypatch.setattr(descubridor, "buscar_web", lambda q, n=10: [
        {"url": "https://www.ninadepartamentos.pe/proyectos", "titulo": "NINA departamentos en preventa", "resumen": "Departamentos de 1 y 2 dormitorios"},
        {"url": "https://urbania.pe/buscar/x", "titulo": "Departamentos", "resumen": "precio"},
        {"url": "https://www.recetas.pe", "titulo": "Recetas", "resumen": "ají de gallina"}])
    assert descubridor.descubrir(db, cantidad=1, pausa=0)["sitios_nuevos"] == 1
    assert db.t["sitios"][0]["dominio"] == "ninadepartamentos.pe" and db.t["sitios"][0]["departamento"] == "Cusco"
    db.t["sitios"][0].update(estado="nuevo", origen="buscador")
    monkeypatch.setattr(descubridor, "texto_pagina", lambda url, n: "Proyecto NINA, departamentos desde S/ 300,000")
    monkeypatch.setattr(llm, "disponible", lambda: True)
    monkeypatch.setattr(llm, "pedir_json", lambda p, **k: {"inmobiliaria": True, "ciudad": "Cusco", "motivo": "constructora con proyectos"})
    assert descubridor.verificar(db)["inmobiliaria"] == 1
    assert db.t["sitios"][0]["estado"] == "inmobiliaria"
