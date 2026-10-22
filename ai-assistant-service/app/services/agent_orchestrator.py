import json
import logging
from typing import Any, AsyncGenerator
from pydantic import BaseModel, Field

from app.core.exceptions import AccessDeniedException, BusinessRuleException, ResourceNotFoundException
from app.core.pii_masker import PIIMasker
from app.core.security import get_request_context, require_authenticated_user
from app.llm.base import BaseLLMProvider, ChatMessage, ImageAttachment
from app.llm.factory import LLMFactory
from app.memory.rag_engine import RAGEngine, rag_engine
from app.memory.session_store import RedisSessionStore, session_store
import app.tools  # noqa: F401 - ensures all agentic tools are registered
from app.tools.base_tool import ToolRegistry, tool_registry

logger = logging.getLogger(__name__)

COMMERCE_SYSTEM_PROMPT = """Sen Commerce Platform'un resmi yapay zeka alışveriş ve satış sonrası destek asistanısın.
Kurallar:
1. Müşterinin sipariş, kargo, fiyat karşılaştırma, 48 saat fiyat koruma iadesi, kupon optimizasyonu, donanım uyumluluğu ve hasarlı ürün iadesi taleplerini sana verilen araçları (tools) çağırarak çöz.
2. Müşteri kimliği (customerId) API Gateway tarafından doğrulanmış X-User-Id başlığından otomatik alınır.
3. Müşteri öfkeli ise veya canlı bir insan temsilciye bağlanmak istiyorsa polemiğe girmeden 'escalate_to_human_support' aracını çağır.
4. Yanıtlarını her zaman nazik, net ve Türkçe olarak ver."""


class ExecutedToolTrace(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class ChatTurnResult(BaseModel):
    session_id: str
    reply: str
    provider_used: str
    model_used: str
    pii_masked: bool = False
    detected_pii_types: list[str] = Field(default_factory=list)
    tools_executed: list[ExecutedToolTrace] = Field(default_factory=list)
    rag_documents_used: list[str] = Field(default_factory=list)
    correlation_id: str


class AgentOrchestrator:
    """
    Coordinates the end-to-end agentic workflow:
      1. PII Masking (Credit Cards, TCKN, IBAN, Secrets)
      2. Redis Sliding-Window Session Memory Load
      3. Semantic RAG Knowledge Context Enrichment
      4. Multi-Step Tool-Calling (ReAct) Loop via Pluggable LLM Provider
      5. Session Persistence
    """

    def __init__(
        self,
        store: RedisSessionStore | None = None,
        rag: RAGEngine | None = None,
        registry: ToolRegistry | None = None,
        max_tool_iterations: int = 5,
    ) -> None:
        self.store = store or session_store
        self.rag = rag or rag_engine
        self.registry = registry or tool_registry
        self.max_tool_iterations = max_tool_iterations

    def _build_system_message(self, user_query: str) -> tuple[ChatMessage, list[str]]:
        rag_docs = self.rag.search(user_query, top_k=2)
        doc_ids = [d["docId"] for d in rag_docs]

        if not rag_docs:
            return ChatMessage(role="system", content=COMMERCE_SYSTEM_PROMPT), []

        context_lines = [
            f"[{d['docId']} - {d['title']}]: {d['content']}" for d in rag_docs
        ]
        enriched_prompt = (
            f"{COMMERCE_SYSTEM_PROMPT}\n\n"
            "İlgili Şirket Politikası ve Bilgi Bankası Bağlamı (RAG):\n"
            + "\n".join(context_lines)
        )
        return ChatMessage(role="system", content=enriched_prompt), doc_ids

    async def process_turn(
        self,
        *,
        session_id: str,
        message: str,
        images: list[ImageAttachment] | None = None,
        model_provider: str | None = None,
        llm_provider_instance: BaseLLMProvider | None = None,
    ) -> ChatTurnResult:
        ctx = require_authenticated_user()
        user_id = ctx.user_id

        # 1. Mask sensitive PII before storing in Redis or sending to external LLM
        mask_result = PIIMasker.mask_text(message)
        clean_user_text = mask_result.masked_text

        # 2. Load conversation history from Redis
        history = await self.store.get_history(user_id=user_id, session_id=session_id)

        # 3. Build system message with RAG context
        system_msg, rag_doc_ids = self._build_system_message(clean_user_text)
        user_msg = ChatMessage(
            role="user",
            content=clean_user_text,
            images=images or [],
        )

        working_messages: list[ChatMessage] = [system_msg, *history, user_msg]
        provider = llm_provider_instance or LLMFactory.get_provider(model_provider)
        tool_defs = self.registry.get_definitions()

        executed_tools: list[ExecutedToolTrace] = []
        final_reply = ""

        # 4. Multi-step ReAct / Tool-Calling loop
        for _ in range(self.max_tool_iterations):
            agent_res = await provider.chat(
                messages=working_messages,
                tools=tool_defs,
            )

            if not agent_res.tool_calls:
                final_reply = agent_res.content
                break

            working_messages.append(
                ChatMessage(
                    role="assistant",
                    content=agent_res.content,
                    tool_calls=agent_res.tool_calls,
                )
            )

            for tc in agent_res.tool_calls:
                try:
                    tool_output = await self.registry.execute(tc.tool_name, tc.arguments)
                except AccessDeniedException:
                    # Security/IDOR violations must fail-fast immediately
                    raise
                except (BusinessRuleException, ResourceNotFoundException) as domain_exc:
                    tool_output = {
                        "error": True,
                        "title": domain_exc.title,
                        "detail": domain_exc.detail,
                    }

                executed_tools.append(
                    ExecutedToolTrace(
                        tool_name=tc.tool_name,
                        arguments=tc.arguments,
                        result=tool_output,
                    )
                )
                working_messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=tc.id or tc.tool_name,
                        tool_name=tc.tool_name,
                        content=json.dumps(tool_output, ensure_ascii=False),
                    )
                )
        else:
            # Fallback if max_tool_iterations reached
            if executed_tools and not final_reply:
                last_result = executed_tools[-1].result
                final_reply = str(last_result.get("message") or json.dumps(last_result, ensure_ascii=False))

        # 5. Persist user & assistant turn in Redis sliding window
        await self.store.append_messages(
            user_id=user_id,
            session_id=session_id,
            new_messages=[
                user_msg,
                ChatMessage(role="assistant", content=final_reply),
            ],
        )

        return ChatTurnResult(
            session_id=session_id,
            reply=final_reply,
            provider_used=provider.provider_name,
            model_used=provider.model_name,
            pii_masked=mask_result.was_masked,
            detected_pii_types=mask_result.detected_types,
            tools_executed=executed_tools,
            rag_documents_used=rag_doc_ids,
            correlation_id=get_request_context().correlation_id,
        )

    async def stream_turn(
        self,
        *,
        session_id: str,
        message: str,
        images: list[ImageAttachment] | None = None,
        model_provider: str | None = None,
        llm_provider_instance: BaseLLMProvider | None = None,
    ) -> AsyncGenerator[str, None]:
        result = await self.process_turn(
            session_id=session_id,
            message=message,
            images=images,
            model_provider=model_provider,
            llm_provider_instance=llm_provider_instance,
        )
        words = result.reply.split(" ") if result.reply else []
        for idx, word in enumerate(words):
            token_text = word if idx == len(words) - 1 else f"{word} "
            payload = json.dumps(
                {
                    "token": token_text,
                    "sessionId": result.session_id,
                    "provider": result.provider_used,
                },
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"


agent_orchestrator = AgentOrchestrator()
