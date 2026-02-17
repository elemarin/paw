"""Health check endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

router = APIRouter()

_start_time = time.time()


@router.get("/health")
async def health(request: Request) -> dict:
    """Health check — returns status, uptime, model info."""
    config = request.app.state.config
    gateway = request.app.state.gateway
    channel_manager = getattr(request.app.state, "channel_manager", None)

    channels: list[dict] = []
    if channel_manager:
        channels = [
            {
                "channel": status.channel,
                "mode": status.mode,
                "enabled": status.enabled,
                "running": status.running,
                "last_error": status.last_error,
                "last_inbound_at": status.last_inbound_at,
                "last_outbound_at": status.last_outbound_at,
            }
            for status in channel_manager.statuses()
        ]

    return {
        "status": "ok",
        "version": "1.0.0",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "model": config.llm.model,
        "llm_stats": gateway.stats,
        "plugins_loaded": len(getattr(request.app.state, "registry", {}).tools)
        if hasattr(request.app.state, "registry")
        else 0,
        "heartbeat": {
            "enabled": config.heartbeat.enabled,
            "interval_minutes": config.heartbeat.interval_minutes,
            "checklist_path": config.heartbeat.checklist_path,
        },
        "channels": channels,
    }
