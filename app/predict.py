"""Phase 9 -- the five prediction/simulation routes (PHASE9.md D1):
POST /api/predict/ltv, /api/predict/upsell, /api/predict/referral,
/api/predict/super-customer, and GET /api/simulate/budget.

Routes are added checkpoint by checkpoint (5, 6, 8) -- this file starts
as the registered-but-empty router so app/main.py's wiring never needs to
change again after checkpoint 4.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
