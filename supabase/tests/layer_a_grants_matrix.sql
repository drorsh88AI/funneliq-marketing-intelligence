-- ============================================================
-- Layer A -- grants matrix (checkpoint 5; not data-dependent)
-- RUN AS ONE UNIT. Read-only catalog functions, no transaction
-- needed, nothing can error. 36 table/view rows + 2 sequence rows
-- = 38, all expected 'pass' = true.
-- ============================================================

select r.rolname, o.obj, p.priv,
       has_table_privilege(r.rolname, o.obj, p.priv) as actual,
       case
         when r.rolname = 'authenticated' and p.priv = 'SELECT'
           then true
         when r.rolname = 'service_role' and o.obj = 'public.funnel_records'
              and p.priv in ('SELECT','INSERT','UPDATE')
           then true
         else false
       end as expected,
       has_table_privilege(r.rolname, o.obj, p.priv) = case
         when r.rolname = 'authenticated' and p.priv = 'SELECT'
           then true
         when r.rolname = 'service_role' and o.obj = 'public.funnel_records'
              and p.priv in ('SELECT','INSERT','UPDATE')
           then true
         else false
       end as pass
from   (values ('anon'),('authenticated'),('service_role')) as r(rolname)
cross join (values ('public.funnel_records'),
                   ('public.followup_insight'),
                   ('public.budget_tier_insight')) as o(obj)
cross join (values ('SELECT'),('INSERT'),('UPDATE'),('DELETE')) as p(priv)

union all

select 'service_role' as rolname, 'public.funnel_records_id_seq' as obj, priv,
       has_sequence_privilege('service_role', 'public.funnel_records_id_seq', priv) as actual,
       true as expected,
       has_sequence_privilege('service_role', 'public.funnel_records_id_seq', priv) as pass
from (values ('usage'), ('select')) as p(priv);
