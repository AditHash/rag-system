"""Simple shared API-key authentication for the demo principal."""

import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException

DEMO_OWNER_ID = "demo-user"


def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """Return the single demo owner when the configured key matches."""
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        raise HTTPException(status_code=503, detail="API key authentication is not configured")
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return DEMO_OWNER_ID
