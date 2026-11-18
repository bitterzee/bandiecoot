-- Momen: remember who posted each moment, and who gave it 🤘 (rockBy: {name: taps}).
create or replace function public.rock_moment(p_id text)
returns void language plpgsql security definer set search_path = '' as $$
declare n text;
begin
  select name into n from public.members where email = lower(coalesce(auth.jwt() ->> 'email', ''));
  if n is null then return; end if;
  update public.items
     set data = jsonb_set(
                  jsonb_set(data, '{rock}', to_jsonb(coalesce((data->>'rock')::int, 0) + 1)),
                  '{rockBy}', coalesce(data->'rockBy', '{}'::jsonb) || jsonb_build_object(n, coalesce((data->'rockBy'->>n)::int, 0) + 1))
   where coll = 'moment' and id = p_id;
end; $$;
revoke execute on function public.rock_moment(text) from public, anon;
grant execute on function public.rock_moment(text) to authenticated;

-- moments posted before names were kept: nobody has rocked them yet, so the last editor is the poster
update public.items i set data = i.data || jsonb_build_object('by', m.name)
  from auth.users u join public.members m on m.email = lower(u.email)
 where i.coll = 'moment' and i.updated_by = u.id and i.data->>'by' is null and coalesce((i.data->>'rock')::int, 0) = 0;
