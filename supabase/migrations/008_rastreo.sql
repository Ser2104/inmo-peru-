create table rastreo (
  url text primary key,
  dominio text not null,
  visto timestamptz not null default now(),
  avisos int not null default 0
);
create index on rastreo (dominio);
alter table rastreo enable row level security;
