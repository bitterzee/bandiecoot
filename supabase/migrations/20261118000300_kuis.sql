-- Kuis Mingguan: the week's quiz (coll 'quiz', id = 2026-W47) and each person's answers (coll 'quizres').
alter table public.items drop constraint if exists items_coll_check;
alter table public.items add constraint items_coll_check check (coll in ('moment','pin','map','song','avatar','relay','lineup','jbmeta','jbstory','bike','quiz','quizres'));
