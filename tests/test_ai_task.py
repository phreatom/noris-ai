"""Tests for the noris AI task entity."""

from unittest.mock import AsyncMock, MagicMock

from openai import BadRequestError
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
import pytest
import voluptuous as vol

from homeassistant.components import ai_task
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import setup_integration

ENTITY_ID = "ai_task.test_task"


def _completion(content: str) -> ChatCompletion:
    return ChatCompletion(
        id="c",
        created=0,
        model="test",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage(role="assistant", content=content),
            )
        ],
    )


async def test_generate_text(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_ai_task
) -> None:
    await setup_integration(hass, mock_config_entry_with_ai_task)
    mock_openai.chat.completions.create = AsyncMock(
        return_value=_completion("Freitext-Ergebnis")
    )

    result = await ai_task.async_generate_data(
        hass, task_name="t", entity_id=ENTITY_ID, instructions="Sag was"
    )

    assert result.data == "Freitext-Ergebnis"
    kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert kwargs["max_tokens"] == 8000
    assert "stream" not in kwargs


async def test_generate_structured_data(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_ai_task
) -> None:
    await setup_integration(hass, mock_config_entry_with_ai_task)
    mock_openai.chat.completions.create = AsyncMock(
        return_value=_completion('```json\n{"name": "Flo"}\n```')
    )

    result = await ai_task.async_generate_data(
        hass,
        task_name="t",
        entity_id=ENTITY_ID,
        instructions="Extrahiere",
        structure=vol.Schema({vol.Required("name"): str}),
    )

    assert result.data == {"name": "Flo"}
    # The mock returns valid JSON regardless of what was requested, so
    # without pinning the response_format the `if structure:` branch that
    # builds it in entity.py could be deleted outright and this test would
    # still pass (fork regression pin, folded in from our version).
    response_format = mock_openai.chat.completions.create.call_args.kwargs[
        "response_format"
    ]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "t"
    assert response_format["json_schema"]["strict"] is True
    assert "name" in response_format["json_schema"]["schema"]["properties"]


async def test_structured_fallback_without_response_format(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_ai_task
) -> None:
    """BadRequest on response_format triggers a prompt-based retry."""
    await setup_integration(hass, mock_config_entry_with_ai_task)
    response = MagicMock()
    response.status_code = 400
    mock_openai.chat.completions.create = AsyncMock(
        side_effect=[
            BadRequestError(
                message="response_format not supported",
                response=response,
                body=None,
            ),
            _completion('{"name": "Flo"}'),
        ]
    )

    result = await ai_task.async_generate_data(
        hass,
        task_name="t",
        entity_id=ENTITY_ID,
        instructions="Extrahiere",
        structure=vol.Schema({vol.Required("name"): str}),
    )

    assert result.data == {"name": "Flo"}
    assert mock_openai.chat.completions.create.await_count == 2
    retry_kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert "response_format" not in retry_kwargs
    assert any(
        m["role"] == "system" and "JSON" in str(m["content"])
        for m in retry_kwargs["messages"]
    )


async def test_invalid_json_raises(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_ai_task
) -> None:
    await setup_integration(hass, mock_config_entry_with_ai_task)
    mock_openai.chat.completions.create = AsyncMock(
        return_value=_completion("kein json")
    )

    with pytest.raises(HomeAssistantError, match="parsing"):
        await ai_task.async_generate_data(
            hass,
            task_name="t",
            entity_id=ENTITY_ID,
            instructions="Extrahiere",
            structure=vol.Schema({vol.Required("name"): str}),
        )


async def test_length_finish_without_output_raises(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_ai_task
) -> None:
    """A truncated, empty completion must raise a max_tokens hint instead of
    silently returning no data."""
    await setup_integration(hass, mock_config_entry_with_ai_task)
    truncated = ChatCompletion(
        id="c",
        created=0,
        model="test",
        object="chat.completion",
        choices=[
            Choice(
                index=0,
                finish_reason="length",
                message=ChatCompletionMessage(role="assistant", content=None),
            )
        ],
    )
    mock_openai.chat.completions.create = AsyncMock(return_value=truncated)

    with pytest.raises(HomeAssistantError, match="max_tokens"):
        await ai_task.async_generate_data(
            hass, task_name="t", entity_id=ENTITY_ID, instructions="Sag was"
        )


async def test_bad_request_without_structure_does_not_retry(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_ai_task
) -> None:
    """A BadRequestError on a free-text task propagates without fallback retry."""
    await setup_integration(hass, mock_config_entry_with_ai_task)
    response = MagicMock()
    response.status_code = 400
    mock_openai.chat.completions.create = AsyncMock(
        side_effect=BadRequestError(message="bad request", response=response, body=None)
    )

    with pytest.raises(HomeAssistantError):
        await ai_task.async_generate_data(
            hass, task_name="t", entity_id=ENTITY_ID, instructions="Sag was"
        )

    assert mock_openai.chat.completions.create.await_count == 1
