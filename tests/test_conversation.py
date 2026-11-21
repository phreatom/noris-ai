"""Tests for the noris AI conversation agent."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from openai import APIStatusError
from openai.types.chat.chat_completion_chunk import (
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
import pytest
from pytest_homeassistant.common import MockConfigEntry
import voluptuous as vol

from custom_components.noris_ai.const import (
    CONVERSATION_SUBENTRY_TYPE,
    DEFAULT_CONVERSATION_NAME,
    DOMAIN,
)
from custom_components.noris_ai.entity import MAX_TOOL_ITERATIONS
from homeassistant.components import conversation
from homeassistant.components.llm import AssistAPI
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_MODEL
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er, intent, llm

from .conftest import CHAT_MODEL, setup_integration
from .test_entity_stream import _chunk, _stream

AGENT_ID = "conversation.test_agent"


def _stream_mock(chunks):
    async def _gen() -> AsyncGenerator:
        for chunk in chunks:
            yield chunk

    return AsyncMock(return_value=_gen())


@pytest.fixture
def mock_config_entry_with_llm_api() -> MockConfigEntry:
    """Return a config entry whose conversation subentry enables the Assist LLM API.

    The shared ``mock_config_entry`` fixture's conversation subentry carries
    only ``CONF_MODEL``, so ``chat_log.llm_api`` stays ``None`` and the model
    is never offered tools. This variant adds ``CONF_LLM_HASS_API`` so the
    tool-call loop in ``_async_handle_chat_log`` actually has an LLM API to
    call tools against.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        title="noris AI",
        data={CONF_API_KEY: "sk-bf-test"},
        subentries_data=[
            ConfigSubentryData(
                data={CONF_MODEL: CHAT_MODEL, CONF_LLM_HASS_API: [llm.LLM_API_ASSIST]},
                subentry_type=CONVERSATION_SUBENTRY_TYPE,
                title=DEFAULT_CONVERSATION_NAME,
                unique_id=None,
            ),
        ],
    )


def _conversation_entities(
    hass: HomeAssistant, entry: MockConfigEntry
) -> list[er.RegistryEntry]:
    """Return this config entry's own conversation entities.

    HA's ``conversation`` component always registers a built-in
    ``conversation.home_assistant`` default-agent entity alongside any
    integration's own agent, so filtering ``hass.states`` by domain alone
    also picks that entity up. Filtering by config entry via the entity
    registry isolates the entity noris_ai's platform actually created.
    """
    registry = er.async_get(hass)
    return [
        entity
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.domain == "conversation"
    ]


def _tool_call_chunk(call_id: str, name: str, arguments: str) -> object:
    """Build a streaming chunk carrying one function tool call."""
    return _chunk(
        tool_calls=[
            ChoiceDeltaToolCall(
                index=0,
                id=call_id,
                type="function",
                function=ChoiceDeltaToolCallFunction(name=name, arguments=arguments),
            )
        ],
        finish="tool_calls",
    )


# --------------------------------------------------------------------------
# Entity creation and plain conversation (upstream)
# --------------------------------------------------------------------------


async def test_conversation_entity_created(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A conversation subentry produces a conversation entity."""
    await setup_integration(hass, mock_config_entry)

    assert len(_conversation_entities(hass, mock_config_entry)) == 1


async def test_simple_answer(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_conversation
) -> None:
    await setup_integration(hass, mock_config_entry_with_conversation)
    mock_openai.chat.completions.create = _stream_mock(
        [
            _chunk("<think>kurz nachdenken</think>"),
            _chunk("Hallo!"),
            _chunk(None, finish="stop"),
        ]
    )

    result = await conversation.async_converse(
        hass, "Hallo", None, Context(), agent_id=AGENT_ID
    )

    assert result.response.response_type == intent.IntentResponseType.ACTION_DONE
    assert result.response.speech["plain"]["speech"] == "Hallo!"
    call_kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "vllm/gpt-oss-120b"
    assert call_kwargs["max_tokens"] == 3000
    assert call_kwargs["stream"] is True


async def test_tool_call_round(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_conversation
) -> None:
    """First response calls a tool, second one answers."""
    mock_tool = MagicMock(spec=llm.Tool)
    mock_tool.name = "test_tool"
    mock_tool.description = "Test"
    mock_tool.parameters = vol.Schema({vol.Optional("param"): str})
    mock_tool.async_call = AsyncMock(return_value=llm.ToolResult(data={"ok": True}))

    first = [
        _chunk(
            tool_calls=[
                ChoiceDeltaToolCall(
                    index=0,
                    id="call_1",
                    type="function",
                    function=ChoiceDeltaToolCallFunction(
                        name="test_tool", arguments='{"param": "x"}'
                    ),
                )
            ],
            finish="tool_calls",
        )
    ]
    second = [_chunk("Erledigt"), _chunk(None, finish="stop")]

    async def _gen(chunks):
        for chunk in chunks:
            yield chunk

    async def _fake_instance(api_self, llm_context):
        # HA 2026.11: AssistAPI lives in homeassistant.components.llm and
        # collects its tools in async_get_api_instance; replacing the
        # instance factory injects our mock tool into chat_log.llm_api.
        return llm.APIInstance(
            api=api_self,
            api_prompt="",
            llm_context=llm_context,
            tools=[mock_tool],
        )

    with patch.object(AssistAPI, "async_get_api_instance", new=_fake_instance):
        await setup_integration(hass, mock_config_entry_with_conversation)
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=[_gen(first), _gen(second)]
        )
        result = await conversation.async_converse(
            hass, "Mach was", None, Context(), agent_id=AGENT_ID
        )

    assert result.response.speech["plain"]["speech"] == "Erledigt"
    mock_tool.async_call.assert_awaited_once()
    assert mock_openai.chat.completions.create.await_count == 2


async def test_broken_model_reports_friendly_error(
    hass: HomeAssistant, mock_openai: MagicMock, mock_config_entry_with_conversation
) -> None:
    await setup_integration(hass, mock_config_entry_with_conversation)
    response = MagicMock()
    response.status_code = 400
    mock_openai.chat.completions.create = AsyncMock(
        side_effect=APIStatusError(
            message="no keys found that support model: gpt-oss-120b",
            response=response,
            body=None,
        )
    )

    result = await conversation.async_converse(
        hass, "Hallo", None, Context(), agent_id=AGENT_ID
    )

    assert result.response.response_type == intent.IntentResponseType.ERROR
    assert "not available" in result.response.speech["plain"]["speech"]


# --------------------------------------------------------------------------
# Tool-loop and serialization regression pins (fork)
# --------------------------------------------------------------------------


async def test_conversation_tool_call_drives_second_round_trip(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry_with_llm_api: MockConfigEntry,
) -> None:
    """A failing tool call still drives a second round trip to the model.

    The requested tool is unknown, so the tool call fails: the failing result
    must feed back into the conversation and trigger the second round trip —
    the loop must not stall on a tool error either. Without the
    ``unresponded_tool_results`` check the model would only ever be called
    once and the final speech would be the (empty) content of the first
    response instead of the second answer.
    """
    first = [
        _tool_call_chunk("call_1", "not_a_real_tool", '{"foo": "bar"}'),
    ]
    second = [_chunk("Das Licht im Wohnzimmer ist an."), _chunk(None, finish="stop")]

    mock_client.chat.completions.create = AsyncMock(
        side_effect=[_stream(first), _stream(second)]
    )
    await setup_integration(hass, mock_config_entry_with_llm_api)
    entity_id = _conversation_entities(hass, mock_config_entry_with_llm_api)[
        0
    ].entity_id

    result = await conversation.async_converse(
        hass, "Schalte das Licht im Wohnzimmer an", None, Context(), agent_id=entity_id
    )

    assert mock_client.chat.completions.create.await_count == 2
    assert (
        result.response.speech["plain"]["speech"] == "Das Licht im Wohnzimmer ist an."
    )


async def test_conversation_tool_call_loop_is_bounded(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry_with_llm_api: MockConfigEntry,
) -> None:
    """A model that always answers with a tool call stops after MAX_TOOL_ITERATIONS.

    ``MAX_TOOL_ITERATIONS`` is imported from ``entity`` rather than
    hardcoded so this test tracks the constant if it ever changes.
    """
    call_count = 0

    def _always_tool_call(**_kwargs: Any) -> Any:
        """Return a stream that always asks for another (bogus) tool call."""
        nonlocal call_count
        call_count += 1
        return _stream(
            [_tool_call_chunk(f"call_{call_count}", "not_a_real_tool", "{}")]
        )

    mock_client.chat.completions.create = AsyncMock(side_effect=_always_tool_call)
    await setup_integration(hass, mock_config_entry_with_llm_api)
    entity_id = _conversation_entities(hass, mock_config_entry_with_llm_api)[
        0
    ].entity_id

    await conversation.async_converse(
        hass, "Schalte das Licht im Wohnzimmer an", None, Context(), agent_id=entity_id
    )

    assert mock_client.chat.completions.create.await_count == MAX_TOOL_ITERATIONS


async def test_conversation_payload_serializes(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry_with_llm_api: MockConfigEntry,
) -> None:
    """The model_args payload serializes with the openai SDK's strict JSON.

    Regression pin for the 2026-11-21 HA-2026.11 incident: openai 3.x builds
    request bodies with ``allow_nan=False`` and rejects any non-JSON-native
    object — voluptuous_openapi returned its ``UNSUPPORTED`` sentinel for
    HA 2026.11's probatio tool schemas, so the request raised ``TypeError``
    before it ever left the process. The mocked client hides serialization
    entirely, so the captured payload is run through the SDK's own serializer
    here.
    """
    from openai._utils._json import openapi_dumps

    captured: dict[str, Any] = {}

    def _capture(**kwargs: Any) -> Any:
        """Record the model_args and answer like a plain stream would."""
        captured.update(kwargs)
        return _stream([_chunk("Bestätigt."), _chunk(None, finish="stop")])

    mock_client.chat.completions.create = AsyncMock(side_effect=_capture)
    await setup_integration(hass, mock_config_entry_with_llm_api)
    entity_id = _conversation_entities(hass, mock_config_entry_with_llm_api)[
        0
    ].entity_id

    result = await conversation.async_converse(
        hass, "Ist das Licht an?", None, Context(), agent_id=entity_id
    )
    assert result.response.response_type != intent.IntentResponseType.ERROR

    # Raises on NaN/inf and on foreign objects (e.g. probatio sentinels).
    openapi_dumps(captured)

    assert {"model", "messages", "tools"} <= set(captured)
    assert all(
        isinstance(tool["function"]["parameters"], dict) for tool in captured["tools"]
    )
