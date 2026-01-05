from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.artagent.backend.registries.agentstore.base import ModelConfig
from src.aoai.manager import AzureOpenAIManager


@pytest.mark.asyncio
async def test_generate_response_respects_responses_config():
    manager = AzureOpenAIManager(
        api_key="test-key",
        azure_endpoint="https://test.openai.azure.com",
        api_version="2024-02-01",
        enable_tracing=False,
    )
    fake_client = MagicMock()
    fake_client.responses.create = MagicMock(
        return_value=SimpleNamespace(
            id="resp_1",
            model="gpt-5",
            output_text="ok",
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        )
    )
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = MagicMock()
    manager.openai_client = fake_client

    model_config = ModelConfig(
        deployment_id="gpt-5",
        endpoint_preference="responses",
        temperature=0.2,
        top_p=0.8,
        max_tokens=123,
        min_p=0.1,
        typical_p=0.2,
        reasoning_effort="low",
        include_reasoning=True,
        verbosity=1,
    )

    response = await manager.generate_response(
        query="hi",
        model_config=model_config,
        conversation_history=[],
        system_message="system",
    )

    assert response.endpoint_used == "responses"
    fake_client.responses.create.assert_called_once()
    called = fake_client.responses.create.call_args.kwargs
    assert called["model"] == "gpt-5"
    assert called["temperature"] == 0.2
    assert called["top_p"] == 0.8
    assert called["min_p"] == 0.1
    assert called["typical_p"] == 0.2
    assert called["reasoning_effort"] == "low"
    assert called["include_reasoning"] is True
    assert called["verbosity"] == 1
    assert called["max_completion_tokens"] == 123
    assert "max_tokens" not in called


@pytest.mark.asyncio
async def test_generate_response_respects_chat_config():
    manager = AzureOpenAIManager(
        api_key="test-key",
        azure_endpoint="https://test.openai.azure.com",
        api_version="2024-02-01",
        enable_tracing=False,
    )
    fake_client = MagicMock()
    fake_client.responses.create = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = MagicMock(
        return_value=SimpleNamespace(
            id="chat_1",
            model="gpt-4o",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        )
    )
    manager.openai_client = fake_client

    model_config = ModelConfig(
        deployment_id="gpt-4o",
        endpoint_preference="chat",
        temperature=0.3,
        top_p=0.9,
        max_tokens=55,
    )

    response = await manager.generate_response(
        query="hi",
        model_config=model_config,
        conversation_history=[],
        system_message="system",
    )

    assert response.endpoint_used == "chat"
    fake_client.chat.completions.create.assert_called_once()
    called = fake_client.chat.completions.create.call_args.kwargs
    assert called["model"] == "gpt-4o"
    assert called["temperature"] == 0.3
    assert called["top_p"] == 0.9
    assert called["max_tokens"] == 55
    assert "min_p" not in called
