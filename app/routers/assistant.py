# app/routers/assistant.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# AI Officer Copilot / Personal Journal — Multi-turn Gemini Assistant
#
# All endpoints are protected by Firebase Authentication (get_current_officer).
# Every conversation is scoped to the verified Firebase UID — never the browser.
# =====================================================================

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services.firebase_auth import get_current_officer
from app.services.firestore_service import (
    create_conversation,
    add_message,
    get_conversation,
    get_conversation_messages,
    list_conversations,
    update_conversation,
)
from app.services.gemini_assistant import gemini_assistant
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/assistant", tags=["AI Assistant"])


# ─────────────────────────────────────────────
# List conversations
# ─────────────────────────────────────────────

@router.get(
    "/conversations",
    summary="List user's AI conversations",
    description="Returns the authenticated officer's conversation history, newest first.",
)
async def api_list_conversations(
    officer: dict = Depends(get_current_officer),
    max_results: int = Query(20, ge=1, le=50),
):
    uid = officer["uid"]
    convs = list_conversations(uid, max_results=max_results)
    return {"conversations": convs, "count": len(convs)}


# ─────────────────────────────────────────────
# Create conversation
# ─────────────────────────────────────────────

@router.post(
    "/conversations",
    summary="Start a new AI conversation",
    status_code=status.HTTP_201_CREATED,
)
async def api_create_conversation(
    officer: dict = Depends(get_current_officer),
    title: str = Query("", description="Optional conversation title"),
):
    uid = officer["uid"]
    conversation_id = create_conversation(uid, title=title)
    if not conversation_id:
        raise HTTPException(status_code=503, detail="Firestore unavailable")
    return {"conversation_id": conversation_id, "title": title or "नई चर्चा"}


# ─────────────────────────────────────────────
# Get conversation (with messages)
# ─────────────────────────────────────────────

@router.get(
    "/conversations/{conversation_id}",
    summary="Get conversation with messages",
)
async def api_get_conversation(
    conversation_id: str,
    officer: dict = Depends(get_current_officer),
):
    uid = officer["uid"]
    conv = get_conversation(uid, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(uid, conversation_id)
    return {"conversation": conv, "messages": messages}


# ─────────────────────────────────────────────
# Send a message (real multi-turn Gemini)
# ─────────────────────────────────────────────

@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Send a message and get Gemini response (multi-turn)",
)
async def api_send_message(
    conversation_id: str,
    payload: dict,
    officer: dict = Depends(get_current_officer),
):
    uid = officer["uid"]
    user_message = (payload.get("content") or "").strip()
    if not user_message:
        raise HTTPException(status_code=422, detail="content is required")

    # Verify the conversation belongs to this officer
    conv = get_conversation(uid, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Conversation is already completed")

    # Persist the user message
    add_message(uid, conversation_id, "user", user_message)

    # Build full history for Gemini multi-turn context
    all_messages = get_conversation_messages(uid, conversation_id)
    history = [{"role": m["role"], "content": m["content"]} for m in all_messages]

    # Call Gemini (multi-turn — the full history is sent)
    result = gemini_assistant.generate_response(history[:-1], user_message)

    if result.get("success"):
        response_text = result["content"]
        add_message(uid, conversation_id, "assistant", response_text)
        return {
            "response": response_text,
            "latency_ms": result.get("latency_ms"),
            "message_count": len(all_messages) + 1,
        }
    else:
        return {
            "response": "⚠️ " + (result.get("error") or "AI service unavailable. Please try again."),
            "latency_ms": None,
            "message_count": len(all_messages) + 1,
        }


# ─────────────────────────────────────────────
# End conversation (triggers summary + action plan)
# ─────────────────────────────────────────────

@router.post(
    "/conversations/{conversation_id}/end",
    summary="End conversation and generate summary + action plan",
)
async def api_end_conversation(
    conversation_id: str,
    officer: dict = Depends(get_current_officer),
):
    uid = officer["uid"]
    conv = get_conversation(uid, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conv.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Conversation already ended")

    # Get full history
    all_messages = get_conversation_messages(uid, conversation_id)
    history = [{"role": m["role"], "content": m["content"]} for m in all_messages]

    # Generate structured intelligence (summary + field insights + action plan)
    intel = gemini_assistant.generate_intelligence(history)
    now = datetime.now(timezone.utc).isoformat()

    if intel.get("success"):
        bundle = intel["bundle"]
        update_data = {
            "status": "completed",
            "summary": bundle.summary.model_dump(),
            "field_insights": [i.model_dump() for i in bundle.field_insights],
            "action_plan": [p.model_dump() for p in bundle.action_plan],
            "summary_generated_at": now,
            "summary_status": "success",
            "updated_at": now,
        }
        update_conversation(uid, conversation_id, update_data)
        return {
            "summary": update_data["summary"],
            "field_insights": update_data["field_insights"],
            "action_plan": update_data["action_plan"],
            "summary_status": "success",
            "summary_generated_at": now,
        }
    else:
        update_data = {
            "status": "completed",
            "summary_status": "error",
            "updated_at": now,
        }
        update_conversation(uid, conversation_id, update_data)
        return {
            "summary_status": "error",
            "message": intel.get("error", "AI intelligence generation failed"),
        }


# ─────────────────────────────────────────────
# Get summary
# ─────────────────────────────────────────────

@router.get(
    "/conversations/{conversation_id}/summary",
    summary="Get conversation summary",
)
async def api_get_summary(
    conversation_id: str,
    officer: dict = Depends(get_current_officer),
):
    uid = officer["uid"]
    conv = get_conversation(uid, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "summary": conv.get("summary", ""),
        "field_insights": conv.get("field_insights", []),
        "action_plan": conv.get("action_plan", []),
        "summary_status": conv.get("summary_status"),
        "status": conv.get("status"),
    }