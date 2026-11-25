alter table inmuebles add column if not exists antiguedad_anios smallint;

create or replace view mapa_inmuebles with (security_invoker = true) as
select i.id, i.lat, i.lng, i.ubicacion_precision, i.titulo, i.url, i.tipo, i.estado, i.departamento, i.provincia, i.distrito,
       i.area_m2, i.dormitorios, i.fuente, a.precio_usd, a.veredicto, a.confianza, a.puntaje_total, a.puntaje_corto, a.puntaje_mediano,
       a.puntaje_largo, a.estrategia, a.tir_10, a.tir_10_temporal, a.renta_mensual_usd, a.flujo_mensual_usd, a.flujo_mensual_temporal,
       a.precio_max_recomendado, a.descuento_vs_zona, a.rentabilidad_neta, i.telefono, i.constructora, i.confirmado, i.confirmacion, i.entorno,
       i.antiguedad_anios
from inmuebles i join analisis a on a.inmueble_id = i.id
where i.activo and i.lat is not null and i.duplicado_de is null and i.sospechoso is null;
