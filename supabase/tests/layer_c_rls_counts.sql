-- ============================================================
-- Layer C -- RLS row counts under two identity states (checkpoint 9,
-- after the 3,500-row load). Plain SELECT counts, nothing raises an
-- error, so no exception handler is needed -- but this file holds
-- TWO INDEPENDENT transaction units, run as two separate pastes:
-- Supabase's SQL Editor renders only the LAST result set of a
-- multi-statement paste, and each unit needs its own visible row.
--
-- Expected (verified in checkpoint 8): table 3500, followup_insight
-- 5, budget_tier_insight 3, only under authenticated+northbound.
-- Owner/service connections must NOT be used here -- RLS does not
-- apply to the table owner, so the test would be meaningless.
-- ============================================================

-- ---- Unit 1 of 2: authenticated, no organization claim ----
begin;
set local role authenticated;

select 'authenticated_no_org' as state,
       (select count(*) from public.funnel_records)      as rows_table,
       (select count(*) from public.followup_insight)    as rows_followup,
       (select count(*) from public.budget_tier_insight) as rows_tiers,
       (select count(*) from public.funnel_records) = 0
         and (select count(*) from public.followup_insight) = 0
         and (select count(*) from public.budget_tier_insight) = 0
       as pass;

rollback;

-- ============================================================
-- ---- Unit 2 of 2: authenticated, organization = northbound ----
-- PASTE SEPARATELY from Unit 1 above.
-- ============================================================
begin;
set local role authenticated;
set local request.jwt.claims =
  '{"role":"authenticated","app_metadata":{"organization":"northbound"}}';

select 'authenticated_northbound' as state,
       (select count(*) from public.funnel_records)      as rows_table,
       (select count(*) from public.followup_insight)    as rows_followup,
       (select count(*) from public.budget_tier_insight) as rows_tiers,
       (select count(*) from public.funnel_records) = 3500
         and (select count(*) from public.followup_insight) = 5
         and (select count(*) from public.budget_tier_insight) = 3
       as pass;

rollback;
