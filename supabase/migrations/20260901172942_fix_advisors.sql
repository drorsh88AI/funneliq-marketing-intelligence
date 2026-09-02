-- Phase 3: fixes for two findings from Supabase's Security + Performance
-- Advisors, run against the live project after the first two migrations.
-- New migration, not an edit of an already-applied one — see
-- docs/planning/PHASE3.md §ד.1 for the full rationale and the advisor
-- output that confirmed both findings.

-- Performance (auth_rls_initplan): auth.jwt() in a RLS policy is
-- re-evaluated once per row. Wrapping it in a scalar subquery lets Postgres
-- evaluate it once per query via an initplan instead.
alter policy funnel_records_northbound_select
  on public.funnel_records
  using ((select auth.jwt()) -> 'app_metadata' ->> 'organization' = 'northbound');

-- Security (anon/authenticated_security_definer_function_executable):
-- public.rls_auto_enable() is a SECURITY DEFINER function created by the
-- project's "Automatic RLS" setting, not by any of our migrations. Its
-- proacl was null, meaning it relied on Postgres's default EXECUTE-to-PUBLIC
-- grant — so anon and authenticated could call it over PostgREST at
-- /rest/v1/rpc/rls_auto_enable. Revoking EXECUTE closes that exposure
-- without touching the platform's own (privileged) trigger that invokes it.
revoke execute on function public.rls_auto_enable()
  from public, anon, authenticated;
