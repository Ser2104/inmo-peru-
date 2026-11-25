alter table oportunidades add column fecha_consultas date;

create or replace view mapa_oportunidades with (security_invoker = true) as
select o.id, o.fuente, o.titulo, o.descripcion, o.rubro, o.categoria, o.metodo, o.entidad, o.telefono, o.correo, o.web, o.departamento, o.provincia, o.distrito,
       o.lat, o.lng, o.monto_usd, o.fecha_publicacion, o.fecha_limite, o.url,
       c.encaja, c.puntaje as puntaje_perfil, c.razon, c.que_piden, c.requisitos, o.items, o.fecha_consultas
from oportunidades o
left join coincidencias c on c.oportunidad_id = o.id and c.perfil_id = 'principal'
where o.lat is not null and coalesce(o.fecha_limite, o.fecha_consultas + 7, o.fecha_publicacion + 12, (o.creado + interval '12 days')::date) >= current_date;
