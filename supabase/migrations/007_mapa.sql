alter table inmuebles add column ubicacion_precision text check (ubicacion_precision in ('exacta','direccion','distrito'));

create table geocache (
  consulta text primary key,
  lat double precision,
  lng double precision,
  creado timestamptz not null default now()
);
alter table geocache enable row level security;

create table usuarios_mapa (email text primary key);
alter table usuarios_mapa enable row level security;

create or replace function puede_ver_mapa() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from usuarios_mapa where lower(email) = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;
revoke execute on function puede_ver_mapa() from public, anon;
grant execute on function puede_ver_mapa() to authenticated;

create policy mapa_lee_inmuebles on inmuebles for select to authenticated using (puede_ver_mapa());
create policy mapa_lee_analisis on analisis for select to authenticated using (puede_ver_mapa());
create policy mapa_lee_arbitraje on arbitraje for select to authenticated using (puede_ver_mapa());
create policy mapa_lee_zonas on zonas_stats for select to authenticated using (puede_ver_mapa());
create policy mapa_lee_mercado on mercado_temporal for select to authenticated using (puede_ver_mapa());
create policy mapa_lee_regulacion on regulacion_temporal for select to authenticated using (puede_ver_mapa());

create view mapa_inmuebles with (security_invoker = true) as
select i.id, i.lat, i.lng, i.ubicacion_precision, i.titulo, i.url, i.tipo, i.estado, i.departamento, i.provincia, i.distrito,
       i.area_m2, i.dormitorios, i.fuente, a.precio_usd, a.veredicto, a.confianza, a.puntaje_total, a.puntaje_corto, a.puntaje_mediano,
       a.puntaje_largo, a.estrategia, a.tir_10, a.tir_10_temporal, a.renta_mensual_usd, a.flujo_mensual_usd, a.flujo_mensual_temporal,
       a.precio_max_recomendado, a.descuento_vs_zona, a.rentabilidad_neta
from inmuebles i join analisis a on a.inmueble_id = i.id
where i.activo and i.lat is not null and i.duplicado_de is null and i.sospechoso is null;

create view mapa_arbitraje with (security_invoker = true) as
select i.id, i.lat, i.lng, i.ubicacion_precision, i.titulo, i.url, i.departamento, i.provincia, i.distrito, i.area_m2, i.dormitorios,
       r.renta_usd, r.ingreso_temporal_mensual_usd, r.utilidad_mensual_usd, r.payback_meses, r.puntaje, r.veredicto, r.riesgos
from inmuebles i join arbitraje r on r.inmueble_id = i.id
where i.activo and i.lat is not null;

grant select on mapa_inmuebles, mapa_arbitraje to authenticated;
revoke select on mapa_inmuebles, mapa_arbitraje from anon;
