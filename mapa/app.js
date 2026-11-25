const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const usd = (x) => (x == null ? "—" : "US$ " + Math.round(x).toLocaleString("es-PE"));
const pct = (x) => (x == null ? "—" : (x * 100).toFixed(1) + "%");
const COLOR = { verde: "#1a7f37", ambar: "#c78a00", rojo: "#c62828", gris: "#6b7280" };
const DEMO = new URLSearchParams(location.search).has("demo");

const estado = { sinExp: false, paraMi: true, capa: "inversion", horizonte: "total", veredictos: new Set(["Comprar", "Negociar", "Revisar a mano", "Descartar"]), zonas: false };
let inmuebles = [], arbitrajes = [], negocios = [], oportunidades = [], sb = null;

const PERU = L.latLngBounds([-18.6, -81.6], [0.2, -68.4]);
const mapa = L.map("mapa", { zoomControl: false, maxBounds: PERU.pad(0.15), maxBoundsViscosity: 1, minZoom: 5 }).fitBounds(PERU);
L.control.zoom({ position: "bottomright" }).addTo(mapa);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa);
fetch("peru.json").then((r) => r.json()).then((peru) => {
  const mundo = [[-90, -180], [-90, 180], [90, 180], [90, -180]];
  const anillos = peru.type === "MultiPolygon" ? peru.coordinates.map((p) => p[0]) : [peru.coordinates[0]];
  L.polygon([mundo, ...anillos.map((a) => a.map(([lng, lat]) => [lat, lng]))], { stroke: false, fillColor: "#fff", fillOpacity: 0.75, interactive: false }).addTo(mapa);
  L.polygon(anillos.map((a) => a.map(([lng, lat]) => [lat, lng])), { color: "#2563eb", weight: 1.5, fill: false, interactive: false }).addTo(mapa);
}).catch(() => {});
const grupo = L.markerClusterGroup({
  showCoverageOnHover: false, maxClusterRadius: 45,
  iconCreateFunction: (c) => {
    const hijos = c.getAllChildMarkers();
    const mejor = hijos.reduce((m, h) => Math.max(m, h.options.nivel ?? 0), 0);
    const fondo = [COLOR.rojo, COLOR.ambar, COLOR.verde][mejor];
    return L.divIcon({ className: "", html: `<div class="punto" style="width:34px;height:34px;font-size:12px;background:${fondo}">${hijos.length}</div>`, iconSize: [34, 34] });
  },
});
const capaZonas = L.layerGroup();
mapa.addLayer(grupo);

function puntaje(i) {
  if (estado.capa !== "inversion") return i.puntaje;
  return estado.horizonte === "total" ? i.puntaje_total : i["puntaje_" + estado.horizonte];
}

function color(p) {
  if (p == null) return COLOR.gris;
  return p >= 7.5 ? COLOR.verde : p >= 6 ? COLOR.ambar : COLOR.rojo;
}

const dias = (f) => f ? Math.ceil((new Date(f + "T23:59:00") - new Date()) / 864e5) : null;
const colorOportunidad = (i) => { const d = dias(i.fecha_limite); return d == null ? COLOR.gris : d > 7 ? COLOR.verde : d >= 2 ? COLOR.ambar : COLOR.rojo; };
const PORTALES = /^(urbania|adondevivir|properati|nexoinmobiliario|infocasas|casas-trovit|casas-mitula|nuroa|doomos|ubicasa)/;
const REMATES = /^(bbva|remaju|rematesya|rematestributarios|propiedadesenremate|precioderemate)/;
const origen = (i) => REMATES.test(i.fuente || "") || i.estado === "remate" ? "remates" : PORTALES.test(i.fuente || "") ? "portales" : "independientes";
const COLOR_VEREDICTO = { "Atractivo": COLOR.verde, "Falta información": COLOR.gris, "Fuera de escala": COLOR.gris, "Comprar": COLOR.verde, "Buena oportunidad": COLOR.verde, "Negociar": COLOR.ambar, "Evaluar": COLOR.ambar, "Revisar a mano": COLOR.ambar };
const nivelDe = (i) => [COLOR.rojo, COLOR.ambar, COLOR.verde].indexOf(colorDe(i));
const colorDe = (i) => estado.capa === "oportunidades" ? colorOportunidad(i) : estado.horizonte === "total" || estado.capa !== "inversion" ? (COLOR_VEREDICTO[i.veredicto] ?? COLOR.rojo) : color(puntaje(i));

function icono(i) {
  const letra = estado.capa === "oportunidades" ? ({ seace: "E", banco_mundial: "I" }[i.fuente] || "P") : estado.capa === "negocios" ? { traspaso: "T", local: "C", estado: "E" }[i.tipo] : estado.capa === "arbitraje" ? "A" : i.estado === "remate" ? "R" : i.estrategia === "temporal" ? "D" : i.estado === "preventa" || i.estado === "en_planos" ? "P" : "";
  return L.divIcon({ className: "", html: `<div class="punto" style="background:${colorDe(i)}">${letra}</div>`, iconSize: [18, 18] });
}

function filtrados() {
  const dep = $("f-dep").value, dist = $("f-dist").value, min = +$("f-puntaje").value;
  const precio = +$("f-precio").value || Infinity;
  if (estado.capa === "oportunidades") {
    const r = $("f-rubro").value;
    return oportunidades.filter((i) => (!estado.paraMi || i.encaja) && (!estado.sinExp || i.requisitos?.sin_experiencia === true) && (!dep || i.departamento === dep) && (!dist || i.distrito === dist) && (!r || i.rubro === r) && (i.monto_usd ?? 0) <= precio);
  }
  if (estado.capa === "negocios") {
    const t = $("f-negocio").value;
    return negocios.filter((i) => (!dep || i.departamento === dep) && (!dist || i.distrito === dist) && (!t || i.tipo === t) && (i.puntaje ?? 0) >= min && (i.inversion_usd ?? 0) <= precio);
  }
  if (estado.capa === "arbitraje") {
    return arbitrajes.filter((i) => (!dep || i.departamento === dep) && (!dist || i.distrito === dist) && (i.puntaje ?? 0) >= min);
  }
  const est = $("f-estrategia").value, tipo = $("f-tipo").value, sit = $("f-estado").value, org = $("f-origen").value;
  return inmuebles.filter((i) =>
    estado.veredictos.has(i.veredicto) && (!dep || i.departamento === dep) && (!dist || i.distrito === dist) &&
    (!est || i.estrategia === est) && (!org || origen(i) === org) && (!tipo || i.tipo === tipo) && (!sit || i.estado === sit) &&
    (i.precio_usd ?? 0) <= precio && (puntaje(i) ?? 0) >= min);
}

function dibujar() {
  const lista = filtrados();
  grupo.clearLayers();
  grupo.addLayers(lista.map((i) => L.marker([i.lat, i.lng], { icon: icono(i), nivel: Math.max(0, nivelDe(i)) }).on("click", () => abrir(i))));
  $("contador").textContent = `${lista.length.toLocaleString("es-PE")} ${{ negocios: "negocios", oportunidades: "oportunidades" }[estado.capa] || "inmuebles"}`;
  dibujarZonas(lista);
  dibujarLista(lista);
  $("leyenda").innerHTML = estado.capa === "oportunidades"
    ? `<span style="background:${COLOR.verde}"></span>Más de 7 días para postular<br><span style="background:${COLOR.ambar}"></span>2 a 7 días<br><span style="background:${COLOR.rojo}"></span>Vence ya<br><span style="background:${COLOR.gris}"></span>Estado: revisa el cronograma en el SEACE<br>E = Estado · I = Banco Mundial · P = empresa privada u otra fuente`
    : estado.capa === "negocios"
    ? `<span style="background:${COLOR.verde}"></span>Atractivo<br><span style="background:${COLOR.ambar}"></span>Negociar / revisar<br><span style="background:${COLOR.rojo}"></span>Descartar<br><span style="background:${COLOR.gris}"></span>Falta información<br>T = traspaso · C = concesión · E = Estado`
    : estado.capa === "arbitraje"
    ? `<span style="background:${COLOR.verde}"></span>Buena oportunidad<br><span style="background:${COLOR.ambar}"></span>Evaluar<br><span style="background:${COLOR.rojo}"></span>No conviene`
    : `<span style="background:${COLOR.verde}"></span>Comprar<br><span style="background:${COLOR.ambar}"></span>Negociar<br><span style="background:${COLOR.rojo}"></span>Descartar<br>D = mejor por días · R = remate · P = preventa`;
}

function dibujarZonas(lista) {
  capaZonas.clearLayers();
  if (!estado.zonas) return;
  const grupos = {};
  for (const i of lista) (grupos[`${i.departamento}|${i.distrito}`] ??= []).push(i);
  for (const [clave, g] of Object.entries(grupos)) {
    const lat = g.reduce((s, i) => s + i.lat, 0) / g.length, lng = g.reduce((s, i) => s + i.lng, 0) / g.length;
    const ps = g.map(puntaje).filter((x) => x != null).sort((a, b) => a - b);
    const med = ps.length ? ps[Math.floor(ps.length / 2)] : null;
    const rent = g.map((i) => i.rentabilidad_neta).filter((x) => x != null).sort((a, b) => a - b);
    L.circle([lat, lng], { radius: 400 + Math.sqrt(g.length) * 150, color: color(med), fillOpacity: 0.25, weight: 1 })
      .bindPopup(`<b>${esc(clave.split("|")[1] || "Sin distrito")}</b><br>${g.length} inmuebles<br>Puntaje mediano: ${med?.toFixed(1) ?? "—"}` +
        (estado.capa === "inversion" ? `<br>Rentabilidad neta mediana: ${pct(rent[Math.floor(rent.length / 2)])}<br>Mejores por días: ${g.filter((i) => i.estrategia === "temporal").length}` : ""))
      .addTo(capaZonas);
  }
}

function dibujarLista(lista) {
  const op = estado.capa === "oportunidades";
  const top = [...lista].sort((a, b) => op ? ((b.puntaje_perfil ?? 0) - (a.puntaje_perfil ?? 0)) || ((b.monto_usd ?? 0) - (a.monto_usd ?? 0)) : (puntaje(b) ?? 0) - (puntaje(a) ?? 0)).slice(0, 30);
  $("items").innerHTML = top.map((i, n) => `<div class="item" data-n="${n}"><b style="color:${colorDe(i)}">${op ? "💼" : (puntaje(i) ?? 0).toFixed(1)}</b> · ${esc((i.titulo || i.nombre || i.tipo || "Inmueble").slice(0, 120))}<br>
    <span class="sub">${esc(i.distrito || "")}, ${esc(i.departamento || "")} · ${estado.capa === "oportunidades" ? esc(i.rubro) + " · " + (i.monto_usd ? usd(i.monto_usd) : "monto no indicado") + (i.fecha_limite ? " · vence " + i.fecha_limite : "") : estado.capa === "negocios" ? esc(i.veredicto) + " · " + usd(i.inversion_usd) : estado.capa === "arbitraje" ? usd(i.utilidad_mensual_usd) + "/mes de ganancia" : usd(i.precio_usd)}</span></div>`).join("") || '<p class="sub">No hay inmuebles con estos filtros.</p>';
  $("items").querySelectorAll(".item").forEach((el) => el.onclick = () => { const i = top[+el.dataset.n]; mapa.setView([i.lat, i.lng], 16); abrir(i); });
}

function barra(nombre, valor) {
  return `<div><small>${nombre}</small><div class="barra-p"><i style="width:${(valor ?? 0) * 10}%;background:${color(valor)}"></i></div><b>${valor?.toFixed(1) ?? "—"}</b></div>`;
}

function encabezado(i, veredicto, colorV) {
  return `<h2>${esc(i.titulo || i.tipo || "Inmueble")}</h2>
    <p class="sub">${esc([i.tipo, i.estado, i.dormitorios ? i.dormitorios + " dorm." : "", i.area_m2 ? Math.round(i.area_m2) + " m²" : ""].filter(Boolean).join(" · "))}<br>${esc(i.distrito || "")}, ${esc(i.provincia || "")}, ${esc(i.departamento || "")}</p>
    <span class="veredicto" style="background:${colorV}">${esc(veredicto)}</span>`;
}

const dominio = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return null; } };

function fuente(i, mensajeWa) {
  const links = [i.url, i.mencionado_en].filter((u) => u && u.startsWith("http"));
  const partes = links.map((u, n) => `<a class="btn" href="${esc(u.split("#")[0])}" target="_blank" rel="noopener">${n ? "Donde se mencionó" : "Ver en"} ${esc(dominio(u))} →</a>`);
  if (i.telefono) partes.push(`<a class="btn" href="https://wa.me/${esc(i.telefono)}?text=${encodeURIComponent(mensajeWa || "Hola, vi su aviso y me interesa. ¿Sigue disponible?")}" target="_blank" rel="noopener">WhatsApp +${esc(i.telefono)}</a>`);
  const quien = [i.entidad, i.constructora].filter(Boolean).map(esc).join(" · ");
  return `<h3>Fuente y contacto</h3><p class="sub">${quien ? quien + "<br>" : ""}Datos tomados de ${esc(links.map(dominio).join(" y ") || "WhatsApp")}. Confirma precio y disponibilidad directamente.</p><div class="fila">${partes.join(" ") || '<span class="sub">Sin enlace: usa 📞 Contactar.</span>'}</div>`;
}

const RUBRO = { cafeteria: "Cafetería", restaurante: "Restaurante", comida_rapida: "Comida rápida", bodega: "Bodega", minimarket: "Minimarket", farmacia: "Farmacia", libreria: "Librería", fotocopiadora: "Fotocopiadora", gimnasio: "Gimnasio", lavanderia: "Lavandería", estacionamiento: "Estacionamiento", quiosco: "Quiosco", hospedaje: "Hospedaje", salon_belleza: "Salón de belleza", otro: "Otro" };

function zona(e, titulo) {
  if (!e) return "";
  return `<h3>${titulo}</h3><p class="sub">A ${e.radio_m} m: ${esc(e.cerca.join(", ") || "poca actividad")}${e.rubro !== "otro" ? ` · ${e.competidores} competidores directos` : ""}.</p>
    ${e.rubro !== "otro" ? barra("Ubicación para " + (RUBRO[e.rubro] || e.rubro).toLowerCase(), e.puntaje) : ""}
    <p class="sub">Mejores negocios para este punto: ${e.mejores_rubros.map(([r, p]) => `<b>${esc(RUBRO[r] || r)}</b> ${p}/10`).join(" · ")}</p>`;
}

async function abrir(i) {
  const p = $("contenido");
  const aprox = i.ubicacion_precision === "distrito" ? '<div class="aviso">📍 Ubicación aproximada: el aviso no trae dirección exacta, se muestra en su distrito.</div>' : "";
  const enlace = fuente(i, estado.capa === "negocios" ? mensajeNegocio(i) : null);
  if (estado.capa === "oportunidades") {
    const d = dias(i.fecha_limite);
    p.innerHTML = `<h2>${esc(i.titulo)}</h2><p class="sub">${esc([i.rubro, i.categoria, i.metodo].filter(Boolean).join(" · "))}<br>${esc([i.distrito, i.provincia, i.departamento].filter(Boolean).join(", "))}</p>
      <span class="veredicto" style="background:${colorOportunidad(i)}">${d == null ? (i.fuente === "seace" ? "Convocado el " + (i.fecha_publicacion || "—") : "Sin fecha límite") : d < 0 ? "Vencida" : d === 0 ? "Vence hoy" : `Quedan ${d} días`}</span>
      <div class="grid"><div class="dato"><small>Quién lo pide</small><b>${esc(i.entidad || "—")}</b></div>
      <div class="dato"><small>Monto referencial</small><b>${usd(i.monto_usd)}</b></div>
      <div class="dato"><small>Publicado</small><b>${esc(i.fecha_publicacion || "—")}</b></div>
      <div class="dato"><small>Fecha límite</small><b>${esc(i.fecha_limite || "—")}</b></div></div>
      ${paraTi(i)}${itemsTabla(i)}<p>${esc(i.descripcion || "")}</p>
      ${i.fuente === "seace" ? `<p class="sub">Compra del Estado en etapa de convocatoria. Para ver bases y cronograma, busca el código <b>${esc((i.metodo || "").split(" · ")[1] || "")}</b> en el <a href="https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml" target="_blank" rel="noopener">buscador del SEACE</a>. Para postular necesitas estar inscrito en el Registro Nacional de Proveedores (RNP).</p>` : '<p class="sub">' + (i.fuente === "banco_mundial" ? "Licitación financiada por el Banco Mundial: revisa requisitos y documentos en el enlace." : "Pedido encontrado en internet: confirma con ellos que siga vigente.") + '</p>'}
      ${i.correo ? `<p class="sub">Correo: <a href="mailto:${esc(i.correo)}">${esc(i.correo)}</a></p>` : ""}${i.web ? `<p class="sub">Web: <a href="${esc(i.web)}" target="_blank" rel="noopener">${esc(i.web)}</a></p>` : ""}
      <div class="aviso">📍 Ubicación aproximada: se muestra en la ciudad de quien lo pide.</div>${fuente({ url: i.url, telefono: /^51\d{9}$/.test(i.telefono || "") ? i.telefono : null, entidad: i.entidad }, "Hola, vi su convocatoria y me interesa ofrecer el servicio. ¿Sigue vigente?")}${i.telefono && !/^51\d{9}$/.test(i.telefono) ? `<p class="sub">Teléfono: ${esc(i.telefono)}</p>` : ""}`;
    abrirPanel("detalle");
    return;
  }
  if (estado.capa === "negocios") {
    const d = i.detalle || {}, tipo = { traspaso: "Traspaso de negocio", local: "Concesión de local", estado: "Proyecto del Estado" }[i.tipo];
    p.innerHTML = `<h2>${esc(i.nombre || tipo)}</h2><p class="sub">${esc([tipo, i.rubro, i.entidad, i.area_m2 ? Math.round(i.area_m2) + " m²" : ""].filter(Boolean).join(" · "))}<br>${esc([i.distrito, i.provincia, i.departamento].filter(Boolean).join(", "))}</p>
      <span class="veredicto" style="background:${COLOR_VEREDICTO[i.veredicto] ?? COLOR.rojo}">${esc(i.veredicto || "Sin analizar")}</span>
      <div class="grid"><div class="dato"><small>${i.tipo === "estado" ? "Inversión del proyecto" : "Inversión inicial"}</small><b>${usd(i.inversion_usd)}</b></div>
      <div class="dato"><small>Canon o alquiler</small><b>${i.canon_mensual_usd ? usd(i.canon_mensual_usd) + "/mes" : "—"}</b></div>
      <div class="dato"><small>Ventas al mes</small><b>${usd(i.ventas_mensuales_usd)}</b></div>
      <div class="dato"><small>Te quedaría al mes</small><b>${usd(i.utilidad_mensual_usd)}</b></div>
      <div class="dato"><small>Ganancia anual</small><b>${pct(i.tir_anual)}</b></div>
      <div class="dato"><small>Recuperas la inversión en</small><b>${i.payback_meses ? i.payback_meses + " meses" : "—"}</b></div>
      <div class="dato"><small>Duración del contrato</small><b>${i.plazo_meses ? i.plazo_meses + " meses" : "—"}</b></div>
      <div class="dato"><small>${i.tipo === "estado" ? "Etapa" : "Fecha límite"}</small><b>${esc(i.tipo === "estado" ? i.etapa || "—" : i.fecha_limite || "—")}</b></div></div>
      ${d.van_pesimista_usd != null ? `<p class="sub">Si vendes 20% menos: ganancia anual ${pct(d.tir_pesimista)}. Se exige al menos ${pct(d.tasa_exigida)} al año por el riesgo de un negocio.</p>` : ""}
      ${zona(i.entorno, "¿Es un punto estratégico?")}${i.ubicacion_precision === "lugar" ? "" : '<div class="aviso">📍 Ubicación aproximada: aún no se pudo evaluar la zona exacta.</div>'}
      <p>${esc(i.descripcion || "")}</p><h3>Ten en cuenta</h3><ul>${(i.riesgos || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      ${enlace}`;
    abrirPanel("detalle");
    return;
  }
  if (estado.capa === "arbitraje") {
    p.innerHTML = encabezado(i, i.veredicto, COLOR_VEREDICTO[i.veredicto] ?? COLOR.rojo) + `
      <p class="sub" style="margin-top:10px">Idea: alquilas este departamento a largo plazo, lo amoblas y lo alquilas por días.</p>
      <div class="grid"><div class="dato"><small>Pagas de alquiler</small><b>${usd(i.renta_usd)}/mes</b></div>
      <div class="dato"><small>Cobrarías por días</small><b>${usd(i.ingreso_temporal_mensual_usd)}/mes</b></div>
      <div class="dato"><small>Te quedaría</small><b>${usd(i.utilidad_mensual_usd)}/mes</b></div>
      <div class="dato"><small>Recuperas el amoblado en</small><b>${i.payback_meses ? i.payback_meses + " meses" : "—"}</b></div></div>
      <h3>Ten en cuenta</h3><ul>${(i.riesgos || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>${aprox}${enlace}`;
    abrirPanel("detalle");
    return;
  }
  const porDias = i.estrategia === "temporal";
  p.innerHTML = encabezado(i, i.veredicto, COLOR_VEREDICTO[i.veredicto] ?? COLOR.rojo) + `
    <span class="sub"> &nbsp;${i.puntaje_total == null ? "Puntaje no confiable: datos del aviso dudosos" : `Puntaje ${i.puntaje_total.toFixed(1)}/10 · confianza ${esc(i.confianza)}`}</span>
    <div class="plazos">${barra("Corto plazo", i.puntaje_corto)}${barra("Mediano plazo", i.puntaje_mediano)}${barra("Largo plazo", i.puntaje_largo)}</div>
    <div class="grid">
      <div class="dato"><small>Precio</small><b>${usd(i.precio_usd)}</b></div>
      <div class="dato"><small>Te conviene pagar hasta</small><b>${usd(i.precio_max_recomendado)}</b></div>
      <div class="dato"><small>Mejor forma de alquilar</small><b>${porDias ? "Airbnb 🏖️" : "Largo plazo 🏠"}</b></div>
      <div class="dato"><small>Te quedaría al mes</small><b>${usd(porDias ? i.flujo_mensual_temporal : i.flujo_mensual_usd)}</b></div>
      <div class="dato"><small>Ganancia anual (10 años)</small><b>${pct(porDias ? i.tir_10_temporal : i.tir_10)}</b></div>
      <div class="dato"><small>Frente a su zona</small><b>${i.descuento_vs_zona == null ? "—" : Math.abs(i.descuento_vs_zona * 100).toFixed(0) + "% " + (i.descuento_vs_zona > 0 ? "más barato" : "más caro")}</b></div>
    </div>${confirmacion(i)}${aprox}${i.tipo === "local" ? zona(i.entorno, "¿Para qué negocio sirve este local?") : ""}<div id="extra"><p class="sub" style="margin-top:14px">Cargando análisis completo…</p></div>${enlace}`;
  abrirPanel("detalle");
  const a = DEMO ? i._analisis : (await sb.from("analisis").select("riesgos,detalle,renta_mensual_usd").eq("inmueble_id", i.id).single()).data;
  $("extra").innerHTML = a ? completo(a) : "";
}

function confirmacion(i) {
  if (!i.confirmacion) return i.veredicto === "Comprar" ? '<div class="aviso">⏳ Aún no se confirmó el aviso. Se revisa en el próximo ciclo.</div>' : "";
  const fecha = new Date(i.confirmado).toLocaleDateString("es-PE");
  return { ok: `<div class="aviso" style="background:#e7f5ec">✅ Confirmado el ${fecha}: el aviso sigue publicado y el precio coincide.</div>`,
    precio_cambio: `<div class="aviso">⚠️ Revisado el ${fecha}: el precio del aviso cambió.</div>`,
    no_verificable: `<div class="aviso">⚠️ Revisado el ${fecha}: no se pudo abrir el aviso; confírmalo tú.</div>`,
    no_disponible: `<div class="aviso">❌ Revisado el ${fecha}: el aviso ya no está publicado.</div>` }[i.confirmacion] || "";
}

function listaParecidos(titulo, lista, alquiler) {
  if (!lista?.length) return "";
  return `<h3>${titulo}</h3><table><tr><th>Precio</th><th>Área</th><th>Dorm.</th><th></th></tr>${lista.map((x) => `<tr><td>${usd(x.precio_usd)}${alquiler ? "/mes" : ""}</td><td>${Math.round(x.area_m2)} m²</td><td>${x.dormitorios ?? "—"}</td><td>${x.url?.startsWith("http") ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(dominio(x.url))}</a>` : ""}</td></tr>`).join("")}</table>`;
}

function completo(a) {
  const d = a.detalle || {}, c = d.comparacion || {}, e = d.escenarios || {};
  const comp = c.temporal ? `<h3>Largo plazo vs. Airbnb</h3><table><tr><th></th><th>Largo plazo</th><th>Airbnb</th></tr>
    <tr><td>Cobras al año</td><td>${usd(c.largo_plazo.ingreso_bruto_anual)}</td><td>${usd(c.temporal.ingreso_bruto_anual)}</td></tr>
    <tr><td>Te queda al mes</td><td>${usd(c.largo_plazo.flujo_mensual_usd)}</td><td>${usd(c.temporal.flujo_mensual_usd)}</td></tr>
    <tr><td>Ganancia anual (10 años)</td><td>${pct(c.largo_plazo.tir_10)}</td><td>${pct(c.temporal.tir_10)}</td></tr></table>
    <p class="sub">Por días: ${usd(c.temporal.adr_usd)} la noche, ${Math.round(c.temporal.ocupacion * 100)}% de noches ocupadas, amoblado ${usd(c.temporal.amoblado_usd)}. Regulación: ${esc(c.regulacion)}.</p>` : "";
  const esc3 = Object.keys(e).length ? `<h3>¿Y si las cosas salen peor o mejor?</h3><table><tr><th></th><th>Ganancia anual</th><th>Al mes</th></tr>
    ${["pesimista", "base", "optimista"].map((k) => `<tr><td>${{ pesimista: "Peor caso", base: "Normal", optimista: "Mejor caso" }[k]}</td><td>${pct(e[k]?.tir_10)}</td><td>${usd(e[k]?.flujo_mensual_usd)}</td></tr>`).join("")}</table>` : "";
  const flujos = (d.flujos_10 || []).map((f, t) => `<tr><td>${t === 0 ? "Compra" : "Año " + t}</td><td style="color:${f < 0 ? COLOR.rojo : COLOR.verde}">${usd(f)}</td></tr>`).join("");
  return `<h3>Ten en cuenta</h3><ul>${(a.riesgos || []).map((r) => `<li>${esc(r)}</li>`).join("") || "<li>Sin alertas importantes</li>"}</ul>
    ${comp}${esc3}${d.parecidos ? `<p class="sub" style="margin-top:12px">Así se confirmó el precio y el alquiler: con estos avisos del mismo distrito, de tamaño y dormitorios parecidos.</p>` + listaParecidos("Parecidos en venta", d.parecidos.venta) + listaParecidos("Parecidos en alquiler", d.parecidos.alquiler, true) : ""}
    <h3>Dinero que entra y sale</h3><p class="sub">Incluye gastos de compra, impuestos y la venta al final del año 10.</p><table>${flujos}</table>
    <p class="sub" style="margin-top:12px">Inversión inicial ${usd(d.inversion_inicial)} · alquiler tradicional estimado ${usd(a.renta_mensual_usd)}/mes · plusvalía usada ${pct(d.plusvalia_usada)}.<br>Es una estimación automática: revisa SUNARP, deudas y el estado del inmueble antes de comprar.</p>`;
}

function abrirPanel(id) {
  if (innerWidth < 700) ["filtros", "lista", "detalle", "contactar", "perfil"].filter((x) => x !== id).forEach((x) => $(x).classList.remove("abierto"));
  $(id).classList.add("abierto");
}

function opciones() {
  const datos = { arbitraje: arbitrajes, negocios, oportunidades, inversion: inmuebles }[estado.capa];
  const dep = $("f-dep").value;
  const llenar = (sel, valores, primero) => {
    const actual = sel.value;
    sel.innerHTML = `<option value="">${primero}</option>` + [...new Set(valores.filter(Boolean))].sort().map((v) => `<option ${v === actual ? "selected" : ""}>${esc(v)}</option>`).join("");
  };
  llenar($("f-dep"), datos.map((i) => i.departamento), "Todo el Perú");
  llenar($("f-dist"), datos.filter((i) => !dep || i.departamento === dep).map((i) => i.distrito), "Todos");
}

async function todo(vista) {
  const filas = [];
  for (let desde = 0; ; desde += 1000) {
    const { data, error } = await sb.from(vista).select("*").range(desde, desde + 999);
    if (error) throw error;
    filas.push(...data);
    if (data.length < 1000) return filas;
  }
}

async function cargar() {
  $("cargando").hidden = false;
  try {
    if (DEMO) {
      const d = await (await fetch("demo.json")).json();
      inmuebles = d.inmuebles; arbitrajes = d.arbitrajes; negocios = d.negocios || [];
    } else {
      const seguro = (v) => todo(v).catch(() => []);
      [inmuebles, arbitrajes, negocios, oportunidades] = await Promise.all([todo("mapa_inmuebles"), seguro("mapa_arbitraje"), seguro("mapa_concesiones"), seguro("mapa_oportunidades")]);
      if (oportunidades.length && oportunidades[0].encaja === undefined) estado.paraMi = false;
    }
  } catch (e) {
    $("cargando").textContent = "No se pudo cargar: " + e.message;
    return;
  }
  $("cargando").hidden = !!(inmuebles.length || arbitrajes.length);
  if (!inmuebles.length && !arbitrajes.length) {
    const { count } = DEMO ? { count: 0 } : await sb.from("inmuebles").select("id", { count: "exact", head: true });
    $("cargando").textContent = count ? `Ya se reunieron ${count.toLocaleString("es-PE")} inmuebles; se están analizando y ubicando. Vuelve en unos minutos.` : "Aún no hay inmuebles. Los agentes los irán agregando.";
  }
  opciones();
  dibujar();
  if (inmuebles.length) mapa.fitBounds(L.latLngBounds(inmuebles.map((i) => [i.lat, i.lng])), { maxZoom: 12, padding: [20, 20] });
}

document.querySelectorAll("[data-cierra]").forEach((b) => b.onclick = () => $(b.dataset.cierra).classList.remove("abierto"));
$("b-filtros").onclick = () => $("filtros").classList.contains("abierto") ? $("filtros").classList.remove("abierto") : abrirPanel("filtros");
$("b-lista").onclick = () => $("lista").classList.contains("abierto") ? $("lista").classList.remove("abierto") : abrirPanel("lista");
$("b-zonas").onclick = () => {
  estado.zonas = !estado.zonas;
  $("b-zonas").classList.toggle("activo", estado.zonas);
  estado.zonas ? capaZonas.addTo(mapa) : mapa.removeLayer(capaZonas);
  dibujar();
};
const CAPAS = [["b-inversion", "inversion"], ["b-arbitraje", "arbitraje"], ["b-negocios", "negocios"], ["b-oportunidades", "oportunidades"]];
for (const [id, capa] of CAPAS) {
  $(id).onclick = () => {
    estado.capa = capa;
    CAPAS.forEach(([b, c]) => $(b).classList.toggle("activo", c === capa));
    modos();
    opciones();
    dibujar();
  };
}
$("f-horizonte").querySelectorAll(".btn").forEach((b) => b.onclick = () => {
  estado.horizonte = b.dataset.v;
  $("f-horizonte").querySelectorAll(".btn").forEach((x) => x.classList.toggle("activo", x === b));
  dibujar();
});
$("f-veredicto").querySelectorAll(".btn").forEach((b) => b.onclick = () => {
  estado.veredictos.has(b.dataset.v) ? estado.veredictos.delete(b.dataset.v) : estado.veredictos.add(b.dataset.v);
  b.classList.toggle("activo");
  dibujar();
});
$("f-dep").onchange = () => { $("f-dist").value = ""; opciones(); dibujar(); };
function modos() {
  $("modos").hidden = estado.capa !== "inversion";
  $("modos-op").hidden = estado.capa !== "oportunidades";
  $("b-paramí").classList.toggle("activo", estado.paraMi);
  $("modos").querySelectorAll(".btn").forEach((b) => b.classList.toggle("activo", b.dataset.modo === $("f-estrategia").value));
}
$("modos").querySelectorAll(".btn").forEach((b) => b.onclick = () => {
  $("f-estrategia").value = $("f-estrategia").value === b.dataset.modo ? "" : b.dataset.modo;
  modos();
  dibujar();
});
$("f-estrategia").addEventListener("change", modos);
["f-dist", "f-origen", "f-negocio", "f-rubro", "f-estrategia", "f-tipo", "f-estado", "f-precio"].forEach((id) => $(id).onchange = dibujar);
$("f-puntaje").oninput = () => { $("v-puntaje").textContent = $("f-puntaje").value; dibujar(); };

const mensaje = (p) => `Hola, soy asistente de Sergio Yacolca, de YACU Grupo Inmobiliario. Nos interesa invertir en ${p.nombre || "su proyecto"}${p.distrito ? " en " + p.distrito : ""}. ¿Nos podrían enviar precios, metrajes, fecha de entrega, forma de pago y mantenimiento de las unidades disponibles? Gracias.`;

function itemsTabla(i) {
  if (!i.items?.length) return "";
  return `<h3>Qué piden exactamente</h3><table><tr><th>Cant.</th><th>Detalle</th></tr>${i.items.map((x) => `<tr><td>${esc(x.cantidad ?? "—")} ${esc(x.unidad || "")}</td><td>${esc(x.descripcion || x.clase || "")}</td></tr>`).join("")}</table>`;
}

function paraTi(i) {
  if (i.encaja == null) return '<div class="aviso">🎯 La IA aún no revisa esta convocatoria contra tu perfil.</div>';
  const r = i.requisitos || {};
  const filas = [["Qué piden", i.que_piden || r.tipo_requerido], ["Cantidad", r.cantidad], ["Antigüedad máxima", r.antiguedad_maxima != null ? r.antiguedad_maxima + " años" : null],
    ["Con conductor", r.con_conductor == null ? null : r.con_conductor ? "Sí" : "No"], ["Plazo", r.plazo], ["Lugar", r.lugar]].filter(([, v]) => v);
  return `<h3>🎯 ¿Te sirve? ${i.encaja ? `<span style="color:${COLOR.verde}">Sí (${i.puntaje_perfil ?? "—"}/100)</span>` : `<span style="color:${COLOR.rojo}">No</span>`}</h3>
    <p class="sub">${esc(i.razon || "")}</p>${filas.length ? `<table>${filas.map(([k, v]) => `<tr><td>${k}</td><td>${esc(v)}</td></tr>`).join("")}</table>` : ""}
    ${(r.requisitos_clave || []).length ? `<p class="sub">Requisitos: ${r.requisitos_clave.map(esc).join(" · ")}</p>` : ""}
    ${r.sin_experiencia == null ? "" : `<h3>¿Piden experiencia previa?</h3><p><b style="color:${r.sin_experiencia ? COLOR.verde : COLOR.rojo}">${r.sin_experiencia ? "No, puedes postular sin experiencia" : "Sí, piden experiencia"}</b><br><span class="sub">${esc(r.experiencia || "")}</span></p>`}
    ${r.sin_empresa == null ? "" : `<h3>¿Puedes postular sin empresa?</h3><p><b style="color:${r.sin_empresa ? COLOR.verde : COLOR.rojo}">${r.sin_empresa ? "Sí, como persona natural con RUC" : "No, piden empresa o una autorización de empresa"}</b><br><span class="sub">${esc(r.sin_empresa_por_que || "")}</span></p>`}
    ${(r.para_postular || []).length ? `<h3>Lo que necesitas antes de postular</h3><ul>${r.para_postular.map((x) => `<li>${esc(typeof x === "string" ? x : Object.values(x).join(" — "))}</li>`).join("")}</ul>` : ""}
    ${(r.costos || []).length ? `<h3>Costos y ganancia ${r.costos_estimados ? "(estimados con precios típicos)" : "(con tus costos)"}</h3><table>${r.costos.map((c) => `<tr><td>${esc(c.concepto)}</td><td>S/ ${Math.round(+c.soles || 0).toLocaleString("es-PE")}</td></tr>`).join("")}
      <tr><td><b>Cobrarías</b></td><td><b>S/ ${Math.round(+r.ingreso_soles || 0).toLocaleString("es-PE")}</b></td></tr>
      <tr><td><b>Te quedaría</b></td><td><b style="color:${(+r.ganancia_soles || 0) > 0 ? COLOR.verde : COLOR.rojo}">S/ ${Math.round(+r.ganancia_soles || 0).toLocaleString("es-PE")}${r.margen != null ? ` (${Math.round(r.margen * 100)}%)` : ""}</b></td></tr></table>` : ""}
    ${i.requisitos ? '<p class="sub">✔ Revisado leyendo las bases oficiales. Para el Estado, como persona natural basta RUC activo y habido + RNP (S/ 29, vigencia indefinida), salvo que las bases pidan otra cosa.</p>' : '<p class="sub">Revisado con el resumen; las bases se leen en el próximo ciclo de tu PC.</p>'}`;
}

function filaActivo(a = {}) {
  const d = document.createElement("div");
  d.className = "activo-fila";
  d.innerHTML = `<input placeholder="Qué (ej. Camioneta 4x4)" value="${esc(a.que || "")}"><input type="number" min="1" placeholder="Cant." value="${esc(a.cantidad || "")}">
    <input placeholder="Detalle (año, capacidad, con chofer)" value="${esc(a.detalle || "")}"><button class="btn" type="button">×</button>`;
  d.querySelector("button").onclick = () => d.remove();
  $("p-activos").appendChild(d);
}
$("p-agregar").onclick = () => filaActivo();

async function abrirPerfil() {
  abrirPanel("perfil");
  if (DEMO) return;
  const { data } = await sb.from("perfiles").select("descripcion,departamentos,activos,tiene_empresa,costos").eq("id", "principal").single();
  $("p-activos").innerHTML = "";
  (data?.activos?.length ? data.activos : [{}]).forEach(filaActivo);
  $("p-desc").value = data?.descripcion || "";
  $("p-empresa").checked = !!data?.tiene_empresa;
  $("p-costos").value = data?.costos || "";
  $("p-deps").value = (data?.departamentos || []).join(", ");
}
$("b-perfil").onclick = abrirPerfil;
$("b-sinexp").onclick = () => { estado.sinExp = !estado.sinExp; $("b-sinexp").classList.toggle("activo", estado.sinExp); dibujar(); };
$("b-paramí").onclick = () => { estado.paraMi = !estado.paraMi; $("b-paramí").classList.toggle("activo", estado.paraMi); dibujar(); };
$("p-guardar").onclick = async () => {
  const deps = $("p-deps").value.split(",").map((x) => x.trim()).filter(Boolean);
  const activos = [...$("p-activos").children].map((d) => { const [q, c, det] = d.querySelectorAll("input"); return { que: q.value.trim(), cantidad: +c.value || 1, detalle: det.value.trim() }; }).filter((a) => a.que);
  const { error } = await sb.from("perfiles").update({ descripcion: $("p-desc").value.trim(), departamentos: deps.length ? deps : null, activos, tiene_empresa: $("p-empresa").checked, costos: $("p-costos").value.trim() || null }).eq("id", "principal");
  $("p-msg").textContent = error ? error.message : "✅ Guardado. La IA volverá a revisar todas las convocatorias en el próximo ciclo (máx. 6 horas).";
};

const mensajeNegocio = (p) => `Hola, soy asistente de Sergio Yacolca, de YACU Grupo Inmobiliario. Nos interesa ${p.nombre || "su negocio"}${p.distrito ? " en " + p.distrito : ""}. ¿Nos podrían indicar la inversión o precio, el canon o alquiler mensual, las ventas promedio al mes y la duración del contrato? Gracias.`;

async function pistas() {
  if (DEMO) { $("pistas").innerHTML = '<p class="sub">No disponible en modo ejemplo.</p>'; return; }
  const campos = "id,nombre,distrito,departamento,url,telefono,contacto_estado,contactado";
  const [r1, r2] = await Promise.all([
    sb.from("pistas").select(campos).not("telefono", "is", null).is("precio", null).in("contacto_estado", ["pendiente", "contactado"]).limit(200),
    sb.from("concesiones").select(campos).not("telefono", "is", null).eq("veredicto", "Falta información").in("contacto_estado", ["pendiente", "contactado"]).limit(200),
  ]);
  const error = r1.error || r2.error;
  if (error) { $("pistas").innerHTML = `<p class="sub">${esc(error.message)}</p>`; return; }
  const data = [...r1.data.map((p) => ({ ...p, tabla: "pistas" })), ...r2.data.map((p) => ({ ...p, tabla: "concesiones" }))].sort((a, b) => a.contacto_estado.localeCompare(b.contacto_estado));
  $("pistas").innerHTML = data.map((p) => `<div class="item" data-id="${p.id}" data-tabla="${p.tabla}"><b>${p.tabla === "concesiones" ? "🏪 " : ""}${esc(p.nombre || "Proyecto")}</b><br>
    <span class="sub">${esc([p.distrito, p.departamento].filter(Boolean).join(", "))}${p.contacto_estado === "contactado" ? " · escrito el " + new Date(p.contactado).toLocaleDateString("es-PE") : ""}</span><br>
    <a class="btn" href="https://wa.me/${p.telefono}?text=${encodeURIComponent(p.tabla === "concesiones" ? mensajeNegocio(p) : mensaje(p))}" target="_blank" rel="noopener" data-wa>Escribir por WhatsApp</a>
    ${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">web</a>` : ""}
    <textarea placeholder="Pega aquí la respuesta"></textarea><button class="btn" data-guardar>Guardar respuesta</button></div>`).join("") || '<p class="sub">No hay proyectos pendientes de contactar.</p>';
  $("pistas").querySelectorAll(".item").forEach((el) => {
    const id = el.dataset.id, tabla = el.dataset.tabla;
    el.querySelector("[data-wa]").onclick = () => sb.from(tabla).update({ contacto_estado: "contactado", contactado: new Date().toISOString() }).eq("id", id).then(() => {});
    el.querySelector("[data-guardar]").onclick = async () => {
      const respuesta = el.querySelector("textarea").value.trim();
      if (!respuesta) return;
      const { error } = await sb.from(tabla).update({ respuesta, contacto_estado: "respondido" }).eq("id", id);
      el.innerHTML = error ? `<p class="sub">${esc(error.message)}</p>` : '<p class="sub">✅ Guardado. Aparecerá en el mapa tras el próximo análisis.</p>';
    };
  });
}
$("b-contactar").onclick = () => $("contactar").classList.contains("abierto") ? $("contactar").classList.remove("abierto") : (abrirPanel("contactar"), pistas());

$("w-agregar").onclick = async () => {
  let url = $("w-url").value.trim();
  if (!url) return;
  if (!/^https?:\/\//.test(url)) url = "https://" + url;
  let d;
  try { d = new URL(url).hostname.replace(/^www\./, ""); } catch { $("w-msg").textContent = "Esa dirección no es válida."; return; }
  if (DEMO) { $("w-msg").textContent = "No disponible en modo ejemplo."; return; }
  const { error } = await sb.from("sitios").insert({ dominio: d, url, ciudad: $("w-ciudad").value.trim() || null, origen: "usuario" });
  $("w-msg").textContent = error ? (error.code === "23505" ? "Esa web ya está en la lista: se revisa en cada ciclo." : error.message) : "✅ Agregada. Sus proyectos aparecerán después del próximo ciclo diario.";
  if (!error) $("w-url").value = "";
};

async function entrar(crear) {
  const email = $("correo").value, password = $("clave").value;
  const { error } = crear ? await sb.auth.signUp({ email, password }) : await sb.auth.signInWithPassword({ email, password });
  if (error) { $("msg-login").textContent = error.message; return; }
  if (crear) { $("msg-login").textContent = "Cuenta creada. Si pide confirmar el correo, revisa tu bandeja y luego entra."; return; }
  $("login").hidden = true;
  cargar();
}

(async () => {
  if (DEMO) { $("contador").textContent = "Datos de ejemplo"; return cargar(); }
  sb = supabase.createClient(CONFIG.supabaseUrl, CONFIG.supabaseKey);
  const { data } = await sb.auth.getSession();
  if (data.session) return cargar();
  $("login").hidden = false;
  $("form-login").onsubmit = (e) => { e.preventDefault(); entrar(false); };
  $("crear").onclick = () => entrar(true);
})();
