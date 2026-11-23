
create table fuentes (
  id text primary key,
  nombre text not null,
  tipo text not null check (tipo in ('navent','ia','bcrp','manual')),
  urls text[] not null default '{}',
  config jsonb not null default '{}',
  activo boolean not null default true,
  ultimo_ok timestamptz,
  ultimo_error text,
  fallos_seguidos int not null default 0,
  creado timestamptz not null default now()
);

create table inmuebles (
  id uuid primary key default gen_random_uuid(),
  fuente text references fuentes(id),
  url text not null unique,
  titulo text,
  tipo text,
  operacion text check (operacion in ('venta','alquiler')),
  estado text default 'terminado' check (estado in ('terminado','en_planos','preventa','remate')),
  departamento text,
  provincia text,
  distrito text,
  direccion text,
  lat double precision,
  lng double precision,
  area_m2 numeric,
  dormitorios int,
  banos int,
  estacionamientos int,
  precio numeric,
  moneda text,
  precio_usd numeric,
  mantenimiento_usd numeric,
  fecha_entrega date,
  constructora text,
  descripcion text,
  duplicado_de uuid references inmuebles(id),
  sospechoso text,
  activo boolean not null default true,
  primera_vez timestamptz not null default now(),
  ultima_vez timestamptz not null default now()
);
create index on inmuebles (departamento, provincia, distrito, tipo, operacion) where activo;
create index on inmuebles (ultima_vez);

create table precios_historial (
  inmueble_id uuid references inmuebles(id) on delete cascade,
  fecha date not null default current_date,
  precio_usd numeric not null,
  primary key (inmueble_id, fecha)
);

create table series_macro (
  codigo text,
  nombre text,
  periodo text,
  valor numeric,
  primary key (codigo, periodo)
);

create table zonas_stats (
  departamento text,
  provincia text,
  distrito text,
  tipo text,
  operacion text,
  n int,
  mediana_m2_usd numeric,
  p25_m2_usd numeric,
  p75_m2_usd numeric,
  plusvalia_anual numeric,
  actualizado timestamptz default now(),
  primary key (departamento, provincia, distrito, tipo, operacion)
);

create table analisis (
  inmueble_id uuid primary key references inmuebles(id) on delete cascade,
  fecha timestamptz not null default now(),
  precio_usd numeric,
  renta_mensual_usd numeric,
  fuente_renta text,
  rentabilidad_bruta numeric,
  rentabilidad_neta numeric,
  flujo_mensual_usd numeric,
  descuento_vs_zona numeric,
  tir_2 numeric, tir_5 numeric, tir_10 numeric,
  van_10 numeric,
  payback_anios numeric,
  precio_max_recomendado numeric,
  puntaje_corto numeric, puntaje_mediano numeric, puntaje_largo numeric, puntaje_total numeric,
  veredicto text,
  confianza text,
  riesgos jsonb,
  detalle jsonb,
  version text
);
create index on analisis (puntaje_total desc);

create table alertas (
  id bigserial primary key,
  inmueble_id uuid references inmuebles(id) on delete cascade,
  fecha timestamptz default now(),
  unique (inmueble_id)
);

create table parametros (
  clave text primary key,
  valor jsonb not null,
  actualizado timestamptz default now()
);

create table ejecuciones (
  id bigserial primary key,
  agente text,
  inicio timestamptz default now(),
  fin timestamptz,
  ok boolean,
  detalle jsonb
);

alter table fuentes enable row level security;
alter table inmuebles enable row level security;
alter table precios_historial enable row level security;
alter table series_macro enable row level security;
alter table zonas_stats enable row level security;
alter table analisis enable row level security;
alter table alertas enable row level security;
alter table parametros enable row level security;
alter table ejecuciones enable row level security;

insert into fuentes (id, nombre, tipo, urls) values
 ('bcrp','BCRP','bcrp','{}'),
 ('urbania','Urbania','navent','{"https://urbania.pe/buscar/venta-de-propiedades?page={n}","https://urbania.pe/buscar/alquiler-de-propiedades?page={n}","https://urbania.pe/buscar/proyectos-propiedades?page={n}"}'),
 ('adondevivir','Adondevivir','navent','{"https://www.adondevivir.com/buscar/venta-de-propiedades?page={n}","https://www.adondevivir.com/buscar/alquiler-de-propiedades?page={n}"}'),
 ('properati','Properati','ia','{"https://www.properati.com.pe/s/venta?page={n}","https://www.properati.com.pe/s/alquiler?page={n}"}'),
 ('nexoinmobiliario','Nexo Inmobiliario','ia','{"https://nexoinmobiliario.pe/busqueda/venta-de-departamentos-en-peru?page={n}"}'),
 ('manual','Ingreso manual','manual','{}');
