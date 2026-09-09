"""Phase 8A checkpoint 10 (PHASE8A.md, part א §7): single source of truth
for the API's shared error-response shapes. Extracted out of
scripts/export_openapi.py so a 7th route (POST /api/predict/super-customer)
and, later, phase 9's real routers can all import the SAME dict objects
instead of three copies drifting apart.
"""
from __future__ import annotations

from app.schemas import ErrorDetail, HTTPValidationError

# D11 (phase 9 planning): 401/403/500/503 on every route; 422 only where
# there is a request body to violate.
ERROR_RESPONSES_NO_422: dict = {
    401: {"model": ErrorDetail},
    403: {"model": ErrorDetail},
    500: {"model": ErrorDetail},
    503: {"model": ErrorDetail},
}
ERROR_RESPONSES: dict = {
    **ERROR_RESPONSES_NO_422,
    422: {"model": HTTPValidationError},
}
