-- Signed-out visitors don't need the membership helpers.
revoke execute on function public.is_member(), public.is_admin() from public, anon;
grant execute on function public.is_member(), public.is_admin() to authenticated;
