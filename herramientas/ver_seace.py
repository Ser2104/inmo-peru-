import json
from inmo.agents.oportunidades import Navegador

r = Navegador().get("https://contratacionesabiertas.oece.gob.pe/api/v1/files", params={"page": 1, "paginateBy": 10, "format": "json"})
d = r.json()
print("paginacion:", d.get("pagination"))
for x in d.get("results", [])[:10]:
    print("archivo:", json.dumps(x, ensure_ascii=False)[:600])
