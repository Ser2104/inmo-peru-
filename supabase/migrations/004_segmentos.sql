alter table zonas_stats add column segmento text not null default '*';
alter table zonas_stats drop constraint zonas_stats_pkey;
alter table zonas_stats add primary key (departamento, provincia, distrito, tipo, operacion, segmento);
