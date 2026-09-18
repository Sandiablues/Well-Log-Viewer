"""
Source Intake API compatibility shell.

The Source Intake routes were split into focused route modules during the
hardening pass. This module intentionally remains as an empty router so existing
main.py registration order stays stable while no route ownership remains here.
"""

from __future__ import annotations

from fastapi import APIRouter


router = APIRouter(prefix="/api/source-intake", tags=["source-intake"])
