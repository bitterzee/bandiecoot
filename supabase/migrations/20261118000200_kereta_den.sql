-- Kereta Den: the shared bike design lives in items (coll 'bike');
-- bike_log counts Claude modifications per person for a daily limit.
alter table public.items drop constraint if exists items_coll_check;
alter table public.items add constraint items_coll_check check (coll in ('moment','pin','map','song','avatar','relay','lineup','jbmeta','jbstory','bike'));

create table if not exists public.bike_log (
  id bigint generated always as identity primary key,
  email text not null default lower(coalesce(auth.jwt() ->> 'email', '')),
  prompt text not null check (length(prompt) between 1 and 200),
  created_at timestamptz not null default now()
);
alter table public.bike_log enable row level security;
drop policy if exists bike_log_read on public.bike_log;
drop policy if exists bike_log_insert on public.bike_log;
create policy bike_log_read on public.bike_log for select to authenticated
  using (public.is_member() and email = lower(coalesce(auth.jwt() ->> 'email', '')));
create policy bike_log_insert on public.bike_log for insert to authenticated
  with check (public.is_member() and email = lower(coalesce(auth.jwt() ->> 'email', '')));
revoke all on public.bike_log from anon;
grant select, insert on public.bike_log to authenticated;
