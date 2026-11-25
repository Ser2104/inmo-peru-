create table oportunidades (
  id uuid primary key default gen_random_uuid(),
  clave text not null unique,
  fuente text not null,
  titulo text,
  descripcion text,
  rubro text,
  categoria text,
  metodo text,
  entidad text,
  telefono text,
  correo text,
  web text,
  departamento text,
  provincia text,
  distrito text,
  lat double precision,
  lng double precision,
  monto_usd numeric,
  fecha_publicacion date,
  fecha_limite date,
  url text,
  creado timestamptz not null default now()
);
create index on oportunidades (rubro, fecha_limite);
alter table oportunidades enable row level security;
create policy mapa_lee_oportunidades on oportunidades for select to authenticated using (puede_ver_mapa());

create view mapa_oportunidades with (security_invoker = true) as
select id, fuente, titulo, descripcion, rubro, categoria, metodo, entidad, telefono, correo, web, departamento, provincia, distrito,
       lat, lng, monto_usd, fecha_publicacion, fecha_limite, url
from oportunidades
where lat is not null and coalesce(fecha_limite, fecha_publicacion + 30, (creado + interval '30 days')::date) >= current_date;
grant select on mapa_oportunidades to authenticated;
revoke select on mapa_oportunidades from anon;
