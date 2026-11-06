import asyncio
import pytest

from app.llm.base import ChatMessage
from app.llm.fake import FakeLLMProvider


@pytest.mark.anyio
async def test_fake_llm_sequential_responses_and_calls_recorded() -> None:
    provider = FakeLLMProvider(responses=["Yanıt 1", "Yanıt 2"])
    messages1 = [ChatMessage(role="user", content="Soru 1")]
    messages2 = [ChatMessage(role="user", content="Soru 2")]

    resp1 = await provider.generate(messages1, temperature=0.2, max_tokens=100)
    assert resp1.content == "Yanıt 1"
    assert resp1.provider == "fake"
    assert resp1.model == "fake-llm"
    assert resp1.usage is not None
    assert resp1.usage.input_tokens == 2  # "Soru 1"
    assert resp1.usage.output_tokens == 2  # "Yanıt 1"

    resp2 = await provider.generate(messages2, temperature=0.5, max_tokens=200)
    assert resp2.content == "Yanıt 2"

    assert len(provider.calls) == 2
    assert provider.calls[0]["messages"] == messages1
    assert provider.calls[0]["temperature"] == 0.2
    assert provider.calls[0]["max_tokens"] == 100
    assert provider.calls[1]["messages"] == messages2
    assert provider.calls[1]["temperature"] == 0.5
    assert provider.calls[1]["max_tokens"] == 200

    # Liste bittiğinde RuntimeError fırlatmalı
    with pytest.raises(RuntimeError, match="FakeLLMProvider: yanıt kalmadı"):
        await provider.generate([ChatMessage(role="user", content="Soru 3")])


def test_fake_llm_both_responses_and_responder_raises_value_error() -> None:
    with pytest.raises(ValueError, match="cannot accept both"):
        FakeLLMProvider(
            responses=["Bir"],
            responder=lambda msgs: "Iki",
        )


@pytest.mark.anyio
async def test_fake_llm_custom_responder() -> None:
    def custom_responder(msgs: list[ChatMessage]) -> str:
        return f"Echo: {msgs[-1].content}"

    provider = FakeLLMProvider(responder=custom_responder)
    resp = await provider.generate([ChatMessage(role="user", content="Merhaba dünya")])
    assert resp.content == "Echo: Merhaba dünya"
    assert resp.usage is not None
    assert resp.usage.input_tokens == 2
    assert resp.usage.output_tokens == 3


@pytest.mark.anyio
async def test_fake_llm_raise_on_call() -> None:
    provider = FakeLLMProvider(raise_on_call=TimeoutError("Bağlantı koptu"))
    with pytest.raises(TimeoutError, match="Bağlantı koptu"):
        await provider.generate([ChatMessage(role="user", content="Soru")])


@pytest.mark.anyio
async def test_fake_llm_delay_sec() -> None:
    provider = FakeLLMProvider(responses=["Geç yanıt"], delay_sec=0.1)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.03):
            await provider.generate([ChatMessage(role="user", content="Soru")])
