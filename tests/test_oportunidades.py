from inmo.agents import oportunidades
from tests.fake_db import FakeDB
from datetime import date, timedelta

HOY = date.today().isoformat()


def release(n, fecha=HOY, titulo="ALQUILER DE MAQUINARIA PESADA: EXCAVADORA Y VOLQUETES"):
    return {"ocid": f"ocds-dgv273-{n}", "date": f"{fecha}T10:00:00-05:00", "tag": ["tender"],
            "parties": [{"name": "MUNICIPALIDAD DISTRITAL DE CAYMA", "roles": ["buyer"], "address": {"region": "AREQUIPA", "locality": "CAYMA"},
                         "contactPoint": {"telephone": "054-123456", "email": "logistica@municayma.gob.pe"}}],
            "tender": {"title": titulo, "mainProcurementCategory": "services", "value": {"amount": 345000, "currency": "PEN"},
                       "datePublished": f"{fecha}T10:00:00-05:00", "items": [{"statusDetails": "CONVOCADO"}]}}


class Http:
    def __init__(self, contenido):
        self.contenido = contenido

    def get(self, url, params=None):
        return type("R", (), {"raise_for_status": lambda s: None, "content": self.contenido})()


def zip_de(paquete):
    import io, json, zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("2026-11.json", json.dumps(paquete))
    return b.getvalue()


def test_rubros():
    assert oportunidades.rubro("Alquiler de volquete de 15 m3") == "camiones y transporte"
    assert oportunidades.rubro("Adquisición de madera tornillo para encofrado") == "madera y aserradero"
    assert oportunidades.rubro("Servicio de mantenimiento correctivo de vehículos en taller") == "talleres y mantenimiento"
    assert oportunidades.rubro("ALQUILER DE MAQUINARIA: EXCAVADORA") == "maquinaria"


def test_seace_solo_guarda_convocatorias_abiertas():
    db = FakeDB()
    cerrada = release(3)
    cerrada["tender"]["items"] = [{"statusDetails": "ADJUDICADO"}]
    paquete = {"records": [{"ocid": "a", "compiledRelease": release(1)}, {"ocid": "b", "compiledRelease": release(2, titulo="Adquisición de madera aserrada")},
                           {"ocid": "c", "compiledRelease": cerrada}]}
    db.upsert("oportunidades", {"clave": "ya-cerrada", "fuente": "seace"})
    r = oportunidades.seace(db, {"tipo_cambio": 3.45}, http=Http(zip_de(paquete)))
    assert r["abiertas"] == 2 and r["nuevas"] == 2 and r["cerradas_quitadas"] == 1
    assert "ya-cerrada" not in {o["clave"] for o in db.t["oportunidades"]}
    o = db.t["oportunidades"][0]
    assert o["rubro"] == "maquinaria" and o["distrito"] == "Cayma" and abs(o["lat"] + 16.3625) < 0.01
    assert round(o["monto_usd"]) == 100000 and o["telefono"] == "054-123456" and o["url"].startswith("https://")


def test_banco_mundial_solo_vigentes():
    futuro = (date.today() + timedelta(days=10)).isoformat()
    datos = {"procnotices": [
        {"id": "OP1", "bid_description": "Alquiler de camiones cisterna", "project_name": "Agua para Arequipa", "submission_deadline_date": futuro + "T00:00:00Z", "contact_city": "Arequipa"},
        {"id": "OP2", "bid_description": "Consultoría", "submission_deadline_date": "2020-01-01T00:00:00Z"}]}
    http = type("H", (), {"get": lambda self, *a, **k: type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: datos})()})()
    db = FakeDB()
    assert oportunidades.banco_mundial(db, {"tipo_cambio": 3.45}, http=http)["vigentes"] == 1
    o = db.t["oportunidades"][0]
    assert o["rubro"] == "camiones y transporte" and o["departamento"] == "Arequipa" and o["fecha_limite"] == futuro
