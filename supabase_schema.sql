create extension if not exists pgcrypto;

create table if not exists public.workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    owner_id uuid not null references auth.users(id) on delete cascade,
    created_at timestamptz not null default now()
);

create table if not exists public.workspace_members (
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    user_id uuid not null references auth.users(id) on delete cascade,
    role text not null default 'member' check (role in ('owner', 'admin', 'member')),
    created_at timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create table if not exists public.reviews (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    created_by uuid not null references auth.users(id),
    filename text not null,
    payload jsonb not null,
    created_at timestamptz not null default now()
);

create table if not exists public.reminders (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    review_id uuid references public.reviews(id) on delete set null,
    title text not null,
    due_date date not null,
    notes text not null default '',
    completed boolean not null default false,
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now()
);

create table if not exists public.share_links (
    id uuid primary key default gen_random_uuid(),
    review_id uuid not null references public.reviews(id) on delete cascade,
    token_hash text not null unique,
    expires_at timestamptz not null,
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now()
);

create table if not exists public.workspace_invites (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references public.workspaces(id) on delete cascade,
    code_hash text not null unique,
    expires_at timestamptz not null,
    created_by uuid not null references auth.users(id),
    created_at timestamptz not null default now()
);

create or replace function public.is_workspace_member(target_workspace uuid)
returns boolean
language sql stable security definer
set search_path = public
as $$
    select exists (
        select 1 from public.workspace_members
        where workspace_id = target_workspace and user_id = auth.uid()
    );
$$;

create or replace function public.get_or_create_workspace()
returns uuid
language plpgsql security definer
set search_path = public
as $$
declare
    target_workspace uuid;
begin
    if auth.uid() is null then
        raise exception 'Authentication required';
    end if;

    select workspace_id into target_workspace
    from public.workspace_members
    where user_id = auth.uid()
    order by created_at
    limit 1;

    if target_workspace is not null then
        return target_workspace;
    end if;

    insert into public.workspaces(name, owner_id)
    values ('My ClauseLens workspace', auth.uid())
    returning id into target_workspace;

    insert into public.workspace_members(workspace_id, user_id, role)
    values (target_workspace, auth.uid(), 'owner');

    return target_workspace;
end;
$$;

alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.reviews enable row level security;
alter table public.reminders enable row level security;
alter table public.share_links enable row level security;
alter table public.workspace_invites enable row level security;

create policy "workspace owners create workspaces" on public.workspaces
    for insert to authenticated with check (owner_id = auth.uid());
create policy "members read workspaces" on public.workspaces
    for select to authenticated using (public.is_workspace_member(id));
create policy "owners update workspaces" on public.workspaces
    for update to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

create policy "members read membership" on public.workspace_members
    for select to authenticated using (public.is_workspace_member(workspace_id));
create policy "owners add themselves" on public.workspace_members
    for insert to authenticated with check (
        user_id = auth.uid() and exists (
            select 1 from public.workspaces w
            where w.id = workspace_id and w.owner_id = auth.uid()
        )
    );

create policy "members read reviews" on public.reviews
    for select to authenticated using (public.is_workspace_member(workspace_id));
create policy "members create reviews" on public.reviews
    for insert to authenticated with check (
        public.is_workspace_member(workspace_id) and created_by = auth.uid()
    );
create policy "authors update reviews" on public.reviews
    for update to authenticated using (created_by = auth.uid())
    with check (created_by = auth.uid() and public.is_workspace_member(workspace_id));
create policy "authors delete reviews" on public.reviews
    for delete to authenticated using (created_by = auth.uid());

create policy "members read reminders" on public.reminders
    for select to authenticated using (public.is_workspace_member(workspace_id));
create policy "members create reminders" on public.reminders
    for insert to authenticated with check (
        public.is_workspace_member(workspace_id) and created_by = auth.uid()
    );
create policy "members update reminders" on public.reminders
    for update to authenticated using (public.is_workspace_member(workspace_id))
    with check (public.is_workspace_member(workspace_id));
create policy "members delete reminders" on public.reminders
    for delete to authenticated using (public.is_workspace_member(workspace_id));

create policy "members read share links" on public.share_links
    for select to authenticated using (
        exists (select 1 from public.reviews r
                where r.id = review_id and public.is_workspace_member(r.workspace_id))
    );
create policy "members create share links" on public.share_links
    for insert to authenticated with check (
        created_by = auth.uid() and exists (
            select 1 from public.reviews r
            where r.id = review_id and public.is_workspace_member(r.workspace_id)
        )
    );
create policy "members delete share links" on public.share_links
    for delete to authenticated using (
        exists (select 1 from public.reviews r
                where r.id = review_id and public.is_workspace_member(r.workspace_id))
    );

create policy "admins manage invites" on public.workspace_invites
    for all to authenticated using (
        exists (select 1 from public.workspace_members m
                where m.workspace_id = workspace_id and m.user_id = auth.uid()
                  and m.role in ('owner', 'admin'))
    ) with check (
        created_by = auth.uid() and exists (
            select 1 from public.workspace_members m
            where m.workspace_id = workspace_id and m.user_id = auth.uid()
              and m.role in ('owner', 'admin')
        )
    );

create or replace function public.join_workspace(invite_code text)
returns uuid
language plpgsql security definer
set search_path = public
as $$
declare
    target_workspace uuid;
begin
    if auth.uid() is null then
        raise exception 'Authentication required';
    end if;

    select workspace_id into target_workspace
    from public.workspace_invites
    where code_hash = encode(digest(invite_code, 'sha256'), 'hex')
      and expires_at > now();

    if target_workspace is null then
        raise exception 'Invite is invalid or expired';
    end if;

    insert into public.workspace_members(workspace_id, user_id, role)
    values (target_workspace, auth.uid(), 'member')
    on conflict (workspace_id, user_id) do nothing;

    return target_workspace;
end;
$$;

create or replace function public.get_shared_review(raw_token text)
returns jsonb
language sql security definer
set search_path = public
as $$
    select r.payload
    from public.share_links s
    join public.reviews r on r.id = s.review_id
    where s.token_hash = encode(digest(raw_token, 'sha256'), 'hex')
      and s.expires_at > now()
    limit 1;
$$;

revoke all on function public.join_workspace(text) from public;
revoke all on function public.get_shared_review(text) from public;
revoke all on function public.get_or_create_workspace() from public;
revoke all on function public.is_workspace_member(uuid) from public;
grant execute on function public.join_workspace(text) to authenticated;
grant execute on function public.get_shared_review(text) to anon, authenticated;
grant execute on function public.get_or_create_workspace() to authenticated;
grant execute on function public.is_workspace_member(uuid) to authenticated;