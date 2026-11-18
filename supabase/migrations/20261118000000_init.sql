-- Bandiecoot: a private app for exactly 7 people.
-- 1) members: the invite list (max 7). Only these emails can create an account.
-- 2) items:   all shared app data, one row per thing (moment, pin, song, ...).
-- 3) media:   private storage bucket for photos.
-- Turn the hook on in Supabase -> Authentication -> Hooks -> "Before User Created"
-- (Postgres function public.hook_before_user_created).

create table if not exists public.members (
  email text primary key check (email = lower(email) and email like '%@%'),
  name text unique check (name in ('Herru','Aries','Ferry','Fanny','Ari','Aldo','Aad')),
  is_admin boolean not null default false,
  added_at timestamptz not null default now()
);
alter table public.members enable row level security;

insert into public.members (email, is_admin) values ('renrasfuldi@gmail.com', true)
on conflict (email) do update set is_admin = true;

create or replace function public.is_member()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.members where email = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;

create or replace function public.is_admin()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.members where is_admin and email = lower(coalesce(auth.jwt() ->> 'email', '')));
$$;

-- Members can see the list (7 friends); changes only through the functions below.
drop policy if exists members_read on public.members;
create policy members_read on public.members for select to authenticated using (public.is_member());

-- Before-user-created hook: only invited emails get an account.
create or replace function public.hook_before_user_created(event jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare addr text := lower(trim(coalesce(event -> 'user' ->> 'email', '')));
begin
  if addr <> '' and exists (select 1 from public.members where email = addr) then
    return '{}'::jsonb;
  end if;
  return jsonb_build_object('error', jsonb_build_object('http_code', 403,
    'message', 'Bandiecoot cuma buat 7 orang. Minta diundang dulu.'));
end; $$;
revoke execute on function public.hook_before_user_created(jsonb) from public, anon, authenticated;
grant execute on function public.hook_before_user_created(jsonb) to supabase_auth_admin;
grant usage on schema public to supabase_auth_admin;
grant select on public.members to supabase_auth_admin;

create or replace function public.whoami()
returns jsonb language sql stable security definer set search_path = '' as $$
  select coalesce((select jsonb_build_object('member', true, 'admin', is_admin, 'name', name, 'email', email)
                   from public.members where email = lower(coalesce(auth.jwt() ->> 'email', ''))),
                  jsonb_build_object('member', false));
$$;

create or replace function public.set_my_name(p_name text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_member() then raise exception 'Belum diundang' using errcode = '42501'; end if;
  if exists (select 1 from public.members where name = p_name and email <> lower(auth.jwt() ->> 'email')) then
    raise exception 'Nama itu sudah dipakai anggota lain';
  end if;
  update public.members set name = p_name where email = lower(auth.jwt() ->> 'email');
end; $$;

create or replace function public.add_member(p_email text)
returns void language plpgsql security definer set search_path = '' as $$
declare addr text := lower(trim(p_email));
begin
  if not public.is_admin() then raise exception 'Cuma admin yang bisa mengundang' using errcode = '42501'; end if;
  if addr !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'Itu bukan alamat email'; end if;
  if not exists (select 1 from public.members where email = addr) and (select count(*) from public.members) >= 7 then
    raise exception 'Sudah 7 orang. Bandiecoot penuh.';
  end if;
  insert into public.members (email) values (addr) on conflict do nothing;
end; $$;

create or replace function public.remove_member(p_email text)
returns void language plpgsql security definer set search_path = '' as $$
declare addr text := lower(trim(p_email));
begin
  if not public.is_admin() then raise exception 'Cuma admin yang bisa menghapus' using errcode = '42501'; end if;
  if addr = lower(auth.jwt() ->> 'email') then raise exception 'Nggak bisa menghapus diri sendiri'; end if;
  delete from public.members where email = addr;
end; $$;

revoke execute on function public.whoami(), public.set_my_name(text), public.add_member(text), public.remove_member(text) from public, anon;
grant execute on function public.whoami(), public.set_my_name(text), public.add_member(text), public.remove_member(text) to authenticated;

-- Shared data
create table if not exists public.items (
  coll text not null check (coll in ('moment','pin','map','song','avatar','relay','lineup','jbmeta','jbstory')),
  id text not null check (length(id) between 1 and 64),
  data jsonb not null,
  updated_at timestamptz not null default now(),
  updated_by uuid default auth.uid() references auth.users (id) on delete set null,
  primary key (coll, id),
  check (pg_column_size(data) < 200000)
);
alter table public.items enable row level security;
drop policy if exists items_read on public.items;
drop policy if exists items_insert on public.items;
drop policy if exists items_update on public.items;
drop policy if exists items_delete on public.items;
create policy items_read   on public.items for select to authenticated using (public.is_member());
create policy items_insert on public.items for insert to authenticated with check (public.is_member());
create policy items_update on public.items for update to authenticated using (public.is_member()) with check (public.is_member());
create policy items_delete on public.items for delete to authenticated using (public.is_member());

create or replace function public.items_touch() returns trigger language plpgsql set search_path = '' as $$
begin new.updated_at := now(); new.updated_by := auth.uid(); return new; end; $$;
drop trigger if exists items_touch on public.items;
create trigger items_touch before insert or update on public.items for each row execute function public.items_touch();

-- 🤘 counter without overwriting someone else's edit
create or replace function public.rock_moment(p_id text)
returns void language sql security definer set search_path = '' as $$
  update public.items set data = jsonb_set(data, '{rock}', to_jsonb(coalesce((data->>'rock')::int, 0) + 1))
  where coll = 'moment' and id = p_id and public.is_member();
$$;
revoke execute on function public.rock_moment(text) from public, anon;
grant execute on function public.rock_moment(text) to authenticated;

alter table public.items replica identity full;
do $$ begin
  alter publication supabase_realtime add table public.items;
exception when duplicate_object then null; end $$;

-- Photos
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('media', 'media', false, 5242880, array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;
drop policy if exists media_read on storage.objects;
drop policy if exists media_write on storage.objects;
drop policy if exists media_update on storage.objects;
drop policy if exists media_delete on storage.objects;
create policy media_read   on storage.objects for select to authenticated using (bucket_id = 'media' and public.is_member());
create policy media_write  on storage.objects for insert to authenticated with check (bucket_id = 'media' and public.is_member());
create policy media_update on storage.objects for update to authenticated using (bucket_id = 'media' and public.is_member());
create policy media_delete on storage.objects for delete to authenticated using (bucket_id = 'media' and public.is_member());
