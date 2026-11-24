create table concesiones (
  id uuid primary key default gen_random_uuid(),
  clave text not null unique,
  tipo text not null check (tipo in ('traspaso','local','estado')),
  nombre text,
  rubro text,
  entidad text,
  url text,
  mencionado_en text,
  departamento text,
  provincia text,
  distrito text,
  direccion text,
  lat double precision,
  lng double precision,
  area_m2 numeric,
  inversion_usd numeric,
  canon_mensual_usd numeric,
  ventas_mensuales_usd numeric,
  utilidad_declarada_usd numeric,
  plazo_meses int,
  fecha_limite date,
  etapa text,
  descripcion text,
  telefono text,
  contacto_estado text not null default 'pendiente' check (contacto_estado in ('pendiente','contactado','respondido','procesado','descartado')),
  respuesta text,
  contactado timestamptz,
  revisado boolean not null default false,
  veredicto text,
  puntaje numeric,
  tir_anual numeric,
  van_usd numeric,
  payback_meses numeric,
  utilidad_mensual_usd numeric,
  detalle jsonb,
  riesgos text[],
  visto timestamptz not null default now(),
  creado timestamptz not null default now()
);
create index on concesiones (tipo, veredicto);
alter table concesiones enable row level security;

create policy mapa_lee_concesiones on concesiones for select to authenticated using (puede_ver_mapa());
create policy mapa_responde_concesiones on concesiones for update to authenticated using (puede_ver_mapa()) with check (puede_ver_mapa());
revoke update on concesiones from authenticated;
grant update (contacto_estado, respuesta, contactado) on concesiones to authenticated;
revoke all on concesiones from anon;

create view mapa_concesiones with (security_invoker = true) as
select id, tipo, nombre, rubro, entidad, url, departamento, provincia, distrito, lat, lng, area_m2, inversion_usd, canon_mensual_usd,
       ventas_mensuales_usd, plazo_meses, fecha_limite, etapa, descripcion, telefono, veredicto, puntaje, tir_anual, van_usd,
       payback_meses, utilidad_mensual_usd, detalle, riesgos
from concesiones
where lat is not null and visto > now() - interval '90 days' and (fecha_limite is null or fecha_limite >= current_date);
grant select on mapa_concesiones to authenticated;
revoke select on mapa_concesiones from anon;
