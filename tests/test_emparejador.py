from inmo import llm
from inmo.agents import emparejador
from tests.fake_db import FakeDB


def preparar():
    db = FakeDB()
    db.upsert("perfiles", {"id": "principal", "descripcion": "Tengo 7 camionetas", "version": 1, "departamentos": None})
    db.upsert("oportunidades", [
        {"clave": "a", "titulo": "Alquiler de camionetas 4x4 con conductor", "departamento": "Arequipa", "url": "https://prod1.seace.gob.pe/a.pdf"},
        {"clave": "b", "titulo": "Adquisición de camionetas", "departamento": "Lima", "url": "https://prod1.seace.gob.pe/b.pdf"},
    ])
    return db


def test_evalua_y_no_repite(monkeypatch):
    db = preparar()
    ids = {o["clave"]: o["id"] for o in db.t["oportunidades"]}
    llamadas = []

    def falso(prompt, **k):
        llamadas.append(prompt)
        if "lista JSON de 30 a 60" in prompt:
            return ["camioneta", "vehiculo"]
        return [{"id": ids["a"], "encaja": True, "puntaje": 90, "razon": "Piden alquiler de camionetas", "que_piden": "3 camionetas 6 meses"},
                {"id": ids["b"], "encaja": False, "puntaje": 5, "razon": "Quieren comprar, no alquilar"}]
    monkeypatch.setattr(llm, "disponible", lambda: True)
    monkeypatch.setattr(llm, "pedir_json", falso)
    db.upsert("oportunidades", {"clave": "c", "titulo": "Compra de útiles de oficina", "departamento": "Lima"})
    r = emparejador.evaluar(db)
    assert r == {"evaluadas_con_ia": 2, "descartadas_sin_ia": 1, "encajan": 1}
    assert emparejador.evaluar(db)["evaluadas_con_ia"] == 0 and len(llamadas) == 2
    db.t["perfiles"][0]["version"] = 2
    assert emparejador.evaluar(db)["evaluadas_con_ia"] == 2


def test_bases_corrigen_y_ponen_fecha(monkeypatch):
    db = preparar()
    a = next(o for o in db.t["oportunidades"] if o["clave"] == "a")
    db.upsert("coincidencias", {"oportunidad_id": a["id"], "perfil_id": "principal", "version": 1, "encaja": True, "puntaje": 90, "bases_leidas": False})
    monkeypatch.setattr(llm, "disponible", lambda: True)
    monkeypatch.setattr(llm, "pedir_json", lambda prompt, **k: {"fecha_limite": "2030-01-15", "cantidad": "3", "antiguedad_maxima": 2, "cumple": False, "por_que": "Piden camionetas de máximo 2 años"})
    assert emparejador.leer_bases(db, descargar=lambda url: "<pdf>" + "requisitos camioneta servicio " * 40)["bases_leidas"] == 1
    c = db.t["coincidencias"][0]
    assert c["encaja"] is False and "2 años" in c["razon"] and c["bases_leidas"] is True
    assert a["fecha_limite"] == "2030-01-15"


def test_bases_ilegibles_no_descartan(monkeypatch):
    db = preparar()
    a = next(o for o in db.t["oportunidades"] if o["clave"] == "a")
    db.upsert("coincidencias", {"oportunidad_id": a["id"], "perfil_id": "principal", "version": 1, "encaja": True, "puntaje": 90, "bases_leidas": False})
    monkeypatch.setattr(llm, "disponible", lambda: True)
    emparejador.leer_bases(db, descargar=lambda url: "<pdf>")
    c = db.t["coincidencias"][0]
    assert c["encaja"] is True and c["requisitos"]["no_legible"]
