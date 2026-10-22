import uuid
from typing import Any
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import RequestContext, require_authenticated_user
from app.llm.base import ImageAttachment
from app.llm.factory import SUPPORTED_PROVIDERS
from app.memory.session_store import session_store
from app.services.agent_orchestrator import (
    ChatTurnResult,
    agent_orchestrator,
)
from app.tools.base_tool import tool_registry

chat_router = APIRouter(prefix="/api/v1/chat", tags=["AI Assistant Chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="Customer natural language prompt")
    session_id: str = Field(
        default_factory=lambda: f"sess-{uuid.uuid4().hex[:12]}",
        description="Conversation session ID for Redis sliding-window memory",
    )
    model_provider: str | None = Field(
        default=None,
        description="Optional LLM provider override (claude, openai, gemini, local)",
    )
    images: list[ImageAttachment] = Field(
        default_factory=list,
        description="Optional base64 or URL images for multimodal damaged-product inspection",
    )


@chat_router.post("", response_model=ChatTurnResult)
async def chat_endpoint(
    request: ChatRequest,
    _ctx: RequestContext = Depends(require_authenticated_user),
) -> ChatTurnResult:
    """Synchronous agentic chat endpoint with multi-step Tool Calling, RAG, and PII masking."""
    return await agent_orchestrator.process_turn(
        session_id=request.session_id,
        message=request.message,
        images=request.images,
        model_provider=request.model_provider,
    )


@chat_router.post("/stream")
async def chat_stream_endpoint(
    request: ChatRequest,
    _ctx: RequestContext = Depends(require_authenticated_user),
) -> StreamingResponse:
    """Server-Sent Events (SSE) streaming chat endpoint for typewriter effect."""
    generator = agent_orchestrator.stream_turn(
        session_id=request.session_id,
        message=request.message,
        images=request.images,
        model_provider=request.model_provider,
    )
    return StreamingResponse(generator, media_type="text/event-stream")


@chat_router.get("/sessions/{session_id}")
async def get_session_history(
    session_id: str,
    ctx: RequestContext = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Retrieves the sliding-window conversation history for the authenticated user's session."""
    messages = await session_store.get_history(user_id=ctx.user_id, session_id=session_id)
    return {
        "sessionId": session_id,
        "userId": ctx.user_id,
        "messageCount": len(messages),
        "messages": [m.model_dump() for m in messages],
    }


@chat_router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_session_history(
    session_id: str,
    ctx: RequestContext = Depends(require_authenticated_user),
) -> Response:
    """Clears the Redis conversation history for the specified session."""
    await session_store.clear_session(user_id=ctx.user_id, session_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@chat_router.get("/tools")
async def list_registered_tools(
    _ctx: RequestContext = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Lists all registered agentic tools and supported LLM providers."""
    defs = tool_registry.get_definitions()
    return {
        "supportedProviders": list(SUPPORTED_PROVIDERS),
        "toolCount": len(defs),
        "tools": [d.model_dump() for d in defs],
    }
