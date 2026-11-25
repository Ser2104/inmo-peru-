alter table perfiles add column tiene_empresa boolean not null default false, add column costos text;
grant update (tiene_empresa, costos) on perfiles to authenticated;

create or replace function perfil_nueva_version() returns trigger language plpgsql set search_path = public as $$
begin
  if new.descripcion is distinct from old.descripcion or new.departamentos is distinct from old.departamentos or new.activos is distinct from old.activos
     or new.tiene_empresa is distinct from old.tiene_empresa or new.costos is distinct from old.costos then
    new.version := old.version + 1;
    new.actualizado := now();
  end if;
  return new;
end $$;
