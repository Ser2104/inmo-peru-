alter table pistas add column telefono text;
alter table pistas add column contacto_estado text not null default 'pendiente' check (contacto_estado in ('pendiente','contactado','respondido','procesado','descartado'));
alter table pistas add column respuesta text;
alter table pistas add column contactado timestamptz;

create policy mapa_lee_pistas on pistas for select to authenticated using (puede_ver_mapa());
create policy mapa_responde_pistas on pistas for update to authenticated using (puede_ver_mapa()) with check (puede_ver_mapa());
revoke update on pistas from authenticated;
grant update (contacto_estado, respuesta, contactado) on pistas to authenticated;
