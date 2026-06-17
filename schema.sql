-- ============================================================
-- YourRA — Supabase schema (safe to run multiple times)
-- Run this whole file in the Supabase SQL editor.
-- ============================================================

-- ---- Tables ------------------------------------------------
create table if not exists user_profiles (
  id uuid references auth.users(id) primary key,
  email text not null unique,
  credits_minutes integer default 0,
  trial_used boolean default false,
  trial_ip text,
  is_active integer default 1,        -- 1 = active, 0 = paused
  full_name text,
  organization text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists transcription_jobs (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id) not null,
  status text default 'pending',
  progress_pct integer default 0,
  original_filename text,
  audio_r2_key text,
  duration_minutes numeric,
  credits_used integer,
  model_used text,
  transcript_bn text,
  transcript_en text,
  chunk_count integer,
  error_message text,
  respondent_meta text,
  created_at timestamptz default now(),
  completed_at timestamptz
);

create table if not exists credit_transactions (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id) not null,
  minutes_added integer not null,
  transaction_type text not null,
  bkash_reference text,
  notes text,
  activated_by text,
  created_at timestamptz default now()
);

create table if not exists trial_ips (
  ip text primary key,
  email text,
  used_at timestamptz default now()
);

create table if not exists pending_payments (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id) not null,
  bundle_name text not null,
  bundle_minutes integer not null,
  bundle_price_bdt numeric not null,
  bkash_trx_id text not null,
  status text default 'pending',
  admin_notes text,
  created_at timestamptz default now(),
  resolved_at timestamptz
);

create table if not exists service_requests (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id),
  service_type text not null,
  description text,
  estimated_size text,
  deadline date,
  contact_email text not null,
  contact_whatsapp text,
  attachment_r2_key text,
  status text default 'new',
  quoted_price text,
  admin_notes text,
  created_at timestamptz default now()
);

create table if not exists trial_requests (
  id uuid default gen_random_uuid() primary key,
  full_name text,
  email text,
  organization text,
  purpose text,
  status text default 'new',
  created_at timestamptz default now()
);

-- ---- Columns added in later versions (safe if they exist) --
alter table user_profiles add column if not exists is_active integer default 1;
alter table user_profiles add column if not exists full_name text;
alter table user_profiles add column if not exists organization text;
alter table transcription_jobs add column if not exists respondent_meta text;
-- Per-job audio retention chosen by the researcher (1..7 days). Null = use the
-- R2_RETENTION_DAYS default. Audio is auto-deleted after this many days.
alter table transcription_jobs add column if not exists retention_days integer;

-- ---- Row Level Security ------------------------------------
alter table user_profiles enable row level security;
alter table transcription_jobs enable row level security;
alter table credit_transactions enable row level security;
alter table pending_payments enable row level security;
alter table service_requests enable row level security;

drop policy if exists "view own profile" on user_profiles;
create policy "view own profile" on user_profiles for select using (auth.uid() = id);
drop policy if exists "update own profile" on user_profiles;
create policy "update own profile" on user_profiles for update using (auth.uid() = id);

drop policy if exists "view own jobs" on transcription_jobs;
create policy "view own jobs" on transcription_jobs for select using (auth.uid() = user_id);
drop policy if exists "insert own jobs" on transcription_jobs;
create policy "insert own jobs" on transcription_jobs for insert with check (auth.uid() = user_id);

drop policy if exists "view own tx" on credit_transactions;
create policy "view own tx" on credit_transactions for select using (auth.uid() = user_id);

drop policy if exists "view own pay" on pending_payments;
create policy "view own pay" on pending_payments for select using (auth.uid() = user_id);
drop policy if exists "insert own pay" on pending_payments;
create policy "insert own pay" on pending_payments for insert with check (auth.uid() = user_id);

drop policy if exists "view own req" on service_requests;
create policy "view own req" on service_requests for select using (auth.uid() = user_id);
drop policy if exists "insert own req" on service_requests;
create policy "insert own req" on service_requests for insert with check (auth.uid() = user_id);

-- ---- Indexes -----------------------------------------------
create index if not exists idx_jobs_user on transcription_jobs(user_id, created_at desc);
create index if not exists idx_payments_status on pending_payments(status);
create index if not exists idx_requests_status on service_requests(status);
