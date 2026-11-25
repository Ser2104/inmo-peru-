from collections import Counter
from datetime import date
from inmo.agents import oportunidades as o

hoy = date.today().isoformat()
r = o.Navegador().get(o.ARCHIVO.format(y=date.today().year, m=date.today().month))
c, fin = Counter(), Counter()
for paquete in o.paquetes(r.content):
    for rel in o.releases(paquete):
        t = rel.get("tender") or {}
        estados = ",".join(sorted({str(i.get("statusDetails")) for i in t.get("items") or []}))[:40]
        aw = ",".join(sorted({str(a.get("status")) for a in rel.get("awards") or []}))
        f = ((t.get("tenderPeriod") or {}).get("endDate") or "")[:10]
        c[(t.get("procurementMethodDetails"), t.get("status"), estados, aw)] += 1
        fin["futuro" if f >= hoy else "pasado" if f else "sin_fecha"] += 1
for k, v in c.most_common(25):
    print("conteo:", v, k)
print("fechas:", fin)
