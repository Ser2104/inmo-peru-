create table pistas (
  id uuid primary key default gen_random_uuid(),
  clave text not null unique,
  nombre text,
  url text,
  mencionado_en text,
  categoria text,
  departamento text,
  provincia text,
  distrito text,
  tipo text,
  estado_obra text,
  constructora text,
  precio numeric,
  moneda text,
  area_m2 numeric,
  resumen text,
  estado text not null default 'nueva' check (estado in ('nueva','incompleta','verificada','descartada')),
  intentos int not null default 0,
  inmueble_id uuid references inmuebles(id) on delete set null,
  creado timestamptz not null default now(),
  actualizado timestamptz not null default now()
);
create index on pistas (estado, intentos);
alter table pistas enable row level security;

insert into fuentes (id, nombre, tipo, urls, config) values
 ('bbva-adjudicados','BBVA inmuebles adjudicados','ia','{"https://www.bbva.pe/personas/productos/inversiones/irbsa.html"}','{"seguir_pdf": true}'),
 ('remaju','Remates judiciales REMAJU','ia','{"https://remaju.pj.gob.pe/remaju/index.xhtml"}','{}')
on conflict (id) do nothing;

insert into fuentes (id, nombre, tipo, urls) values ('explorador','Explorador (foros, noticias, constructoras, remates)','manual','{}') on conflict (id) do nothing;
