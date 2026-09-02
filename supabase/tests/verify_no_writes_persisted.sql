-- ============================================================
-- verify_no_writes_persisted.sql -- durability evidence for Layer D
-- (checkpoint 9). Run in a FRESH call, after layer_d_write_denial.sql
-- has run and rolled back. This is the primary evidence that nothing
-- written in D survived -- not a session-affinity check, and it does
-- not depend on being the same connection as D: it independently
-- re-reads the table's current state from scratch. Run with the
-- owner/service connection (no role switch), so RLS does not filter
-- rows and the counts reflect the whole table.
-- ============================================================

select 'row_count' as check_name,
       '3500' as expected,
       (select count(*) from public.funnel_records)::text as actual,
       (select count(*) from public.funnel_records) = 3500 as pass

union all

select 'row_1_ad_budget_unchanged',
       '2500',
       (select ad_budget::text from public.funnel_records where source_row_id = 1),
       (select ad_budget from public.funnel_records where source_row_id = 1) = 2500;
