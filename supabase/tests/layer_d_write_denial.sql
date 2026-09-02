-- ============================================================
-- Layer D -- three write attempts that must all be denied (checkpoint 9,
-- after the 3,500-row load). RUN AS ONE UNIT: single transaction, three
-- independent DO blocks each with EXCEPTION WHEN insufficient_privilege
-- (no WHEN OTHERS), same pattern proven in layer_e1_anon_denial.sql at
-- checkpoint 5. Ends in ROLLBACK -- see verify_no_writes_persisted.sql
-- for the durability evidence this leaves no side effects.
--
-- Identity: authenticated + organization=northbound (read-allowed,
-- write must still be denied). The INSERT lists all 18 NOT NULL
-- columns explicitly (16 integer + referred + source_row_id), with
-- id given explicitly too, so nextval() on the sequence is never
-- called and no sequence privilege is involved -- the only 42501
-- reachable is the table's own INSERT privilege. source_row_id=999999
-- is unused, so UNIQUE never fires ahead of the ACL check.
-- ============================================================

begin;

select set_config('app.start_pid', pg_backend_pid()::text, true);

set local role authenticated;
set local request.jwt.claims =
  '{"role":"authenticated","app_metadata":{"organization":"northbound"}}';

-- D1: INSERT
do $$
declare
  v_state   text;
  v_message text;
begin
  insert into public.funnel_records (
    id, source_row_id, ad_budget, num_leads, leads_answered, leads_not_answered,
    followup_1, followup_2, followup_3, followup_4, followup_5,
    not_closed, closed, calls_to_closed, calls_to_not_closed,
    customer_acquisition_cost, purchased, upsell, referred
  ) values (
    999999, 999999, 500, 11, 4, 7,
    3, 2, 1, 1, 1,
    0, 0, 0, 0,
    0, 0, 0, 'No'
  );
  raise exception 'UNEXPECTED: northbound was not denied on INSERT';
exception
  when insufficient_privilege then
    get stacked diagnostics
      v_state = returned_sqlstate,
      v_message = message_text;
    perform set_config('app.d1_state', v_state, true);
    perform set_config('app.d1_message', v_message, true);
end $$;

-- D2: UPDATE on an existing row, with a no-op value change.
do $$
declare
  v_state   text;
  v_message text;
begin
  update public.funnel_records set ad_budget = ad_budget where source_row_id = 1;
  raise exception 'UNEXPECTED: northbound was not denied on UPDATE';
exception
  when insufficient_privilege then
    get stacked diagnostics
      v_state = returned_sqlstate,
      v_message = message_text;
    perform set_config('app.d2_state', v_state, true);
    perform set_config('app.d2_message', v_message, true);
end $$;

-- D3: DELETE on the same existing row.
do $$
declare
  v_state   text;
  v_message text;
begin
  delete from public.funnel_records where source_row_id = 1;
  raise exception 'UNEXPECTED: northbound was not denied on DELETE';
exception
  when insufficient_privilege then
    get stacked diagnostics
      v_state = returned_sqlstate,
      v_message = message_text;
    perform set_config('app.d3_state', v_state, true);
    perform set_config('app.d3_message', v_message, true);
end $$;

reset role;
reset request.jwt.claims;

select 'same_pid' as check_name,
       current_setting('app.start_pid') as expected,
       pg_backend_pid()::text as actual,
       pg_backend_pid()::text = current_setting('app.start_pid') as pass
union all
select 'current_user_equals_session_user',
       session_user::text, current_user::text,
       current_user = session_user
union all
select 'role_reset',
       'none', coalesce(current_setting('role', true), '<null>'),
       coalesce(current_setting('role', true), 'none') = 'none'
union all
select 'claims_safe',
       'NULL, empty, or valid JSON',
       coalesce(nullif(current_setting('request.jwt.claims', true), ''), '<null-or-empty>'),
       current_setting('request.jwt.claims', true) is null
         or current_setting('request.jwt.claims', true) = ''
         or pg_input_is_valid(current_setting('request.jwt.claims', true), 'jsonb')
union all
select 'insert_sqlstate', '42501',
       coalesce(current_setting('app.d1_state', true), '<not set - handler not reached>'),
       current_setting('app.d1_state', true) = '42501'
union all
select 'insert_message', 'contains funnel_records, not sequence',
       coalesce(current_setting('app.d1_message', true), '<not set>'),
       current_setting('app.d1_message', true) ilike '%funnel_records%'
         and current_setting('app.d1_message', true) not ilike '%sequence%'
union all
select 'update_sqlstate', '42501',
       coalesce(current_setting('app.d2_state', true), '<not set - handler not reached>'),
       current_setting('app.d2_state', true) = '42501'
union all
select 'update_message', 'contains funnel_records, not sequence',
       coalesce(current_setting('app.d2_message', true), '<not set>'),
       current_setting('app.d2_message', true) ilike '%funnel_records%'
         and current_setting('app.d2_message', true) not ilike '%sequence%'
union all
select 'delete_sqlstate', '42501',
       coalesce(current_setting('app.d3_state', true), '<not set - handler not reached>'),
       current_setting('app.d3_state', true) = '42501'
union all
select 'delete_message', 'contains funnel_records, not sequence',
       coalesce(current_setting('app.d3_message', true), '<not set>'),
       current_setting('app.d3_message', true) ilike '%funnel_records%'
         and current_setting('app.d3_message', true) not ilike '%sequence%'
union all
select 'row_count_unchanged', '3500',
       (select count(*)::text from public.funnel_records),
       (select count(*) from public.funnel_records) = 3500
union all
select 'row_1_ad_budget_unchanged', '2500',
       (select ad_budget::text from public.funnel_records where source_row_id = 1),
       (select ad_budget from public.funnel_records where source_row_id = 1) = 2500;

rollback;
