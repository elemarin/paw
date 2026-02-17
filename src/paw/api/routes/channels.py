"""Channel management endpoints."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from paw.api.middleware.auth import verify_api_key

router = APIRouter()


class ModeRequest(BaseModel):
    mode: str


@router.get("/v1/channels/status")
async def list_channel_status(
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
) -> dict:
    manager = request.app.state.channel_manager
    return {
        "channels": [
            {
                "channel": status.channel,
                "mode": status.mode,
                "enabled": status.enabled,
                "running": status.running,
                "last_error": status.last_error,
                "last_inbound_at": status.last_inbound_at,
                "last_outbound_at": status.last_outbound_at,
            }
            for status in manager.statuses()
        ],
        "heartbeat": {
            "enabled": request.app.state.config.heartbeat.enabled,
            "interval_minutes": request.app.state.config.heartbeat.interval_minutes,
            "checklist_path": request.app.state.config.heartbeat.checklist_path,
        },
    }


@router.post("/v1/channels/telegram/pair-code")
async def create_telegram_pair_code(
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
) -> dict:
    cfg = request.app.state.config.channels.telegram
    if not cfg.pairing_enabled:
        raise HTTPException(status_code=400, detail="Telegram pairing is disabled")
    code = secrets.token_hex(3).upper()
    await request.app.state.db.channel_pairing_code_create(
        channel="telegram",
        code=code,
        ttl_minutes=cfg.pairing_code_ttl_minutes,
    )
    return {"code": code, "ttl_minutes": cfg.pairing_code_ttl_minutes}


@router.get("/v1/channels/{channel}/sessions/{session_key}/mode")
async def get_channel_mode(
    channel: str,
    session_key: str,
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
) -> dict:
    mode = await request.app.state.db.channel_session_mode_get(channel, session_key)
    return {"channel": channel, "session_key": session_key, "mode": mode or "regular"}


@router.post("/v1/channels/{channel}/sessions/{session_key}/mode")
async def set_channel_mode(
    channel: str,
    session_key: str,
    body: ModeRequest,
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
) -> dict:
    mode = body.mode.strip().lower()
    if mode not in {"regular", "smart"}:
        raise HTTPException(status_code=400, detail="mode must be regular or smart")
    await request.app.state.db.channel_session_mode_set(channel, session_key, mode)
    return {"channel": channel, "session_key": session_key, "mode": mode}
