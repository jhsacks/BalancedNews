create extension if not exists citext;
create table if not exists public.newsletter_subscribers (
  id uuid primary key default gen_random_uuid(),
  email citext unique not null,
  preference text not null check (preference in ('AM','PM','BOTH')),
  active boolean not null default true,
  unsubscribe_token uuid not null default gen_random_uuid(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.newsletter_subscribers enable row level security;
revoke all on public.newsletter_subscribers from anon, authenticated;

create or replace function public.subscribe_newsletter(p_email text, p_preference text)
returns void language plpgsql security definer set search_path=public as $$
begin
  if p_email !~* '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$' then raise exception 'invalid email'; end if;
  if p_preference not in ('AM','PM','BOTH') then raise exception 'invalid preference'; end if;
  insert into newsletter_subscribers(email,preference,active,updated_at)
  values(lower(trim(p_email))::citext,p_preference,true,now())
  on conflict(email) do update set preference=excluded.preference,active=true,updated_at=now();
end; $$;

create or replace function public.unsubscribe_newsletter(p_token uuid)
returns void language plpgsql security definer set search_path=public as $$
begin
  update newsletter_subscribers set active=false,updated_at=now() where unsubscribe_token=p_token;
end; $$;

grant execute on function public.subscribe_newsletter(text,text) to anon;
grant execute on function public.unsubscribe_newsletter(uuid) to anon;
