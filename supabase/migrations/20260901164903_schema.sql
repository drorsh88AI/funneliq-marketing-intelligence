-- Phase 3: funnel_records table, RLS, and grants.
-- SQL for storage, retrieval, permissions and stable aggregates only.
-- No training, CV, SHAP, conformal, bootstrap or calibration here (Python, phase 6).
-- See docs/planning/PHASE3.md §ד for the full rationale, including why every
-- numeric column is `integer` (measured against the CSV, not assumed) and why
-- source_row_id is 1-based.

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

-- Explicit revoke from authenticated too, not just anon/public: this project
-- has "Automatically expose new tables" OFF, so a bare `grant select` alone
-- would already start from zero privileges. The revoke is written anyway so
-- this migration's final permission state does not depend on that project
-- setting — it is deterministic on any project. See PHASE3.md §ד (N10).
revoke all    on public.funnel_records from anon, authenticated, service_role, public;
grant  select on public.funnel_records to   authenticated;

create policy funnel_records_northbound_select
  on public.funnel_records for select to authenticated
  using (auth.jwt() -> 'app_metadata' ->> 'organization' = 'northbound');

-- service_role (used by scripts/load_data.py via the secret key) has
-- BYPASSRLS, but that only bypasses row-level security *policies* — it does
-- not bypass table-level GRANT/REVOKE, and "Automatically expose new tables"
-- being OFF means service_role gets no default privileges either. Without
-- this, the loader's upsert would fail with permission denied.
-- select/insert/update only — the loader upserts, it never deletes, and the
-- Data Contract check (checkpoint 8) reads the table directly, not a view.
grant select, insert, update
  on public.funnel_records
  to service_role;

-- Sequence privileges are a separate ACL namespace from table privileges;
-- bigserial's nextval()/currval() during INSERT needs this explicitly.
-- Revoked first for the same determinism reason as the table above — this
-- migration's final state must not depend on a project's default privileges.
revoke all on sequence public.funnel_records_id_seq
  from anon, authenticated, service_role, public;

grant usage, select
  on sequence public.funnel_records_id_seq
  to service_role;
