-- Chay 1 lan trong Supabase -> SQL Editor -> New query -> Run
create table if not exists public.us_ai_jobs (
  job_id       text primary key,
  source       text,
  title        text,
  company      text,
  location     text,
  region       text,
  is_us        boolean,
  salary       text,
  tags         text,
  url          text,
  repl_kw      text,          -- keyword nghe AI lam thay duoc
  ai_skill_kw  text,          -- keyword nghe ve AI (build AI)
  first_seen   timestamptz default now(),   -- giu nguyen lan dau thay
  crawled_at   timestamptz default now()    -- cap nhat moi lan crawl
);

create index if not exists idx_us_ai_jobs_is_us   on public.us_ai_jobs (is_us);
create index if not exists idx_us_ai_jobs_crawled on public.us_ai_jobs (crawled_at desc);

-- Xem job My moi nhat:
--   select title, company, region, salary, repl_kw, url
--   from public.us_ai_jobs where is_us order by crawled_at desc limit 50;
