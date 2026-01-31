-- Phase C: Supabase schema for HealBee (chats, messages, user_memory)
-- Run in Supabase SQL Editor. RLS ensures users only access their own data.

-- Chats: one per conversation
create table if not exists public.chats (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null default 'Chat',
  created_at timestamptz not null default now()
);

-- Messages: one per message in a chat
create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  chat_id uuid not null references public.chats(id) on delete cascade,
  role text not null default 'user',
  content text not null default '',
  created_at timestamptz not null default now()
);

-- User memory: key-value for continuity across chats (e.g. last_symptoms, last_advice)
create table if not exists public.user_memory (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  key text not null,
  value text not null default '',
  updated_at timestamptz not null default now(),
  unique(user_id, key)
);

-- RLS
alter table public.chats enable row level security;
alter table public.messages enable row level security;
alter table public.user_memory enable row level security;

create policy "Users can manage own chats"
  on public.chats for all using (auth.uid() = user_id);

create policy "Users can manage messages in own chats"
  on public.messages for all
  using (exists (select 1 from public.chats where chats.id = messages.chat_id and chats.user_id = auth.uid()));

create policy "Users can manage own user_memory"
  on public.user_memory for all using (auth.uid() = user_id);

-- User profile: persistent personal data (one row per user). Used for context-aware responses only; never for diagnosis.
create table if not exists public.user_profile (
  user_id uuid primary key references auth.users(id) on delete cascade,
  name text,
  age integer,
  gender text check (gender in ('male', 'female', 'other', 'prefer_not_to_say')),
  height_cm integer,
  weight_kg integer,
  medical_history text[] default '{}',
  allergies text[] default '{}',
  chronic_conditions text[] default '{}',
  pregnancy_status boolean,
  additional_notes text,
  updated_at timestamptz not null default now()
);

alter table public.user_profile enable row level security;
create policy "Users can manage own profile"
  on public.user_profile for all using (auth.uid() = user_id);
create index if not exists idx_user_profile_user_id on public.user_profile(user_id);

-- Indexes
create index if not exists idx_chats_user_id on public.chats(user_id);
create index if not exists idx_messages_chat_id on public.messages(chat_id);
create index if not exists idx_user_memory_user_id on public.user_memory(user_id);
