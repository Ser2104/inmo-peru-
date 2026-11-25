import json
from inmo.agents.oportunidades import API, Navegador

r = Navegador().get(API, params={"format": "json", "order": "desc"})
d = r.json()
print("claves:", list(d)[:10], "links:", d.get("links"))
rels = d.get("releases") or d.get("records") or []
print("cantidad:", len(rels))
for x in rels[:3]:
    print(json.dumps({k: x.get(k) for k in ("ocid", "date", "tag")}, ensure_ascii=False), "| tender:", json.dumps(x.get("tender"), ensure_ascii=False)[:500])
print("fechas:", [x.get("date") for x in rels][:20])
