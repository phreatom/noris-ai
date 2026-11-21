"""Tests for the noris AI config flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
from openai import APIConnectionError, AuthenticationError
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.noris_ai.const import (
    AI_TASK_SUBENTRY_TYPE,
    CONF_MAX_TOKENS,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONVERSATION_SUBENTRY_TYPE,
    DEFAULT_MODEL,
    DEFAULT_STT_NAME,
    DEFAULT_TTS_NAME,
    DOMAIN,
    STT_SUBENTRY_TYPE,
    TTS_SUBENTRY_TYPE,
)
from custom_components.noris_ai.models import is_stt_model, is_tts_model
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_MODEL, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import setup_integration


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


# --------------------------------------------------------------------------
# Main-entry flows (API key)
# --------------------------------------------------------------------------


async def test_user_flow_happy_path(
    hass: HomeAssistant, mock_openai: MagicMock
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-test"}
    )
    await hass.async_block_till_done()
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

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-bad"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}

    # Recovery: the next attempt with a working key succeeds.
    mock_client.models.list = AsyncMock(return_value=SimpleNamespace(data=[]))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-good"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_key_aborts(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-test"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    result = await mock_plain_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-new"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_plain_config_entry.data[CONF_API_KEY] == "sk-bf-new"


async def test_reconfigure_updates_key(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfigure replaces the stored key on the main entry."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "sk-bf-new"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_API_KEY] == "sk-bf-new"


async def test_subentry_flow_aborts_when_entry_not_loaded(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """A subentry flow against a NOT_LOADED entry aborts rather than erroring.

    Only the conversation handler is exercised here: every subentry flow
    guards its first step with the identical
    ``if self._get_entry().state is not ConfigEntryState.LOADED`` check, so
    one handler covers the shared guard.
    """
    mock_config_entry.add_to_hass(hass)
    assert mock_config_entry.state is config_entries.ConfigEntryState.NOT_LOADED

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, CONVERSATION_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entry_not_loaded"


# --------------------------------------------------------------------------
# Conversation agent / AI task subentry flows (upstream)
# --------------------------------------------------------------------------


async def test_conversation_subentry_recommended(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    """Create an agent with recommended settings — one step only."""
    await setup_integration(hass, mock_plain_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_plain_config_entry.entry_id, CONVERSATION_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Mein Agent",
            CONF_MODEL: DEFAULT_MODEL,
            CONF_LLM_HASS_API: ["assist"],
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mein Agent"
    assert result["data"] == {
        CONF_MODEL: DEFAULT_MODEL,
        CONF_LLM_HASS_API: ["assist"],
        CONF_RECOMMENDED: True,
    }


async def test_conversation_subentry_advanced(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    """Unchecking recommended leads to the advanced step."""
    await setup_integration(hass, mock_plain_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_plain_config_entry.entry_id, CONVERSATION_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Tuning-Agent",
            CONF_MODEL: "vllm/release/glm-5-2",
            # The prompt belongs to the init form; submitting it here also
            # verifies it survives the advanced step into the stored data.
            "prompt": "Du bist knapp.",
            CONF_RECOMMENDED: False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MAX_TOKENS: 5000,
            CONF_TEMPERATURE: 0.5,
            CONF_TOP_P: 0.9,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MODEL] == "vllm/release/glm-5-2"
    assert result["data"][CONF_MAX_TOKENS] == 5000
    assert result["data"]["prompt"] == "Du bist knapp."


async def test_conversation_subentry_reconfigure(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    """The model of an existing agent can be changed via reconfigure.

    This pins the model dropdown in the reconfigure form — switching the
    model of an existing subentry is the primary reconfigure use case.
    """
    await setup_integration(hass, mock_plain_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_plain_config_entry.entry_id, CONVERSATION_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Agent",
            CONF_MODEL: DEFAULT_MODEL,
            CONF_RECOMMENDED: True,
        },
    )
    subentry_id = next(iter(mock_plain_config_entry.subentries))

    result = await mock_plain_config_entry.start_subentry_reconfigure_flow(
        hass, subentry_id
    )
    assert result["step_id"] == "init"
    # The reconfigure form offers the model dropdown with the current model.
    schema = result["data_schema"].schema
    model_key = next(k for k in schema if k == "model")
    assert model_key.default() == DEFAULT_MODEL

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MODEL: "vllm/qwen3.6-27b",
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = mock_plain_config_entry.subentries[subentry_id]
    assert subentry.data[CONF_MODEL] == "vllm/qwen3.6-27b"


async def test_conversation_subentry_reconfigure_keeps_control_disabled(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    """Reconfiguring a subentry created without device control must not
    silently re-enable it by defaulting llm_hass_api to Assist again."""
    await setup_integration(hass, mock_plain_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_plain_config_entry.entry_id, CONVERSATION_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Agent ohne Kontrolle",
            CONF_MODEL: DEFAULT_MODEL,
            CONF_LLM_HASS_API: [],
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_LLM_HASS_API not in result["data"]
    subentry_id = next(iter(mock_plain_config_entry.subentries))

    result = await mock_plain_config_entry.start_subentry_reconfigure_flow(
        hass, subentry_id
    )
    assert result["step_id"] == "init"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MODEL: DEFAULT_MODEL,
            CONF_LLM_HASS_API: [],
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = mock_plain_config_entry.subentries[subentry_id]
    assert CONF_LLM_HASS_API not in subentry.data


async def test_conversation_subentry_reconfigure_default_omits_llm_hass_api(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    """The reconfigure result must never re-add llm_hass_api unless it was
    explicitly submitted with a non-empty value."""
    await setup_integration(hass, mock_plain_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_plain_config_entry.entry_id, CONVERSATION_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Agent",
            CONF_MODEL: DEFAULT_MODEL,
            CONF_LLM_HASS_API: [],
            CONF_RECOMMENDED: True,
        },
    )
    subentry_id = next(iter(mock_plain_config_entry.subentries))

    result = await mock_plain_config_entry.start_subentry_reconfigure_flow(
        hass, subentry_id
    )
    assert result["step_id"] == "init"

    # Inspect the form's default for llm_hass_api: it must be empty, not
    # pre-filled with Assist, since the subentry has no stored key.
    schema = result["data_schema"].schema
    llm_hass_api_default = next(
        key.default() for key in schema if str(key) == "llm_hass_api"
    )
    assert llm_hass_api_default == []

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_MODEL: DEFAULT_MODEL,
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = mock_plain_config_entry.subentries[subentry_id]
    assert CONF_LLM_HASS_API not in subentry.data


async def test_ai_task_subentry_recommended(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, mock_plain_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_plain_config_entry.entry_id, AI_TASK_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Meine Task",
            CONF_MODEL: DEFAULT_MODEL,
            CONF_RECOMMENDED: True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Meine Task"
    assert result["data"] == {CONF_MODEL: DEFAULT_MODEL, CONF_RECOMMENDED: True}


async def test_ai_task_subentry_advanced(
    hass: HomeAssistant,
    mock_openai: MagicMock,
    mock_plain_config_entry: MockConfigEntry,
) -> None:
    await setup_integration(hass, mock_plain_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_plain_config_entry.entry_id, AI_TASK_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Task",
            CONF_MODEL: DEFAULT_MODEL,
            CONF_RECOMMENDED: False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "advanced"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_MAX_TOKENS: 16000, CONF_TEMPERATURE: 0.2, CONF_TOP_P: 1.0},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAX_TOKENS] == 16000
    assert "prompt" not in result["data"]


# --------------------------------------------------------------------------
# Chat/AI-task dropdowns exclude non-chat models (fork behavior)
# --------------------------------------------------------------------------


async def test_conversation_subentry_excludes_audio_models(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Voxtral must not be offered as a conversation model."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, CONVERSATION_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )

    options = result["data_schema"].schema["model"].config["options"]
    values = [option["value"] for option in options]
    assert "vllm/qsu/voxtral-small-24b-2507" not in values
    assert "vllm/release/gpt-oss-120b" in values


async def test_ai_task_subentry_excludes_audio_models(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Voxtral must not be offered as an AI Task model either.

    Only the conversation half of this fix was covered before; the headline
    claim is that Voxtral disappears from BOTH the conversation and AI Task
    dropdowns.
    """
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, AI_TASK_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )

    options = result["data_schema"].schema["model"].config["options"]
    values = [option["value"] for option in options]
    assert "vllm/qsu/voxtral-small-24b-2507" not in values
    assert "vllm/release/gpt-oss-120b" in values


# --------------------------------------------------------------------------
# Speech-to-text subentry flows (fork)
# --------------------------------------------------------------------------


async def test_stt_subentry_offers_only_audio_models(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The STT dropdown lists Voxtral and nothing else."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, STT_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    options = result["data_schema"].schema["model"].config["options"]
    assert [option["value"] for option in options] == [
        "vllm/qsu/voxtral-small-24b-2507"
    ]


async def test_stt_subentry_creates_entity(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Choosing a model creates the subentry with the friendly title."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, STT_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"model": "vllm/qsu/voxtral-small-24b-2507"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_STT_NAME
    assert result["data"] == {"model": "vllm/qsu/voxtral-small-24b-2507"}


async def test_stt_subentry_aborts_without_audio_models(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    default_models: list,
) -> None:
    """With no audio model on the gateway, say so instead of an empty dropdown."""
    await setup_integration(hass, mock_config_entry)
    mock_client.models.list = AsyncMock(
        return_value=SimpleNamespace(
            data=[m for m in default_models if not is_stt_model(m)]
        )
    )

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, STT_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_audio_models"


async def test_stt_subentry_reconfigure_changes_model(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfiguring the STT subentry offers the current model and updates it.

    The reconfigure path had zero coverage in an earlier iteration: a
    reviewer's ``raise RuntimeError`` as the first statement of the
    reconfigure step still passed the full suite.
    """
    await setup_integration(hass, mock_config_entry)
    subentry_id = next(
        subentry_id
        for subentry_id, subentry in mock_config_entry.subentries.items()
        if subentry.subentry_type == STT_SUBENTRY_TYPE
    )

    result = await mock_config_entry.start_subentry_reconfigure_flow(hass, subentry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    model_key = next(k for k in result["data_schema"].schema if k == "model")
    assert model_key.default() == "vllm/qsu/voxtral-small-24b-2507"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"model": "vllm/qsu/voxtral-small-24b-2507"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    updated = mock_config_entry.subentries[subentry_id]
    assert updated.data["model"] == "vllm/qsu/voxtral-small-24b-2507"


# --------------------------------------------------------------------------
# Text-to-speech subentry flows (fork)
# --------------------------------------------------------------------------


async def test_tts_subentry_offers_only_speech_models(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """The TTS dropdown lists the speech models and nothing else."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, TTS_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.FORM
    options = result["data_schema"].schema["model"].config["options"]
    values = [option["value"] for option in options]
    assert "Cosyvoice3/release/cosyvoice3-0.5b-rl" in values
    assert "Kokoro-TTS/release/kokoro-tts-german-martin" in values
    assert "vllm/release/gpt-oss-120b" not in values
    assert "vllm/qsu/voxtral-small-24b-2507" not in values


async def test_tts_subentry_creates_entity(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Choosing a model creates a subentry with the friendly title."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, TTS_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"model": "Cosyvoice3/release/cosyvoice3-0.5b-rl"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_TTS_NAME
    assert result["data"] == {"model": "Cosyvoice3/release/cosyvoice3-0.5b-rl"}


async def test_tts_subentry_aborts_without_speech_models(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    default_models: list,
) -> None:
    """With no speech model on the gateway, say so instead of an empty dropdown."""
    await setup_integration(hass, mock_config_entry)
    mock_client.models.list = AsyncMock(
        return_value=SimpleNamespace(
            data=[m for m in default_models if not is_tts_model(m)]
        )
    )

    result = await hass.config_entries.subentries.async_init(
        (mock_config_entry.entry_id, TTS_SUBENTRY_TYPE),
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_speech_models"


async def test_tts_subentry_reconfigure_changes_model(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Reconfiguring the TTS subentry offers the current model and updates it.

    Mirrors the STT reconfigure test: both reconfigure paths had zero
    coverage in an earlier iteration — a reviewer's ``raise RuntimeError``
    left the full suite green.
    """
    await setup_integration(hass, mock_config_entry)
    subentry_id = next(
        subentry_id
        for subentry_id, subentry in mock_config_entry.subentries.items()
        if subentry.subentry_type == TTS_SUBENTRY_TYPE
    )

    result = await mock_config_entry.start_subentry_reconfigure_flow(hass, subentry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    model_key = next(k for k in result["data_schema"].schema if k == "model")
    assert model_key.default() == "Cosyvoice3/release/cosyvoice3-0.5b-rl"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"model": "Kokoro-TTS/release/kokoro-tts-german-martin"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    updated = mock_config_entry.subentries[subentry_id]
    assert updated.data["model"] == "Kokoro-TTS/release/kokoro-tts-german-martin"


async def test_tts_subentry_reconfigure_aborts_without_speech_models(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    default_models: list,
) -> None:
    """Reconfigure also guards against an empty speech-model dropdown.

    Pins the ``no_speech_models`` guard on the reconfigure path into
    ``async_step_init``, which is reached separately from the user flow.
    """
    await setup_integration(hass, mock_config_entry)
    subentry_id = next(
        subentry_id
        for subentry_id, subentry in mock_config_entry.subentries.items()
        if subentry.subentry_type == TTS_SUBENTRY_TYPE
    )
    mock_client.models.list = AsyncMock(
        return_value=SimpleNamespace(
            data=[m for m in default_models if not is_tts_model(m)]
        )
    )

    result = await mock_config_entry.start_subentry_reconfigure_flow(hass, subentry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_speech_models"
