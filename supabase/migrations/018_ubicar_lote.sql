create or replace function ubicar_lote(filas jsonb) returns int language sql security invoker set search_path = public as $$
  with d as (
    select (x->>'id')::uuid id, (x->>'lat')::float8 lat, (x->>'lng')::float8 lng, x->>'ubicacion_precision' p
    from jsonb_array_elements(filas) x
  ), u as (
    update inmuebles i set lat = d.lat, lng = d.lng, ubicacion_precision = d.p from d where i.id = d.id returning 1
  )
  select count(*)::int from u;
$$;
revoke execute on function ubicar_lote(jsonb) from public, anon, authenticated;
grant execute on function ubicar_lote(jsonb) to service_role;
