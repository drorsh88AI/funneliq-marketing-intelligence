"""Phase 9 -- the two Supabase-backed insight routes (PHASE9.md D1):
GET /api/insights/followup and GET /api/insights/budget-tiers.

Routes are added checkpoint by checkpoint (8, 9) -- this file starts as
the registered-but-empty router so app/main.py's wiring never needs to
change again after checkpoint 4.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
