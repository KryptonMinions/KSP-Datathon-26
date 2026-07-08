-- AUTH_ARCHITECTURE_4.md glue table: username -> synthetic email.
-- Supabase Auth only knows email; this is the lookup FastAPI uses to
-- resolve a submitted username to the synthetic, never-shown email before
-- calling signInWithPassword.
create table if not exists public.user_directory (
    username text primary key,
    synthetic_email text not null unique,
    created_at timestamptz not null default now()
);

-- RLS enabled on every table in the public schema (Config section). No
-- policies are defined here on purpose: this table is only ever read or
-- written by FastAPI using the project's secret key, which bypasses RLS.
-- Client roles (authenticated/anon) get zero access by default-deny.
alter table public.user_directory enable row level security;

-- --------------------------------------------------------------------------
-- RLS Policy Pattern (Role-Scoped Rows) -- template for case/record tables.
-- Apply this shape to each table added by the data-schema work; adjust the
-- owning/assigned column name per table.
-- --------------------------------------------------------------------------
--
-- alter table public.<table> enable row level security;
--
-- create policy "investigating_officer_scoped_read"
--     on public.<table> for select
--     using (
--         (auth.jwt() -> 'app_metadata' ->> 'role') = 'investigating_officer'
--         and assigned_officer_id = auth.uid()
--     );
--
-- create policy "supervisor_full_read"
--     on public.<table> for select
--     using ((auth.jwt() -> 'app_metadata' ->> 'role') = 'supervisor');
--
-- create policy "analyst_full_read"
--     on public.<table> for select
--     using ((auth.jwt() -> 'app_metadata' ->> 'role') = 'analyst');
--
-- -- admin: no case/record data access (user-management scope only) --
-- -- deliberately no admin policy on case/record tables.
