-- ============================================================
-- Layer B -- object flags (checkpoint 5; not data-dependent)
-- RUN AS ONE UNIT. relrowsecurity on the table, reloptions
-- (security_invoker=true) on both views. Raw actual value is
-- printed alongside pass so a wording difference does not fail
-- silently.
-- ============================================================

select 'public.funnel_records' as obj, 'relrowsecurity' as flag,
       c.relrowsecurity::text as actual,
       'true' as expected,
       c.relrowsecurity = true as pass
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname = 'funnel_records'

union all

select 'public.followup_insight', 'reloptions',
       coalesce(c.reloptions::text, '<null>'),
       'contains security_invoker=true',
       coalesce(c.reloptions::text, '') like '%security_invoker=true%'
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname = 'followup_insight'

union all

select 'public.budget_tier_insight', 'reloptions',
       coalesce(c.reloptions::text, '<null>'),
       'contains security_invoker=true',
       coalesce(c.reloptions::text, '') like '%security_invoker=true%'
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relname = 'budget_tier_insight';
