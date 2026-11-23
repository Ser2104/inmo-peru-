create table mercado_temporal (
  id bigserial primary key,
  clave text not null unique,
  departamento text,
  provincia text,
  distrito text,
  adr_usd numeric,
  ocupacion numeric,
  ingreso_anual_usd numeric,
  anuncios int,
  dormitorios int,
  fuente text,
  url text,
  periodo text,
  fecha timestamptz not null default now()
);
create index on mercado_temporal (departamento, provincia, distrito);
alter table mercado_temporal enable row level security;

create table regulacion_temporal (
  departamento text not null,
  distrito text not null,
  estado text not null check (estado in ('permitido','restringido','prohibido','desconocido')),
  nota text,
  fuente text,
  actualizado timestamptz not null default now(),
  primary key (departamento, distrito)
);
alter table regulacion_temporal enable row level security;

create table arbitraje (
  inmueble_id uuid primary key references inmuebles(id) on delete cascade,
  fecha timestamptz not null default now(),
  renta_usd numeric,
  ingreso_temporal_mensual_usd numeric,
  utilidad_mensual_usd numeric,
  inversion_usd numeric,
  retorno_anual numeric,
  payback_meses numeric,
  puntaje numeric,
  veredicto text,
  confianza text,
  riesgos jsonb,
  detalle jsonb
);
create index on arbitraje (puntaje desc);
alter table arbitraje enable row level security;

alter table analisis add column estrategia text default 'largo_plazo';
alter table analisis add column tir_10_temporal numeric;
alter table analisis add column flujo_mensual_temporal numeric;
alter table analisis add column ingreso_temporal_anual numeric;

insert into regulacion_temporal (departamento, distrito, estado, nota, fuente) values
 ('lima','miraflores','restringido','Ordenanza municipal impide alquiler vacacional o rotativo en edificios de zonas residenciales','https://dplnews.com/?p=91602');
