from collections import Counter
from datetime import date
from inmo.agents import oportunidades as o

hoy = date.today().isoformat()
r = o.Navegador().get(o.ARCHIVO.format(y=date.today().year, m=date.today().month))
n = 0
c = Counter()
for paquete in o.paquetes(r.content):
    for rel in o.releases(paquete):
        t = rel.get("tender") or {}
        if "CONVOCADO" not in {str(i.get("statusDetails")).upper() for i in t.get("items") or []} or t.get("procurementMethod") == "direct":
            continue
        fechas = {k: (t.get(k) or {}) for k in ("tenderPeriod", "enquiryPeriod", "awardPeriod", "contractPeriod")}
        for k, v in fechas.items():
            fin = str(v.get("endDate") or "")[:10]
            c[(k, "futuro" if fin >= hoy else "pasado" if fin else "sin")] += 1
        n += 1
        if n <= 4:
            print("muestra:", t.get("datePublished"), {k: (v.get("startDate"), v.get("endDate")) for k, v in fechas.items()}, "docs:", [(d.get("documentType"), d.get("title"), d.get("datePublished")) for d in (t.get("documents") or [])][:3])
print("conteo:", dict(c), "convocados:", n)
