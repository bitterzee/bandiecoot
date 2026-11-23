-- Tamiya: each person's Mini 4WD setup and best time-trial time (coll 'tamiya', id = name).
alter table public.items drop constraint if exists items_coll_check;
alter table public.items add constraint items_coll_check check (coll in ('moment','pin','map','song','avatar','relay','lineup','jbmeta','jbstory','bike','quiz','quizres','placepic','chat','tamiya'));
