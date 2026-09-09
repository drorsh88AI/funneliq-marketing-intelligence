"""Phase 9 -- the two Supabase-backed insight routes (PHASE9.md D1):
GET /api/insights/followup (checkpoint 9) and GET /api/insights/budget-tiers
(checkpoint 8).
"""
from __future__ import annotations

from collections import Counter

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from postgrest.exceptions import APIError
from supabase import Client

from app.api_contract import ERROR_RESPONSES_NO_422
from app.auth import bearer, current_user
from app.schemas import (
    BudgetTiersResponse,
    CallsBucket,
    CallsDistribution,
    CallsPart,
    FollowupResponse,
    FunnelStage,
    PartError,
    PartUnavailable,
    StagesPart,
    TierRow,
)
from app.supabase_client import (
    fetch_all_rows,
    get_user_client,
    independent_purchased_count,
    status_for_supabase_error,
)

router = APIRouter()


def _tier_sort_key(row: dict) -> tuple[int, int]:
    """D15: tier_order ascending, the NULL-tier gap row (if it appears
    at all) always last -- the view itself has no ORDER BY (D12 finding
    11), so this is the second, independent guarantee: even though the
    query below now sends its own `.order()` explicitly (criterion 71),
    that request-level ordering is a PostgREST-side hint, not something
    this test suite's mocks (or, defensively, a future view change) can
    be trusted to honor -- so the response is always re-sorted here
    regardless of what order the rows arrived in."""
    tier_order = row["tier_order"]
    return (1, 0) if tier_order is None else (0, tier_order)


@router.get(
    "/api/insights/budget-tiers",
    response_model=BudgetTiersResponse,
    dependencies=[Depends(bearer)],
    responses=ERROR_RESPONSES_NO_422,
)
def insights_budget_tiers(
    user: dict = Depends(current_user),
    client: Client = Depends(get_user_client),
) -> BudgetTiersResponse:
    """PHASE8.md D11: zero rows for an authorized user is 200 + `{"tiers":
    []}` -- a real (if empty) result, never inferred as 401/403. RLS is
    enforced through the view (security_invoker=true, PHASE3.md D4) via
    the caller's own JWT (client comes from get_user_client, D4)."""
    try:
        response = (
            client.table("budget_tier_insight")
            .select("tier_order,budget_tier,n_records,conversion_rate")
            .order("tier_order", nullsfirst=False)
            .retry(False)
            .execute()
        )
    except (APIError, httpx.TransportError) as e:
        status, detail = status_for_supabase_error(e)
        raise HTTPException(status_code=status, detail=detail) from e

    rows = sorted(response.data, key=_tier_sort_key)
    return BudgetTiersResponse(tiers=[TierRow(**row) for row in rows])


# ---------------------------------------------------------------------------
# GET /api/insights/followup (checkpoint 9, D12). Two independently-sourced
# parts (IA.md §7.1): `stages` from the followup_insight view, and
# `calls_to_closed` aggregated server-side from funnel_records. Each part
# is fetched and classified separately into one of three outcomes:
#   "auth"        -- the Supabase call itself failed with a 401/403-class
#                    error (D16). Propagates as a route-level HTTPException,
#                    discarding any data the OTHER part already fetched --
#                    401/403 always outrank a 200 with partial data.
#   "unavailable" -- a non-auth failure (503/TransportError) or a business
#                    invariant violation (wrong stage count/sequence,
#                    aggregation mismatch against the independent count).
#                    Becomes PartUnavailable in the response.
#   "available"   -- real data, wrapped in the part's *Part model.
# ---------------------------------------------------------------------------

def _fetch_stages(client: Client):
    """Returns ("auth", status_code, detail) | ("unavailable", PartError)
    | ("available", StagesPart)."""
    try:
        response = (
            client.table("followup_insight")
            .select("stage_order,stage,from_leads,to_leads,drop_rate")
            .order("stage_order")
            .retry(False)
            .execute()
        )
    except (APIError, httpx.TransportError) as e:
        status, detail = status_for_supabase_error(e)
        if status in (401, 403):
            return ("auth", status, detail)
        return ("unavailable", PartError(reason_code="data_unavailable", message="failed to fetch follow-up stages"))

    rows = sorted(response.data, key=lambda r: r["stage_order"])
    try:
        stages = [FunnelStage(**row) for row in rows]
        part = StagesPart(status="available", data=stages)
    except ValidationError:
        return (
            "unavailable",
            PartError(
                reason_code="data_unavailable",
                message="follow-up stages did not match the expected 5-stage sequence",
            ),
        )
    return ("available", part)


def _fetch_calls_to_closed(client: Client):
    """Returns ("auth", status_code, detail) | ("unavailable", PartError)
    | ("available", CallsPart)."""
    try:
        rows = fetch_all_rows(client, "funnel_records", "calls_to_closed", filters={"purchased": 1})
        independent_count = independent_purchased_count(client)
    except (APIError, httpx.TransportError) as e:
        status, detail = status_for_supabase_error(e)
        if status in (401, 403):
            return ("auth", status, detail)
        return (
            "unavailable",
            PartError(reason_code="data_unavailable", message="failed to fetch calls_to_closed"),
        )

    population_n = len(rows)
    if population_n != independent_count:
        # IA.md §7.1: NEVER validated against len(rows) itself -- that
        # would be circular and let a silently-truncated page pass.
        return (
            "unavailable",
            PartError(
                reason_code="aggregation_mismatch",
                message="paginated calls_to_closed fetch did not match the independent row count",
            ),
        )

    counter = Counter(row["calls_to_closed"] for row in rows)
    buckets = [CallsBucket(calls=calls, n=n) for calls, n in sorted(counter.items())]
    try:
        distribution = CallsDistribution(population_n=population_n, distribution=buckets)
        part = CallsPart(status="available", data=distribution)
    except ValidationError:
        return (
            "unavailable",
            PartError(reason_code="aggregation_mismatch", message="calls_to_closed distribution failed its own consistency check"),
        )
    return ("available", part)


@router.get(
    "/api/insights/followup",
    response_model=FollowupResponse,
    dependencies=[Depends(bearer)],
    responses=ERROR_RESPONSES_NO_422,
)
def insights_followup(
    user: dict = Depends(current_user),
    client: Client = Depends(get_user_client),
) -> FollowupResponse:
    """PHASE9.md D12: 401/403 always outrank a partial 200 -- checked
    across BOTH parts before either is turned into a response, so a
    part that already succeeded is discarded rather than leaked
    alongside an auth failure from the other. Two non-auth failures
    (or invariant violations) in both parts is 503, not 200 with two
    unavailable parts."""
    stages_outcome = _fetch_stages(client)
    calls_outcome = _fetch_calls_to_closed(client)

    auth_failures = [o for o in (stages_outcome, calls_outcome) if o[0] == "auth"]
    if auth_failures:
        status, detail = min((o[1], o[2]) for o in auth_failures)  # 401 outranks 403
        raise HTTPException(status_code=status, detail=detail)

    stages_part = stages_outcome[1] if stages_outcome[0] == "available" else PartUnavailable(
        status="unavailable", error=stages_outcome[1]
    )
    calls_part = calls_outcome[1] if calls_outcome[0] == "available" else PartUnavailable(
        status="unavailable", error=calls_outcome[1]
    )

    if stages_outcome[0] != "available" and calls_outcome[0] != "available":
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    return FollowupResponse(stages=stages_part, calls_to_closed=calls_part)
