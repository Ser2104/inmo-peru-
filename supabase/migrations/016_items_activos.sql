alter table oportunidades add column items jsonb;
alter table perfiles add column activos jsonb;
grant update (activos) on perfiles to authenticated;

create or replace function perfil_nueva_version() returns trigger language plpgsql set search_path = public as $$
begin
  if new.descripcion is distinct from old.descripcion or new.departamentos is distinct from old.departamentos or new.activos is distinct from old.activos then
    new.version := old.version + 1;
    new.actualizado := now();
  end if;
  return new;
end $$;

update perfiles set activos = '[{"que": "Camioneta", "cantidad": 7, "detalle": ""}]'::jsonb where id = 'principal';

create or replace view mapa_oportunidades with (security_invoker = true) as
select o.id, o.fuente, o.titulo, o.descripcion, o.rubro, o.categoria, o.metodo, o.entidad, o.telefono, o.correo, o.web, o.departamento, o.provincia, o.distrito,
       o.lat, o.lng, o.monto_usd, o.fecha_publicacion, o.fecha_limite, o.url,
       c.encaja, c.puntaje as puntaje_perfil, c.razon, c.que_piden, c.requisitos, o.items
from oportunidades o
left join coincidencias c on c.oportunidad_id = o.id and c.perfil_id = 'principal'
where o.lat is not null and coalesce(o.fecha_limite, o.fecha_publicacion + 12, (o.creado + interval '12 days')::date) >= current_date;
