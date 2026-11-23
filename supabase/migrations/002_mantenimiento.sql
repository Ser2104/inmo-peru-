alter table inmuebles drop constraint inmuebles_duplicado_de_fkey;
alter table inmuebles add constraint inmuebles_duplicado_de_fkey foreign key (duplicado_de) references inmuebles(id) on delete set null;

create or replace function tamano_db() returns bigint
language sql security definer set search_path = public as $$
  select pg_database_size(current_database());
$$;

create or replace function limpiar_antiguo() returns jsonb
language plpgsql security definer set search_path = public as $$
declare a int; b int; c int; d int;
begin
  delete from ejecuciones where inicio < now() - interval '90 days';
  get diagnostics a = row_count;
  delete from precios_historial h using inmuebles i
   where h.inmueble_id = i.id and not i.activo and h.fecha < current_date - 730;
  get diagnostics b = row_count;
  update inmuebles set descripcion = null
   where not activo and descripcion is not null and ultima_vez < now() - interval '180 days';
  get diagnostics c = row_count;
  delete from inmuebles where not activo and ultima_vez < now() - interval '3 years';
  get diagnostics d = row_count;
  return jsonb_build_object('ejecuciones', a, 'historial', b, 'descripciones', c, 'inmuebles', d);
end $$;

revoke execute on function tamano_db() from public, anon, authenticated;
revoke execute on function limpiar_antiguo() from public, anon, authenticated;
grant execute on function tamano_db() to service_role;
grant execute on function limpiar_antiguo() to service_role;

create or replace function marcar_actualizado() returns trigger language plpgsql set search_path = public as $$
begin new.actualizado = now(); return new; end $$;
create trigger parametros_actualizado before update on parametros for each row execute function marcar_actualizado();
