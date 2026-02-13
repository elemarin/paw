"""API key authentication middleware."""

from __future__ import annotations

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader
import structlog

logger = structlog.get_logger()

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """Verify the API key if auth is enabled."""
    config_key = request.app.state.config.api_key

    # No auth configured — allow all
    if not config_key:
        return None

    if not api_key:
        logger.warning("auth.missing_key", path=request.url.path)
        raise HTTPException(status_code=401, detail="Missing API key. Provide X-API-Key header.")

    if api_key != config_key:
        logger.warning("auth.invalid_key", path=request.url.path)
        raise HTTPException(status_code=403, detail="Invalid API key.")

    return api_key
