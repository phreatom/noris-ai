"""Tests for the noris AI AI Task entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from homeassistant.components import ai_task
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import setup_integration
from .test_conversation import chat_completion


def _task_entity_id(hass: HomeAssistant) -> str:
    """Return the single AI task entity id."""
    return next(s.entity_id for s in hass.states.async_all() if s.domain == "ai_task")


async def test_generate_free_text(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Free-text generation returns the raw model output."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=chat_completion("Es sind 21 Grad.")
    )
    await setup_integration(hass, mock_config_entry)

    result = await ai_task.async_generate_data(
        hass,
        task_name="wetter",
        entity_id=_task_entity_id(hass),
        instructions="Wie warm ist es?",
    )

    assert result.data == "Es sind 21 Grad."


async def test_generate_structured_data(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A structure request parses the JSON response into a dict."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=chat_completion('{"temperatur": 21}')
    )
    await setup_integration(hass, mock_config_entry)

    result = await ai_task.async_generate_data(
        hass,
        task_name="wetter",
        entity_id=_task_entity_id(hass),
        instructions="Wie warm ist es?",
        structure=vol.Schema({vol.Required("temperatur"): int}),
    )

    assert result.data == {"temperatur": 21}


async def test_generate_structured_data_invalid_json(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Unparseable structured output raises a clear error."""
    mock_client.chat.completions.create = AsyncMock(
        return_value=chat_completion("nicht json")
    )
    await setup_integration(hass, mock_config_entry)

    with pytest.raises(HomeAssistantError, match="Error parsing structured response"):
        await ai_task.async_generate_data(
            hass,
            task_name="wetter",
            entity_id=_task_entity_id(hass),
            instructions="Wie warm ist es?",
            structure=vol.Schema({vol.Required("temperatur"): int}),
        )
