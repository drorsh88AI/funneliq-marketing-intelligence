-- FunnelIQ -- schema.sql
--
-- A SNAPSHOT of the final schema state, meant to be run ONCE on an EMPTY
-- Supabase project (see README, local setup): the funnel_records table, row
-- level security, the policy, grants, the two insight views, and one guarded
-- revoke.
--
-- supabase/migrations/ stays the history and the source of truth for the live
-- project. This file is NOT a concatenation of those migrations. It differs
-- from them in two deliberate ways:
--
--   1. The RLS policy is created directly in its final form. Migration
--      20260901172942_fix_advisors.sql later altered it to wrap auth.jwt() in
--      a scalar subquery (the auth_rls_initplan advisor finding); a fresh
--      project has no reason to create the slow form first.
--
--   2. The revoke on public.rls_auto_enable() is wrapped in an existence
--      check. That function is NOT created by any migration: it is created by
--      the Supabase project setting "Automatic RLS". A bare revoke would fail
--      on a project that has the setting off ("function does not exist").
--
-- Not idempotent: running it twice fails on the first CREATE. It does not
-- drop anything and does not touch any other schema.
--
-- tests/test_schema_sql.py checks, statically and without a database, that
-- this file stays derivable from the migrations (so an added migration file,
-- or a change to a migration's statements, fails the test until this file is
-- reviewed; a change to a comment or to formatting does not necessarily fail
-- it). It does NOT execute SQL. Running this file on a clean project has not been done
-- and will not be done in phase 13 (docs/planning/PHASE13.md, D4 and D10).

-- ---------------------------------------------------------------------------
-- The table. Every numeric column is `integer` (measured against the CSV, not
-- assumed) and source_row_id is 1-based. See docs/planning/PHASE3.md.
-- ---------------------------------------------------------------------------

create table public.funnel_records (
  id                        bigserial primary key,
  source_row_id             integer not null unique,
  ad_budget                 integer not null,
  num_leads                 integer not null,
  leads_answered            integer not null,
  leads_not_answered        integer not null,
  followup_1                integer not null,
  followup_2                integer not null,
  followup_3                integer not null,
  followup_4                integer not null,
  followup_5                integer not null,
  not_closed                integer not null,
  closed                    integer not null,
  calls_to_closed           integer not null,
  calls_to_not_closed       integer not null,
  customer_acquisition_cost integer not null,
  ltv_months                integer,
  purchased                 integer not null,
  upsell                    integer not null,
  cumulative_profit         integer,
  referred                  text    not null
);

alter table public.funnel_records enable row level security;

-- Explicit revoke from authenticated too, not just anon/public, so the final
-- permission state does not depend on the project's "Automatically expose new
-- tables" setting.
revoke all    on public.funnel_records from anon, authenticated, service_role, public;
grant  select on public.funnel_records to   authenticated;

-- Only authenticated users whose JWT carries app_metadata.organization =
-- 'northbound' can read rows. (select auth.jwt()) is evaluated once per query
-- instead of once per row.
create policy funnel_records_northbound_select
  on public.funnel_records for select to authenticated
  using ((select auth.jwt()) -> 'app_metadata' ->> 'organization' = 'northbound');

-- service_role (the loader, via the secret key) bypasses RLS policies but not
-- table-level GRANT/REVOKE. select/insert/update only: the loader upserts and
-- never deletes.
grant select, insert, update
  on public.funnel_records
  to service_role;

-- Sequence privileges are a separate ACL namespace from table privileges;
-- bigserial's nextval()/currval() during INSERT needs this explicitly.
revoke all on sequence public.funnel_records_id_seq
  from anon, authenticated, service_role, public;

grant usage, select
  on sequence public.funnel_records_id_seq
  to service_role;

-- ---------------------------------------------------------------------------
-- The two insight views. security_invoker = true so the table's RLS is
-- enforced through them, not bypassed. Units are canonical 0-1 ratios.
-- stage_order / tier_order are explicit because SQL does not guarantee row
-- order without ORDER BY. followup_insight uses `having count(*) > 0` so a
-- blocked user gets zero rows, not one NULL row. The 1501-1999 ad_budget gap
-- is not folded into a tier: the CASE has no ELSE, so it surfaces as its own
-- NULL-tier row.
-- ---------------------------------------------------------------------------

create view public.followup_insight with (security_invoker = true) as
    select 1 as stage_order, 'followup_1' as stage,
           sum(leads_answered) as from_leads, sum(followup_1) as to_leads,
           1 - sum(followup_1)::numeric / nullif(sum(leads_answered), 0) as drop_rate
    from public.funnel_records having count(*) > 0
  union all
    select 2, 'followup_2', sum(followup_1), sum(followup_2),
           1 - sum(followup_2)::numeric / nullif(sum(followup_1), 0)
    from public.funnel_records having count(*) > 0
  union all
    select 3, 'followup_3', sum(followup_2), sum(followup_3),
           1 - sum(followup_3)::numeric / nullif(sum(followup_2), 0)
    from public.funnel_records having count(*) > 0
  union all
    select 4, 'followup_4', sum(followup_3), sum(followup_4),
           1 - sum(followup_4)::numeric / nullif(sum(followup_3), 0)
    from public.funnel_records having count(*) > 0
  union all
    select 5, 'followup_5', sum(followup_4), sum(followup_5),
           1 - sum(followup_5)::numeric / nullif(sum(followup_4), 0)
    from public.funnel_records having count(*) > 0;

create view public.budget_tier_insight with (security_invoker = true) as
select case when ad_budget <= 1500               then 1
            when ad_budget between 2000 and 5000 then 2
            when ad_budget >  5000               then 3    end as tier_order,
       case when ad_budget <= 1500               then 'Low'
            when ad_budget between 2000 and 5000 then 'Mid'
            when ad_budget >  5000               then 'High' end as budget_tier,
       count(*)                                    as n_records,
       avg(closed::numeric / nullif(num_leads, 0)) as conversion_rate
from public.funnel_records
group by 1, 2;

revoke all    on   public.followup_insight, public.budget_tier_insight
              from anon, authenticated, service_role, public;
grant  select on   public.followup_insight, public.budget_tier_insight
              to   authenticated;

-- ---------------------------------------------------------------------------
-- public.rls_auto_enable() is a SECURITY DEFINER function created by the
-- Supabase "Automatic RLS" project setting, not by this file. With no explicit
-- ACL it relies on the default EXECUTE-to-PUBLIC grant, so anon and
-- authenticated could call it over PostgREST. Revoking closes that exposure.
-- The existence check makes this a no-op on a project without the setting.
-- prokind = 'f' keeps it to a plain function: pg_proc also lists procedures,
-- aggregates and window functions, and REVOKE ... ON FUNCTION targets only a
-- function. pronargs = 0 matches the no-argument signature revoked below.
-- ---------------------------------------------------------------------------

do $$
begin
  if exists (
    select 1
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = 'rls_auto_enable'
      and p.pronargs = 0
      and p.prokind = 'f'
  ) then
    revoke execute on function public.rls_auto_enable()
      from public, anon, authenticated;
  end if;
end
$$;
