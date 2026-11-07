from unittest.mock import AsyncMock, MagicMock
import pytest

from app.agent.tools.base import ToolContext
from app.agent.tools.policy import SearchPolicyArgs, SearchPolicyTool
from app.api.answer import AnswerResponse, CitationResponse


def test_search_policy_schema_has_empty_parameters() -> None:
    tool = SearchPolicyTool(rag_service=MagicMock())
    params = tool.definition().parameters
    assert params.get("properties") == {} or len(params.get("properties", {})) == 0
    assert params.get("additionalProperties") is False


@pytest.mark.anyio
async def test_search_policy_tool_answered_produces_terminal_reply() -> None:
    mock_rag = AsyncMock()
    mock_rag.answer.return_value = AnswerResponse(
        status="answered",
        answer="İade süresi 14 gündür [1].",
        citations=[
            CitationResponse(
                number=1,
                chunk_id="chunk-1",
                source_file="iade.pdf",
                page_start=1,
                page_end=1,
                heading_path=["İade Koşulları"],
            )
        ],
    )

    tool = SearchPolicyTool(rag_service=mock_rag)
    ctx = ToolContext(
        user_id="user-1",
        correlation_id="corr-abc",
        question="İade sürem kaç gün?",
    )

    res = await tool.run(SearchPolicyArgs(), ctx)

    assert res.ok is True
    assert res.terminal_reply is not None
    assert res.terminal_reply.kind == "policy_answer"
    assert res.terminal_reply.reply == "İade süresi 14 gündür [1]."
    assert len(res.terminal_reply.citations) == 1
    assert res.terminal_reply.citations[0].source_file == "iade.pdf"

    # Servise kullanıcının orijinal ctx.question'ı iletildi
    mock_rag.answer.assert_called_once_with(
        question="İade sürem kaç gün?",
        correlation_id="corr-abc",
    )


@pytest.mark.anyio
async def test_search_policy_tool_abstained_produces_terminal_abstained() -> None:
    mock_rag = AsyncMock()
    mock_rag.answer.return_value = AnswerResponse(
        status="abstained",
        answer="Bu konuda dokümanlarımızda bilgi bulamadım.",
        abstain_reason="low_retrieval_score",
        citations=[],
    )

    tool = SearchPolicyTool(rag_service=mock_rag)
    ctx = ToolContext(
        user_id="user-1",
        correlation_id=None,
        question="Uzay mekiği satıyor musunuz?",
    )

    res = await tool.run(SearchPolicyArgs(), ctx)

    assert res.ok is True
    assert res.terminal_reply is not None
    assert res.terminal_reply.kind == "abstained"
    assert res.terminal_reply.reply == "Bu konuda dokümanlarımızda bilgi bulamadım."


@pytest.mark.anyio
async def test_search_policy_tool_exception_bubbles_up() -> None:
    mock_rag = AsyncMock()
    mock_rag.answer.side_effect = RuntimeError("Qdrant connection dropped")

    tool = SearchPolicyTool(rag_service=mock_rag)
    ctx = ToolContext(user_id="user-1", correlation_id=None, question="iade")

    # Kesinti abstain değildir; yukarı fırlamalıdır
    with pytest.raises(RuntimeError, match="Qdrant connection dropped"):
        await tool.run(SearchPolicyArgs(), ctx)
