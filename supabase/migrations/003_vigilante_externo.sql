create extension if not exists pg_net schema extensions;
create extension if not exists pg_cron;

create table if not exists secretos (clave text primary key, valor text not null);
alter table secretos enable row level security;

create or replace function vigilante_externo() returns void
language plpgsql security definer set search_path = public as $$
declare
  ultimo timestamptz;
  token text := (select valor from secretos where clave = 'telegram_token');
  chat text := (select valor from secretos where clave = 'telegram_chat_id');
  avisado timestamptz := (select (valor #>> '{}')::timestamptz from parametros where clave = 'vigilante_externo_aviso');
begin
  select max(fin) into ultimo from ejecuciones where agente = 'analista' and ok;
  if token is null or (ultimo is not null and ultimo > now() - interval '10 hours') then
    return;
  end if;
  if avisado is not null and avisado > now() - interval '12 hours' then
    return;
  end if;
  perform net.http_post(
    url := 'https://api.telegram.org/bot' || token || '/sendMessage',
    body := jsonb_build_object('chat_id', chat, 'text',
      '🚨 Analizador inmobiliario: los agentes no corren desde ' || coalesce(ultimo::text, 'nunca') ||
      '. Revisa GitHub Actions (puede estar desactivado o sin minutos).'),
    headers := '{"Content-Type": "application/json"}'::jsonb
  );
  insert into parametros (clave, valor) values ('vigilante_externo_aviso', to_jsonb(now()))
  on conflict (clave) do update set valor = excluded.valor, actualizado = now();
end $$;

revoke execute on function vigilante_externo() from public, anon, authenticated;

select cron.schedule('vigilante-externo', '15 * * * *', 'select vigilante_externo()');
