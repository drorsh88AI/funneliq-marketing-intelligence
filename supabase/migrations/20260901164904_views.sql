-- Phase 3: runtime insight views for the dashboard.
-- Two views, security_invoker=true so the table's RLS is enforced through
-- them, not bypassed. See docs/planning/PHASE3.md §ה for the full rationale:
--
-- - The unit is a canonical 0-1 ratio, not a percentage. Percentage display
--   is a presentation-layer concern (phase 8/9), not stored here.
-- - stage_order / tier_order are explicit because SQL does not guarantee row
--   order without ORDER BY, and an alphabetical sort would silently render
--   the wrong sequence (High, Low, Mid instead of Low, Mid, High).
-- - followup_insight uses `having count(*) > 0` per stage so a blocked user
--   gets zero rows, not a single NULL row that looks like an empty success.
-- - The 1501-1999 ad_budget gap is not folded into an existing tier: the
--   CASE has no ELSE, so a value in that gap surfaces as its own NULL-tier
--   row instead of being silently absorbed into "Mid".

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
