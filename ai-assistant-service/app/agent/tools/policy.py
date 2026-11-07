"""Search policy tool backed by RAG generation service.

Answers corporate policies (returns, cancellations, delivery terms, warranties).
Any answered or abstained RAG response becomes an immutable terminal reply for the agent.
"""

from typing import Any
from pydantic import BaseModel, ConfigDict

from app.agent.models import AgentReply
from app.agent.tools.base import Tool, ToolContext, ToolResult
from app.api.answer import CitationResponse
from app.core.config import settings
from app.rag.generation.service import RagAnswerService


class SearchPolicyArgs(BaseModel):
    """Empty schema: user query is always taken directly from verified context."""

    model_config = ConfigDict(extra="forbid")


class SearchPolicyTool(Tool):
    """Answers store policy questions using verified document retrieval and citations."""

    name = "search_policy"
    description = (
        "Şirketin iade, iptal, kargo, garanti vb. politika ve genel kural sorularını dokümanlardan cevaplar. "
        "Müşterinin kendi siparişi hakkında kullanma."
    )
    args_model = SearchPolicyArgs

    def __init__(self, rag_service: RagAnswerService, timeout_sec: float | None = None) -> None:
        self._rag_service = rag_service
        self.timeout_sec = (
            timeout_sec if timeout_sec is not None else settings.AGENT_POLICY_TOOL_TIMEOUT_SEC
        )

    async def run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:
        # Karar 4: Modelin ürettiği sorgu değil, kullanıcının maskelenmiş orijinal sorusu iletilir
        rag_resp = await self._rag_service.answer(
            question=ctx.question,
            correlation_id=ctx.correlation_id,
        )

        if rag_resp.status == "answered":
            citations = [
                c if isinstance(c, CitationResponse) else CitationResponse(
                    number=c.number,
                    chunk_id=c.chunk_id,
                    source_file=c.source_file,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    heading_path=getattr(c, "heading_path", []),
                )
                for c in getattr(rag_resp, "citations", [])
            ]
            terminal_reply = AgentReply(
                kind="policy_answer",
                reply=rag_resp.answer,
                citations=citations,
            )
            return ToolResult(
                ok=True,
                data={"durum": "cevaplandi", "ozet": "Politika dokümanlarından yanıt bulundu."},
                terminal_reply=terminal_reply,
            )

        # Abstained durumu
        terminal_reply = AgentReply(
            kind="abstained",
            reply=rag_resp.answer,
            citations=[],
        )
        return ToolResult(
            ok=True,
            data={"durum": "bilgi_bulunamadi", "ozet": "Politika dokümanlarında ilgili bilgi yer almıyor."},
            terminal_reply=terminal_reply,
        )
