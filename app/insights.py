"""Phase 9 -- the two Supabase-backed insight routes (PHASE9.md D1):
GET /api/insights/followup (checkpoint 9) and GET /api/insights/budget-tiers
(checkpoint 8).
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from postgrest.exceptions import APIError
from supabase import Client

from app.api_contract import ERROR_RESPONSES_NO_422
from app.auth import bearer, current_user
from app.schemas import BudgetTiersResponse, TierRow
from app.supabase_client import get_user_client, status_for_supabase_error

router = APIRouter()


def _tier_sort_key(row: dict) -> tuple[int, int]:
    """D15: tier_order ascending, the NULL-tier gap row (if it appears
    at all) always last -- budget_tier_insight has no ORDER BY, so the
    row order postgrest returns is not guaranteed."""
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
            .retry(False)
            .execute()
        )
    except (APIError, httpx.TransportError) as e:
        status, detail = status_for_supabase_error(e)
        raise HTTPException(status_code=status, detail=detail) from e

    rows = sorted(response.data, key=_tier_sort_key)
    return BudgetTiersResponse(tiers=[TierRow(**row) for row in rows])
