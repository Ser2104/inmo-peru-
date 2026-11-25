create table perfiles (
  id text primary key,
  descripcion text not null,
  departamentos text[],
  version int not null default 1,
  actualizado timestamptz not null default now()
);
alter table perfiles enable row level security;
create policy mapa_lee_perfiles on perfiles for select to authenticated using (puede_ver_mapa());
create policy mapa_edita_perfiles on perfiles for update to authenticated using (puede_ver_mapa()) with check (puede_ver_mapa());
revoke update on perfiles from authenticated;
grant update (descripcion, departamentos) on perfiles to authenticated;

create or replace function perfil_nueva_version() returns trigger language plpgsql set search_path = public as $$
begin
  if new.descripcion is distinct from old.descripcion or new.departamentos is distinct from old.departamentos then
    new.version := old.version + 1;
    new.actualizado := now();
  end if;
  return new;
end $$;
create trigger perfil_version before update on perfiles for each row execute function perfil_nueva_version();

insert into perfiles (id, descripcion) values ('principal',
 'Tengo 7 camionetas propias. Puedo ofrecer alquiler de camionetas (con o sin conductor), servicio de movilidad o transporte de personal y traslado de carga ligera en camioneta. No vendo vehículos ni hago obras.');

create table coincidencias (
  oportunidad_id uuid not null references oportunidades(id) on delete cascade,
  perfil_id text not null references perfiles(id) on delete cascade,
  version int not null,
  encaja boolean not null,
  puntaje int,
  razon text,
  que_piden text,
  requisitos jsonb,
  bases_leidas boolean not null default false,
  actualizado timestamptz not null default now(),
  primary key (oportunidad_id, perfil_id)
);
alter table coincidencias enable row level security;
create policy mapa_lee_coincidencias on coincidencias for select to authenticated using (puede_ver_mapa());

drop view mapa_oportunidades;
create view mapa_oportunidades with (security_invoker = true) as
select o.id, o.fuente, o.titulo, o.descripcion, o.rubro, o.categoria, o.metodo, o.entidad, o.telefono, o.correo, o.web, o.departamento, o.provincia, o.distrito,
       o.lat, o.lng, o.monto_usd, o.fecha_publicacion, o.fecha_limite, o.url,
       c.encaja, c.puntaje as puntaje_perfil, c.razon, c.que_piden, c.requisitos
from oportunidades o
left join coincidencias c on c.oportunidad_id = o.id and c.perfil_id = 'principal'
where o.lat is not null and coalesce(o.fecha_limite, o.fecha_publicacion + 30, (o.creado + interval '30 days')::date) >= current_date;
grant select on mapa_oportunidades to authenticated;
revoke select on mapa_oportunidades from anon;
