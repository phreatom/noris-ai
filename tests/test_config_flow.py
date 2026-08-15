"""Tests for the noris AI config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
from openai import APIConnectionError, AuthenticationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.noris_ai.const import DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component


def _auth_error() -> AuthenticationError:
    """Build a 401 from the SDK."""
    request = httpx.Request("GET", "https://ai.noris.de/v1/models")
    return AuthenticationError(
        "nope", response=httpx.Response(401, request=request), body=None
    )


def _connection_error() -> APIConnectionError:
    """Build a transport failure from the SDK."""
    return APIConnectionError(
        request=httpx.Request("GET", "https://ai.noris.de/v1/models")
    )


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """A valid key creates the config entry."""
    await async_setup_component(hass, "homeassistant", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-test"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "noris AI"
    assert result["data"] == {CONF_API_KEY: "sk-bf-test"}


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (_auth_error(), "invalid_auth"),
        (_connection_error(), "cannot_connect"),
        (ValueError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    side_effect: Exception,
    expected_error: str,
) -> None:
    """Validation failures are shown on the form rather than aborting."""
    mock_client.models.list = MagicMock(side_effect=side_effect)

    await async_setup_component(hass, "homeassistant", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-bad"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_duplicate_key_aborts(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Re-adding the same key aborts as already configured."""
    mock_config_entry.add_to_hass(hass)

    await async_setup_component(hass, "homeassistant", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-test"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_key(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reauth replaces the stored key."""
    mock_config_entry.add_to_hass(hass)

    await async_setup_component(hass, "homeassistant", {})
    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-new"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_API_KEY] == "sk-bf-new"


async def test_reconfigure_updates_key(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfigure replaces the stored key."""
    mock_config_entry.add_to_hass(hass)

    await async_setup_component(hass, "homeassistant", {})
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-new"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_API_KEY] == "sk-bf-new"
