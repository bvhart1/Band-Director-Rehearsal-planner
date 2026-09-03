-- Rehearsal Coach schema
-- Run this in the Supabase SQL editor (or via the CLI) on a fresh project.

create table if not exists rehearsals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null,
  audio_path text not null,
  status text not null default 'uploaded'
    check (status in ('uploaded', 'processing', 'analyzed', 'failed')),
  error_message text,
  recorded_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

-- Safe to re-run: adds the column if this table already existed without it.
alter table rehearsals add column if not exists error_message text;

create table if not exists rehearsal_plans (
  id uuid primary key default gen_random_uuid(),
  rehearsal_id uuid not null unique references rehearsals (id) on delete cascade,
  summary text not null,
  created_at timestamptz not null default now()
);

create table if not exists drill_items (
  id uuid primary key default gen_random_uuid(),
  rehearsal_id uuid not null references rehearsals (id) on delete cascade,
  title text not null,
  description text not null,
  priority text not null check (priority in ('high', 'medium', 'low')),
  suggested_minutes integer not null default 5,
  measures text,
  done boolean not null default false,
  created_at timestamptz not null default now()
);

alter table rehearsals enable row level security;
alter table rehearsal_plans enable row level security;
alter table drill_items enable row level security;

create policy "Directors manage their own rehearsals"
  on rehearsals for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Directors read plans for their own rehearsals"
  on rehearsal_plans for select
  using (
    exists (
      select 1 from rehearsals
      where rehearsals.id = rehearsal_plans.rehearsal_id
      and rehearsals.user_id = auth.uid()
    )
  );

create policy "Directors manage drill items for their own rehearsals"
  on drill_items for all
  using (
    exists (
      select 1 from rehearsals
      where rehearsals.id = drill_items.rehearsal_id
      and rehearsals.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1 from rehearsals
      where rehearsals.id = drill_items.rehearsal_id
      and rehearsals.user_id = auth.uid()
    )
  );

-- Storage bucket for uploaded rehearsal audio.
-- Create the bucket "rehearsal-audio" (private) in the Supabase dashboard, then apply:
insert into storage.buckets (id, name, public)
values ('rehearsal-audio', 'rehearsal-audio', false)
on conflict (id) do nothing;

create policy "Directors upload to their own folder"
  on storage.objects for insert
  with check (
    bucket_id = 'rehearsal-audio'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy "Directors read their own audio"
  on storage.objects for select
  using (
    bucket_id = 'rehearsal-audio'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
