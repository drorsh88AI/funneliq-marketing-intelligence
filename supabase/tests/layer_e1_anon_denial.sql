-- ============================================================
-- Layer E1 -- anon denial, real errors (checkpoint 5, re-run at
-- checkpoint 9 with 3,500 real rows behind the RLS). RUN AS ONE
-- UNIT: single transaction, three DO blocks each with EXCEPTION
-- WHEN insufficient_privilege (no WHEN OTHERS) -- the internal
-- PL/pgSQL savepoint means the outer transaction never stays
-- aborted, so there is no dependency on session affinity between
-- calls. This is the exact block executed at checkpoint 5 on
-- 2026-09-02; reproduced here verbatim, no placeholders.
-- ============================================================

begin;

select set_config('app.start_pid', pg_backend_pid()::text, true);

set local role anon;

do $$
declare
  v_state   text;
  v_message text;
begin
  perform (select count(*) from public.funnel_records);
  raise exception 'UNEXPECTED: anon was not denied on funnel_records';
exception
  when insufficient_privilege then
    get stacked diagnostics
      v_state = returned_sqlstate,
      v_message = message_text;
    perform set_config('app.t1_state', v_state, true);
    perform set_config('app.t1_message', v_message, true);
end $$;

do $$
declare
  v_state   text;
  v_message text;
begin
  perform (select count(*) from public.followup_insight);
  raise exception 'UNEXPECTED: anon was not denied on followup_insight';
exception
  when insufficient_privilege then
    get stacked diagnostics
      v_state = returned_sqlstate,
      v_message = message_text;
    perform set_config('app.t2_state', v_state, true);
    perform set_config('app.t2_message', v_message, true);
end $$;

do $$
declare
  v_state   text;
  v_message text;
begin
  perform (select count(*) from public.budget_tier_insight);
  raise exception 'UNEXPECTED: anon was not denied on budget_tier_insight';
exception
  when insufficient_privilege then
    get stacked diagnostics
      v_state = returned_sqlstate,
      v_message = message_text;
    perform set_config('app.t3_state', v_state, true);
    perform set_config('app.t3_message', v_message, true);
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
select 'funnel_records_sqlstate',
       '42501',
       coalesce(current_setting('app.t1_state', true), '<not set - DO block did not reach handler>'),
       current_setting('app.t1_state', true) = '42501'
union all
select 'funnel_records_message',
       'permission denied for table funnel_records',
       coalesce(current_setting('app.t1_message', true), '<not set>'),
       current_setting('app.t1_message', true) = 'permission denied for table funnel_records'
union all
select 'followup_insight_sqlstate',
       '42501',
       coalesce(current_setting('app.t2_state', true), '<not set - DO block did not reach handler>'),
       current_setting('app.t2_state', true) = '42501'
union all
select 'followup_insight_message',
       'permission denied for view followup_insight',
       coalesce(current_setting('app.t2_message', true), '<not set>'),
       current_setting('app.t2_message', true) = 'permission denied for view followup_insight'
union all
select 'budget_tier_insight_sqlstate',
       '42501',
       coalesce(current_setting('app.t3_state', true), '<not set - DO block did not reach handler>'),
       current_setting('app.t3_state', true) = '42501'
union all
select 'budget_tier_insight_message',
       'permission denied for view budget_tier_insight',
       coalesce(current_setting('app.t3_message', true), '<not set>'),
       current_setting('app.t3_message', true) = 'permission denied for view budget_tier_insight';

commit;
