"""Tests for the noris AI config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
from openai import APIConnectionError, AuthenticationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.noris_ai.config_flow import _is_chat_model, _is_stt_model
from custom_components.noris_ai.const import DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from .conftest import fake_model


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


def test_chat_filter_accepts_text_models() -> None:
    """Ordinary vLLM chat models remain selectable."""
    assert _is_chat_model(fake_model("vllm/release/gpt-oss-120b")) is True


def test_chat_filter_rejects_rerankers_and_embeddings() -> None:
    """Non-text output modalities are not chat models."""
    assert (
        _is_chat_model(
            fake_model("vllm/release/bge-reranker-v2-m3", output_type="rerank")
        )
        is False
    )
    assert (
        _is_chat_model(
            fake_model("vllm/release/harrier-oss-v1-0.6b", output_type="embeddings")
        )
        is False
    )


def test_chat_filter_rejects_audio_models() -> None:
    """Voxtral is an audio model and must not appear in chat dropdowns."""
    model = fake_model(
        "vllm/qsu/voxtral-small-24b-2507",
        hugging_face_id="mistralai/Voxtral-Small-24B-2507",
    )

    assert _is_chat_model(model) is False


def test_chat_filter_rejects_other_providers() -> None:
    """Only vllm/* models are offered, per existing policy."""
    assert _is_chat_model(fake_model("something/else")) is False


def test_chat_filter_falls_back_without_metadata() -> None:
    """With no output_modalities, the old name heuristic still applies."""
    assert (
        _is_chat_model(fake_model("vllm/release/gpt-oss-120b", output_type=None))
        is True
    )
    assert (
        _is_chat_model(fake_model("vllm/release/bge-reranker-v2-m3", output_type=None))
        is False
    )


def test_stt_filter_accepts_voxtral_by_hugging_face_id() -> None:
    """Audio capability is detected from hugging_face_id."""
    model = fake_model(
        "vllm/qsu/some-opaque-name",
        hugging_face_id="mistralai/Voxtral-Small-24B-2507",
    )

    assert _is_stt_model(model) is True


def test_stt_filter_accepts_whisper_by_id() -> None:
    """A future Whisper deployment is picked up from the model id."""
    assert _is_stt_model(fake_model("vllm/release/whisper-large-v3")) is True


def test_stt_filter_tolerates_null_hugging_face_id() -> None:
    """A null hugging_face_id must not raise; many gateway models have none."""
    assert _is_stt_model(fake_model("vllm/release/gpt-oss-120b")) is False


def test_stt_filter_rejects_chat_models() -> None:
    """Text models are not offered as transcription engines."""
    assert _is_stt_model(fake_model("vllm/qsu/glm-5-2")) is False
