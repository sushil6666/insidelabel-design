create type public.app_role as enum ('admin', 'user');

create table public.user_roles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  role app_role not null,
  unique (user_id, role)
);
grant select on public.user_roles to authenticated;
grant all on public.user_roles to service_role;
alter table public.user_roles enable row level security;
create policy "Users see own roles" on public.user_roles for select to authenticated using (auth.uid() = user_id);

create or replace function public.has_role(_user_id uuid, _role app_role)
returns boolean language sql stable security definer set search_path = public
as $$ select exists (select 1 from public.user_roles where user_id = _user_id and role = _role) $$;

-- The very first account created becomes the admin; later accounts get nothing.
create or replace function public.grant_first_admin()
returns trigger language plpgsql security definer set search_path = public
as $$
begin
  if not exists (select 1 from public.user_roles where role = 'admin') then
    insert into public.user_roles (user_id, role) values (new.id, 'admin');
  end if;
  return new;
end $$;
create trigger on_auth_user_created_first_admin after insert on auth.users
for each row execute function public.grant_first_admin();

create table public.claim_rules (
  id text primary key,
  label text not null,
  match text[] not null default '{}',
  match_regex text,
  check_type text not null,
  terms text[] not null default '{}',
  confidence text not null default 'medium',
  verify boolean not null default true,
  note text not null default '',
  status text not null default 'draft',
  source text not null default 'ai',
  example_claim text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint claim_rules_check_type check (check_type in ('added_sugar_present','preservative_present','subject_absent_or_flavour_only','ingredient_present','not_checkable')),
  constraint claim_rules_status check (status in ('draft','approved','rejected')),
  constraint claim_rules_confidence check (confidence in ('high','medium','low'))
);
grant select on public.claim_rules to anon;
grant select, insert, update, delete on public.claim_rules to authenticated;
grant all on public.claim_rules to service_role;
alter table public.claim_rules enable row level security;
create policy "Anyone reads approved rules" on public.claim_rules for select to anon, authenticated using (status = 'approved');
create policy "Admin reads all rules" on public.claim_rules for select to authenticated using (public.has_role(auth.uid(), 'admin'));
create policy "Admin inserts rules" on public.claim_rules for insert to authenticated with check (public.has_role(auth.uid(), 'admin'));
create policy "Admin updates rules" on public.claim_rules for update to authenticated using (public.has_role(auth.uid(), 'admin')) with check (public.has_role(auth.uid(), 'admin'));
create policy "Admin deletes rules" on public.claim_rules for delete to authenticated using (public.has_role(auth.uid(), 'admin'));

create table public.unmatched_claims (
  id uuid primary key default gen_random_uuid(),
  claim text not null unique,
  times_seen integer not null default 1,
  first_seen timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  status text not null default 'new',
  draft_rule_id text references public.claim_rules(id) on delete set null,
  constraint unmatched_status check (status in ('new','drafted','dismissed'))
);
grant select, update, delete on public.unmatched_claims to authenticated;
grant all on public.unmatched_claims to service_role;
alter table public.unmatched_claims enable row level security;
create policy "Admin reads unmatched" on public.unmatched_claims for select to authenticated using (public.has_role(auth.uid(), 'admin'));
create policy "Admin updates unmatched" on public.unmatched_claims for update to authenticated using (public.has_role(auth.uid(), 'admin')) with check (public.has_role(auth.uid(), 'admin'));
create policy "Admin deletes unmatched" on public.unmatched_claims for delete to authenticated using (public.has_role(auth.uid(), 'admin'));

-- Called server-side only (service role) after a scan.
create or replace function public.record_unmatched_claims(_claims text[])
returns void language sql security definer set search_path = public
as $$
  insert into public.unmatched_claims (claim)
  select distinct lower(trim(c)) from unnest(_claims) c where length(trim(c)) between 2 and 120
  on conflict (claim) do update set times_seen = unmatched_claims.times_seen + 1, last_seen = now();
$$;
revoke execute on function public.record_unmatched_claims(text[]) from public, anon, authenticated;
grant execute on function public.record_unmatched_claims(text[]) to service_role;