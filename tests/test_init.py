"""Tests for noris AI setup and teardown."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from openai import APIConnectionError, AuthenticationError, PermissionDeniedError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .conftest import setup_integration


def _auth_error(status: int) -> AuthenticationError | PermissionDeniedError:
    """Build an SDK auth error carrying the given HTTP status."""
    request = httpx.Request("GET", "https://ai.noris.de/v1/models")
    response = httpx.Response(status, request=request)
    error_cls = AuthenticationError if status == 401 else PermissionDeniedError
    return error_cls("nope", response=response, body=None)


async def test_setup_stores_client(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A successful setup validates the key and stores the client."""
    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is mock_client


@pytest.mark.parametrize("status", [401, 403])
async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    status: int,
) -> None:
    """An invalid key puts the entry into SETUP_ERROR and triggers reauth."""
    mock_client.models.list = MagicMock(side_effect=_auth_error(status))

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_setup_connection_failure_retries(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A transport failure leaves the entry in SETUP_RETRY."""
    request = httpx.Request("GET", "https://ai.noris.de/v1/models")
    mock_client.models.list = MagicMock(side_effect=APIConnectionError(request=request))

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The entry unloads cleanly."""
    await setup_integration(hass, mock_config_entry)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_update_listener_reloads(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Changing entry data reloads the entry."""
    await setup_integration(hass, mock_config_entry)

    with patch.object(
        hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
    ) as mock_reload:
        hass.config_entries.async_update_entry(
            mock_config_entry, data={**mock_config_entry.data, "api_key": "sk-bf-other"}
        )
        await hass.async_block_till_done()

    mock_reload.assert_awaited_once_with(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED
