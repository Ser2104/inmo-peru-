import json
from datetime import date
from inmo.agents import oportunidades as o

hoy = date.today()
r = o.Navegador().get(o.ARCHIVO.format(y=hoy.year, m=hoy.month))
print("estado:", r.status_code, "bytes:", len(r.content), "inicio:", r.content[:4])
n = abiertas = 0
for paquete in o.paquetes(r.content):
    for rel in o.releases(paquete):
        n += 1
        if o.abierta(rel, hoy.isoformat()):
            abiertas += 1
            if abiertas <= 2:
                print("ejemplo:", json.dumps({k: rel.get(k) for k in ("ocid", "date", "tender", "parties")}, ensure_ascii=False)[:1500])
print("releases:", n, "abiertas:", abiertas)
