create table entorno (clave text primary key, conteos jsonb not null, creado timestamptz not null default now());
alter table entorno enable row level security;
alter table concesiones add column ubicacion_precision text, add column puntaje_ubicacion numeric, add column entorno jsonb;
alter table inmuebles add column entorno jsonb;

create or replace view mapa_concesiones with (security_invoker = true) as
select id, tipo, nombre, rubro, entidad, url, departamento, provincia, distrito, lat, lng, area_m2, inversion_usd, canon_mensual_usd,
       ventas_mensuales_usd, plazo_meses, fecha_limite, etapa, descripcion, telefono, veredicto, puntaje, tir_anual, van_usd,
       payback_meses, utilidad_mensual_usd, detalle, riesgos, mencionado_en, ubicacion_precision, puntaje_ubicacion, entorno
from concesiones
where lat is not null and visto > now() - interval '90 days' and (fecha_limite is null or fecha_limite >= current_date)
  and (url like 'http%' or mencionado_en like 'http%' or telefono is not null);

create or replace view mapa_inmuebles with (security_invoker = true) as
select i.id, i.lat, i.lng, i.ubicacion_precision, i.titulo, i.url, i.tipo, i.estado, i.departamento, i.provincia, i.distrito,
       i.area_m2, i.dormitorios, i.fuente, a.precio_usd, a.veredicto, a.confianza, a.puntaje_total, a.puntaje_corto, a.puntaje_mediano,
       a.puntaje_largo, a.estrategia, a.tir_10, a.tir_10_temporal, a.renta_mensual_usd, a.flujo_mensual_usd, a.flujo_mensual_temporal,
       a.precio_max_recomendado, a.descuento_vs_zona, a.rentabilidad_neta, i.telefono, i.constructora, i.confirmado, i.confirmacion, i.entorno
from inmuebles i join analisis a on a.inmueble_id = i.id
where i.activo and i.lat is not null and i.duplicado_de is null and i.sospechoso is null;
