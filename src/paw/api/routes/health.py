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

    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "model": config.llm.model,
        "llm_stats": gateway.stats,
        "plugins_loaded": len(getattr(request.app.state, "registry", {}).tools if hasattr(request.app.state, "registry") else []),
    }
