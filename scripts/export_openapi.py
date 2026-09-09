"""Phase 8 -- deterministic OpenAPI export for the locked API contract
(docs/planning/PHASE8.md D1, D.0a).

Builds a ONE-OFF, isolated FastAPI() instance inside this script and
registers the six business routes on it with locked signatures --
response_model, the BearerAuth dependency, and the exact error responses
per route. This app is never run: every handler body is a bare `...`
(never called, since OpenAPI schema generation is purely static). It is
never imported by app/main.py and never registered there (D1) -- Render
deploys straight from `main`, so a route that returned 501 would have
gone live on the real service.

Run directly to (re)write docs/api/openapi.json:
    python scripts/export_openapi.py

tests/test_api_contract.py imports build_app()/export_schema() from here
to run the drift check (criterion 1): re-exporting must reproduce the
locked file byte-for-byte.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.security import HTTPBearer  # noqa: E402

from app.api_contract import ERROR_RESPONSES, ERROR_RESPONSES_NO_422  # noqa: E402
from app.schemas import (  # noqa: E402
    BudgetSimulation,
    BudgetTiersResponse,
    EarlyFunnelInput,
    FollowupResponse,
    FunnelInput,
    LtvPrediction,
    PropensityPrediction,
    SuperCustomerPrediction,
)

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.json"

# D13: the auth.py finding this phase reacts to (Header(default=None) is
# not a security scheme) does NOT get fixed here -- app/auth.py is
# untouched in phase 8. This is the contract's OWN declaration of what
# phase 9's current_user must become. auto_error=False mirrors today's
# behavior: a missing header reaches application code and gets a
# hand-written 401, not FastAPI's automatic one.
bearer = HTTPBearer(scheme_name="BearerAuth", auto_error=False)

# ERROR_RESPONSES/ERROR_RESPONSES_NO_422 moved to app/api_contract.py in
# phase 8A (PHASE8A.md D20) -- single source, now shared with the 7th
# route below and, later, phase 9's real routers. Re-exported under these
# same names (imported above) so nothing else in this file changes.


def build_app() -> FastAPI:
    """A fresh, isolated app with exactly the six locked business routes
    -- never app/main.py's app, never mounted, never started."""
    app = FastAPI(title="FunnelIQ API contract", version="phase-8")

    @app.post(
        "/api/predict/ltv",
        response_model=LtvPrediction,
        dependencies=[Depends(bearer)],
        responses=ERROR_RESPONSES,
    )
    def predict_ltv(body: FunnelInput): ...  # contract-only, never called

    @app.post(
        "/api/predict/upsell",
        response_model=PropensityPrediction,
        dependencies=[Depends(bearer)],
        responses=ERROR_RESPONSES,
    )
    def predict_upsell(body: FunnelInput): ...  # contract-only, never called

    @app.post(
        "/api/predict/referral",
        response_model=PropensityPrediction,
        dependencies=[Depends(bearer)],
        responses=ERROR_RESPONSES,
    )
    def predict_referral(body: FunnelInput): ...  # contract-only, never called

    @app.get(
        "/api/simulate/budget",
        response_model=BudgetSimulation,
        dependencies=[Depends(bearer)],
        responses=ERROR_RESPONSES_NO_422,
    )
    def simulate_budget(): ...  # contract-only, never called; no body (D10)

    @app.get(
        "/api/insights/followup",
        response_model=FollowupResponse,
        dependencies=[Depends(bearer)],
        responses=ERROR_RESPONSES_NO_422,
    )
    def insights_followup(): ...  # contract-only, never called

    @app.get(
        "/api/insights/budget-tiers",
        response_model=BudgetTiersResponse,
        dependencies=[Depends(bearer)],
        responses=ERROR_RESPONSES_NO_422,
    )
    def insights_budget_tiers(): ...  # contract-only, never called

    # Phase 8A (PHASE8A.md D20): additive 7th route -- P4S's own request/
    # response pair, same ERROR_RESPONSES (has a body, so needs 422 too)
    # as the three existing POST routes.
    @app.post(
        "/api/predict/super-customer",
        response_model=SuperCustomerPrediction,
        dependencies=[Depends(bearer)],
        responses=ERROR_RESPONSES,
    )
    def predict_super_customer(body: EarlyFunnelInput): ...  # contract-only, never called

    return app


def export_schema() -> dict:
    """The exact dict tests/test_api_contract.py's drift check (criterion
    1) and field-map check (criterion 5) both work from."""
    return build_app().openapi()


def _serialize(schema: dict) -> str:
    """sort_keys=True so the output is deterministic across runs
    regardless of any incidental dict-ordering differences upstream --
    same content in, byte-identical bytes out, every time."""
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    schema = export_schema()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(_serialize(schema), encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
