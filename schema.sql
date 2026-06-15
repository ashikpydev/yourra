-- ============================================================
-- YourRA — Supabase schema
-- Run this entire file in the Supabase SQL editor (one-time setup).
-- ============================================================

-- Users get a profile row on first authenticated request (see backend/auth.py)
create table if not exists user_profiles (
  id uuid references auth.users(id) primary key,
  email text not null unique,
  credits_minutes integer default 0,
  trial_used boolean default false,
  trial_ip text,
  is_active integer default 1,       -- 1 = active, 0 = paused (set from admin panel)
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
-- If upgrading an existing project, also run:
-- alter table user_profiles add column if not exists is_active integer default 1;

create table if not exists transcription_jobs (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id) not null,
  status text default 'pending',          -- pending | processing | merging | completed | failed
  progress_pct integer default 0,
  original_filename text,
  audio_r2_key text,
  duration_minutes numeric,
  credits_used integer,
  model_used text,                        -- 'flash' | 'pro'
  transcript_bn text,
  transcript_en text,
  chunk_count integer,
  error_message text,
  respondent_meta text,            -- JSON: survey type + respondent demographics
  created_at timestamptz default now(),
  completed_at timestamptz
);
-- If upgrading an existing project, also run:
-- alter table transcription_jobs add column if not exists respondent_meta text;

create table if not exists credit_transactions (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id) not null,
  minutes_added integer not null,
  transaction_type text not null,         -- 'trial' | 'manual_bkash'
  bkash_reference text,
  notes text,
  activated_by text,
  created_at timestamptz default now()
);

-- One row per IP that has used the free trial, to block repeat trials
create table if not exists trial_ips (
  ip text primary key,
  email text,
  used_at timestamptz default now()
);

-- Manual bKash top-up requests submitted by users, reviewed by admin
create table if not exists pending_payments (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id) not null,
  bundle_name text not null,
  bundle_minutes integer not null,
  bundle_price_bdt numeric not null,
  bkash_trx_id text not null,
  status text default 'pending',          -- pending | approved | rejected
  admin_notes text,
  created_at timestamptz default now(),
  resolved_at timestamptz
);

-- Phase 2: "Request a Service" submissions (SurveyCTO, data processing, etc.)
create table if not exists service_requests (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references user_profiles(id),
  service_type text not null,             -- 'surveycto' | 'data_processing' | 'analysis' | 'manuscript' | 'other'
  description text,
  estimated_size text,
  deadline date,
  contact_email text not null,
  contact_whatsapp text,
  attachment_r2_key text,
  status text default 'new',              -- new | quoted | accepted | in_progress | delivered | cancelled
  quoted_price text,
  admin_notes text,
  created_at timestamptz default now()
);

-- ============================================================
-- Row Level Security
-- ============================================================
alter table user_profiles enable row level security;
alter table transcription_jobs enable row level security;
alter table credit_transactions enable row level security;
alter table pending_payments enable row level security;
alter table service_requests enable row level security;
-- trial_ips has no user-facing access at all (service role only, no policy needed)

-- user_profiles: users can read/update only their own row
create policy "Users can view own profile" on user_profiles
  for select using (auth.uid() = id);
create policy "Users can update own profile" on user_profiles
  for update using (auth.uid() = id);

-- transcription_jobs: users can view/insert only their own jobs
create policy "Users can view own jobs" on transcription_jobs
  for select using (auth.uid() = user_id);
create policy "Users can insert own jobs" on transcription_jobs
  for insert with check (auth.uid() = user_id);

-- credit_transactions: read-only for the owning user
create policy "Users can view own transactions" on credit_transactions
  for select using (auth.uid() = user_id);

-- pending_payments: users can view/insert only their own
create policy "Users can view own payments" on pending_payments
  for select using (auth.uid() = user_id);
create policy "Users can insert own payments" on pending_payments
  for insert with check (auth.uid() = user_id);

-- service_requests: users can view/insert only their own (anonymous requests
-- with user_id null are handled via the service-role key from the backend)
create policy "Users can view own requests" on service_requests
  for select using (auth.uid() = user_id);
create policy "Users can insert own requests" on service_requests
  for insert with check (auth.uid() = user_id);

-- Note: the backend uses the SUPABASE_SERVICE_ROLE_KEY for all writes that
-- need to bypass RLS (e.g., admin actions, background pipeline updates).
-- These policies mainly protect against direct client-side access.

-- ============================================================
-- Indexes
-- ============================================================
create index if not exists idx_jobs_user on transcription_jobs(user_id, created_at desc);
create index if not exists idx_payments_status on pending_payments(status);
create index if not exists idx_requests_status on service_requests(status);
