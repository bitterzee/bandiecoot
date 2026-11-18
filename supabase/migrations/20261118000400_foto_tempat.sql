-- Real photos of places on the Nostalgia maps: one row per photo (coll 'placepic').
alter table public.items drop constraint if exists items_coll_check;
alter table public.items add constraint items_coll_check check (coll in ('moment','pin','map','song','avatar','relay','lineup','jbmeta','jbstory','bike','quiz','quizres','placepic'));
