from html import escape


def _pct(x):
    return "—" if x is None else f"{x * 100:.1f}%"


def _usd(x):
    return "—" if x is None else f"US$ {x:,.0f}"


def _comparacion(c, elegida):
    if not c or not c.get("temporal"):
        return ""
    l, t = c["largo_plazo"], c["temporal"]
    fila = lambda n, k, f: f"<tr><td>{n}</td><td>{f(l.get(k))}</td><td>{f(t.get(k))}</td></tr>"
    marca = lambda e: " ✅" if elegida == e else ""
    return (f"<h2>Alquiler tradicional vs. por días (Airbnb)</h2><table><tr><th></th><th>Tradicional{marca('largo_plazo')}</th><th>Por días{marca('temporal')}</th></tr>"
            + fila("Ingreso bruto anual", "ingreso_bruto_anual", _usd) + fila("Flujo mensual", "flujo_mensual_usd", _usd)
            + fila("Rentabilidad neta", "rentabilidad_neta", _pct) + fila("TIR 5 años", "tir_5", _pct) + fila("TIR 10 años", "tir_10", _pct)
            + f"</table><p>Por días: tarifa US$ {t['adr_usd']:,.0f}/noche, ocupación {t['ocupacion'] * 100:.0f}% (datos a nivel de {escape(str(t['nivel']))}), "
            f"amoblado US$ {t['amoblado_usd']:,.0f}. Regulación del distrito: {escape(str(c.get('regulacion')))}.</p>")


def html(inm, a):
    d = a.get("detalle") or {}
    esc = d.get("escenarios", {})
    filas_esc = "".join(
        f"<tr><td>{n.title()}</td><td>{_pct(e.get('tir_2'))}</td><td>{_pct(e.get('tir_5'))}</td><td>{_pct(e.get('tir_10'))}</td><td>{_usd(e.get('van_10'))}</td><td>{_usd(e.get('flujo_mensual_usd'))}</td></tr>"
        for n, e in esc.items()
    )
    flujos = "".join(f"<tr><td>Año {t}</td><td>{_usd(f)}</td></tr>" for t, f in enumerate(d.get("flujos_10", [])))
    riesgos = "".join(f"<li>{escape(r)}</li>" for r in a.get("riesgos") or []) or "<li>Sin alertas importantes</li>"
    color = {"Comprar": "#1a7f37", "Negociar": "#b58100", "Descartar": "#c62828"}.get(a["veredicto"], "#555")
    z = d.get("zona_venta") or {}
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reporte — {escape(inm.get('titulo') or '')}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:860px;margin:auto;padding:16px;color:#1d1d1f}}
table{{border-collapse:collapse;width:100%;margin:8px 0 20px}}td,th{{border-bottom:1px solid #e5e5e5;padding:6px;text-align:left}}
.v{{display:inline-block;padding:6px 14px;border-radius:8px;color:#fff;background:{color};font-weight:600}}
.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}.c{{background:#f5f5f7;border-radius:10px;padding:10px}}
.c b{{display:block;font-size:1.3em}}</style></head><body>
<h1>{escape(inm.get('titulo') or 'Inmueble')}</h1>
<p>{escape(str(inm.get('tipo') or ''))} · {escape(str(inm.get('estado') or ''))} · {escape(str(inm.get('distrito') or ''))}, {escape(str(inm.get('provincia') or ''))}, {escape(str(inm.get('departamento') or ''))} · <a href="{escape(inm.get('url') or '')}">ver aviso</a></p>
<p><span class="v">{a['veredicto']}</span> &nbsp; Puntaje {a['puntaje_total']}/10 · confianza {a['confianza']}</p>
<div class="g">
<div class="c">Corto plazo<b>{a['puntaje_corto']}</b></div><div class="c">Mediano plazo<b>{a['puntaje_mediano']}</b></div><div class="c">Largo plazo<b>{a['puntaje_largo']}</b></div>
<div class="c">Precio<b>{_usd(a['precio_usd'])}</b></div><div class="c">Precio máx. recomendado<b>{_usd(a['precio_max_recomendado'])}</b></div>
<div class="c">Alquiler estimado<b>{_usd(a['renta_mensual_usd'])}/mes</b></div><div class="c">Rentabilidad neta<b>{_pct(a['rentabilidad_neta'])}</b></div>
<div class="c">Flujo mensual<b>{_usd(a['flujo_mensual_usd'])}</b></div><div class="c">Vs. precio de la zona<b>{_pct(a['descuento_vs_zona'])} {'más barato' if (a['descuento_vs_zona'] or 0) > 0 else 'más caro'}</b></div>
</div>
{_comparacion(d.get("comparacion"), a.get("estrategia"))}
<h2>Riesgos</h2><ul>{riesgos}</ul>
<h2>Escenarios</h2><table><tr><th></th><th>TIR 2 años</th><th>TIR 5 años</th><th>TIR 10 años</th><th>VAN 10 años</th><th>Flujo mensual</th></tr>{filas_esc}</table>
<h2>Datos usados</h2><table>
<tr><td>Inversión inicial (con gastos de compra)</td><td>{_usd(d.get('inversion_inicial'))}</td></tr>
<tr><td>Gastos de compra (alcabala, notaría, registro)</td><td>{_usd(d.get('costos_compra'))}</td></tr>
<tr><td>Cuota de hipoteca</td><td>{_usd(d.get('cuota_hipoteca_mensual'))}</td></tr>
<tr><td>Origen del alquiler estimado</td><td>{escape(a.get('fuente_renta') or '')} ({d.get('comparables_alquiler', 0)} alquileres comparables)</td></tr>
<tr><td>Precio mediano de la zona ({escape(str(d.get('nivel_zona_venta') or '—'))})</td><td>{_usd(z.get('mediana_m2_usd'))}/m² · {z.get('n', 0)} avisos</td></tr>
<tr><td>Plusvalía anual usada</td><td>{_pct(d.get('plusvalia_usada'))}</td></tr>
<tr><td>Meses hasta empezar a alquilar</td><td>{d.get('meses_hasta_renta', 0)}</td></tr>
</table>
<h2>Flujo de caja (10 años, incluye venta al final)</h2><table>{flujos}</table>
<p style="color:#777;font-size:.85em">Estimación automática con datos públicos. No es asesoría financiera: verifica partida registral (SUNARP), deudas y estado físico antes de comprar.</p>
</body></html>"""
