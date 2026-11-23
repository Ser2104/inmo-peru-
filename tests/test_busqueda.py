from inmo import config, llm, busqueda
from inmo.agents import rastreador
from inmo.collectors import base, ia
from tests.fake_db import FakeDB

SITEMAP_INDICE = '<sitemapindex><sitemap><loc>https://constructora.pe/proyectos-sitemap.xml</loc></sitemap></sitemapindex>'
SITEMAP = ('<urlset><url><loc>https://constructora.pe/proyecto/torre-sol</loc></url><url><loc>https://constructora.pe/blog/consejos</loc></url>'
           '<url><loc>https://constructora.pe/departamentos/vista-mar</loc></url><url><loc>https://otro.pe/proyecto/x</loc></url></urlset>')


def paginas(url, **k):
    if url.endswith("robots.txt"):
        return "User-agent: *\nDisallow: /privado\nSitemap: https://constructora.pe/sitemap_index.xml"
    return {"https://constructora.pe/sitemap_index.xml": SITEMAP_INDICE, "https://constructora.pe/proyectos-sitemap.xml": SITEMAP}.get(url, "<html></html>")


def test_sitemap_filtra_paginas_utiles(monkeypatch):
    monkeypatch.setattr(base, "descargar", paginas)
    assert rastreador.paginas_candidatas("https://www.constructora.pe/") == ["https://constructora.pe/proyecto/torre-sol", "https://constructora.pe/departamentos/vista-mar"]


def test_rastreador_no_repite(monkeypatch):
    db = FakeDB()
    db.upsert("fuentes", {"id": "c", "nombre": "C", "tipo": "ia", "activo": True, "urls": ["https://constructora.pe/"]})
    monkeypatch.setattr(base, "descargar", paginas)
    monkeypatch.setattr(ia, "extraer", lambda html, url: [{"url": url, "titulo": "Depa", "precio": 300000, "moneda": "PEN", "area_m2": 70, "distrito": "Cayma", "departamento": "Arequipa"}])
    p = {**db.parametros(), "tipo_cambio": 3.45}
    assert rastreador.ejecutar(db, p)["inmuebles"] == 2
    assert rastreador.ejecutar(db, p)["paginas_nuevas"] == 0
    assert db.t["inmuebles"][0]["distrito"] == "Cayma"


def test_grandes_portales_no_se_rastrean():
    db = FakeDB()
    db.upsert("fuentes", {"id": "u", "nombre": "U", "tipo": "ia", "activo": True, "urls": ["https://urbania.pe/x", "https://inmobiliaria-sur.pe/"]})
    assert rastreador.sitios(db) == ["inmobiliaria-sur.pe"]


def test_busqueda_gratis_cuando_google_no_tiene_cuota(monkeypatch):
    llm._SIN_BUSQUEDA_NATIVA.clear()
    monkeypatch.setattr(config, "BUSQUEDA_GOOGLE", "auto")
    llamadas = []

    def pedir(prompt, buscar, intentos):
        llamadas.append(buscar)
        if buscar:
            raise RuntimeError("Ninguna IA respondió: gemini: 429")
        if "búsquedas cortas" in prompt:
            return ["preventa cayma", "proyectos arequipa"]
        assert "torre-sol" in prompt
        return [{"nombre": "Torre Sol", "url": "https://constructora.pe/proyecto/torre-sol"}]

    monkeypatch.setattr(llm, "_pedir", pedir)
    monkeypatch.setattr(busqueda, "buscar_web", lambda c, n=8: [{"titulo": "Torre Sol", "url": "https://constructora.pe/proyecto/torre-sol", "resumen": "desde S/ 300 mil"}])
    monkeypatch.setattr(busqueda, "texto_pagina", lambda u, limite=4000: "Torre Sol en Cayma")
    assert llm.pedir_json("Busca proyectos", buscar=True)[0]["nombre"] == "Torre Sol"
    llm.pedir_json("Busca proyectos", buscar=True)
    assert llamadas.count(True) == 1
    llm._SIN_BUSQUEDA_NATIVA.clear()
