-- Kamar: each person's room layout (coll 'room', id = name).
alter table public.items drop constraint if exists items_coll_check;
alter table public.items add constraint items_coll_check check (coll in ('moment','pin','map','song','avatar','relay','lineup','jbmeta','jbstory','bike','quiz','quizres','placepic','chat','tamiya','room'));
