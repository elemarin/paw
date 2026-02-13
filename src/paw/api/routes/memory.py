"""Memory API — direct CRUD for PAW's persistent key-value memory."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from paw.api.middleware.auth import verify_api_key

router = APIRouter()


class MemorySetRequest(BaseModel):
    key: str
    value: str


@router.get("/v1/memory")
async def list_memories(
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
):
    """List all stored memories."""
    memory_tool = request.app.state.memory_tool
    if not memory_tool._store:
        return []
    return [{"key": k, "value": v} for k, v in memory_tool._store.items()]


@router.get("/v1/memory/{key}")
async def get_memory(
    key: str,
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
):
    """Get a specific memory by key."""
    memory_tool = request.app.state.memory_tool
    value = memory_tool._store.get(key)
    if value is None:
        return {"error": "not_found", "key": key}
    return {"key": key, "value": value}


@router.put("/v1/memory")
async def set_memory(
    body: MemorySetRequest,
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
):
    """Store a memory key-value pair."""
    memory_tool = request.app.state.memory_tool
    result = await memory_tool.execute(action="remember", key=body.key, value=body.value)
    return {"status": "ok", "result": result}


@router.delete("/v1/memory/{key}")
async def delete_memory(
    key: str,
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
):
    """Delete a memory by key."""
    memory_tool = request.app.state.memory_tool
    result = await memory_tool.execute(action="forget", key=key)
    return {"status": "ok", "result": result}
