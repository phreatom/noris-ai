"""Tests for the noris AI conversation agent."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components import conversation
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import entity_registry as er, intent

from .conftest import setup_integration


def chat_completion(content: str | None, *, tool_calls: list[Any] | None = None) -> Any:
    """Build a minimal chat.completions response."""
    message = SimpleNamespace(
        role="assistant",
        content=content,
        tool_calls=tool_calls,
        model_extra={},
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


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


async def test_conversation_entity_created(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A conversation subentry produces a conversation entity."""
    await setup_integration(hass, mock_config_entry)

    assert len(_conversation_entities(hass, mock_config_entry)) == 1


async def test_conversation_answers(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A plain question returns the model's answer as the response speech."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=chat_completion("Das Licht im Wohnzimmer ist an.")
    )
    await setup_integration(hass, mock_config_entry)
    entity_id = _conversation_entities(hass, mock_config_entry)[0].entity_id

    result = await conversation.async_converse(
        hass, "Ist das Licht an?", None, Context(), agent_id=entity_id
    )

    assert (
        result.response.speech["plain"]["speech"] == "Das Licht im Wohnzimmer ist an."
    )


async def test_conversation_reports_api_error(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """An empty choices list surfaces as an error response, not a crash."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=SimpleNamespace(choices=[])
    )
    await setup_integration(hass, mock_config_entry)
    entity_id = _conversation_entities(hass, mock_config_entry)[0].entity_id

    result = await conversation.async_converse(
        hass, "Ist das Licht an?", None, Context(), agent_id=entity_id
    )

    assert result.response.response_type == intent.IntentResponseType.ERROR
