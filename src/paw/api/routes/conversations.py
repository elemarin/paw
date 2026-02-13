"""Conversations API — list, get, delete conversations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from paw.api.middleware.auth import verify_api_key

router = APIRouter()


@router.get("/v1/conversations")
async def list_conversations(
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
):
    """List all conversations."""
    conversations = request.app.state.conversations
    return conversations.list_all()


@router.delete("/v1/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    _api_key: str | None = Depends(verify_api_key),
):
    """Delete a conversation."""
    conversations = request.app.state.conversations
    if conversations.delete(conversation_id):
        return {"status": "deleted", "id": conversation_id}
    return {"status": "not_found", "id": conversation_id}
