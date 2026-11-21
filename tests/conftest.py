"""Fixtures for the noris AI integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from openai.types import Model
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.noris_ai.const import (
    AI_TASK_SUBENTRY_TYPE,
    CONF_RECOMMENDED,
    CONVERSATION_SUBENTRY_TYPE,
    DEFAULT_AI_TASK_NAME,
    DEFAULT_CONVERSATION_NAME,
    DEFAULT_MODEL,
    DEFAULT_STT_NAME,
    DEFAULT_TTS_NAME,
    DOMAIN,
    STT_SUBENTRY_TYPE,
    TTS_SUBENTRY_TYPE,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_API_KEY, CONF_MODEL
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

# Gateway catalog ids used across the fixtures. CHAT_MODEL/AUDIO_MODEL/
# SPEECH_MODEL are the live channel-prefixed ids (2026-11-21 catalog).
CHAT_MODEL = "vllm/release/gpt-oss-120b"
AUDIO_MODEL = "vllm/qsu/voxtral-small-24b-2507"
SPEECH_MODEL = "Cosyvoice3/release/cosyvoice3-0.5b-rl"


@pytest.fixture
def hass_config_dir(hass_tmp_config_dir: str) -> str:
    """Use a fresh, per-test config directory instead of the plugin's shared one.

    Without this override every test shares
    ``pytest_homeassistant/testing_config`` as ``hass.config``,
    including its ``tts/`` disk cache. The tts component's
    ``async_get_media_source_audio`` path checks that disk cache *before*
    calling the entity, keyed only on message+language+options+engine — so a
    synthesis test run once leaves a file behind that lets an identical test
    pass on every subsequent run without the mocked API ever being called
    again, silently defeating the test. ``hass_tmp_config_dir`` (from the
    plugin) copies the shared config into a pytest ``tmp_path`` that is
    discarded after the test.
    """
    return hass_tmp_config_dir


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture(autouse=True)
async def setup_homeassistant_component(hass: HomeAssistant) -> None:
    """Set up the homeassistant component.

    The conversation component (a manifest dependency of noris_ai) needs the
    exposed-entities registry that the homeassistant component provides.
    """
    assert await async_setup_component(hass, "homeassistant", {})


@pytest.fixture
def default_models() -> list[Model]:
    """Return a model catalog resembling the live gateway (page-style).

    Contains one entry per capability the flows distinguish: chat models, the
    Voxtral transcription model, both speech models, and a reranker that every
    picker must exclude.
    """
    return [
        Model(id=CHAT_MODEL, created=0, object="model", owned_by="vllm"),
        Model(id="vllm/release/glm-5-2", created=0, object="model", owned_by="vllm"),
        Model(id=AUDIO_MODEL, created=0, object="model", owned_by="vllm"),
        Model(id=SPEECH_MODEL, created=0, object="model", owned_by="cosyvoice"),
        Model(
            id="Kokoro-TTS/release/kokoro-tts-german-martin",
            created=0,
            object="model",
            owned_by="kokoro",
        ),
        # Excluded from every picker by the name heuristic.
        Model(id="vllm/bge-reranker-v2-m3", created=0, object="model", owned_by="vllm"),
    ]


@pytest.fixture
def mock_client(default_models: list[Model]) -> Iterator[MagicMock]:
    """Patch the AsyncOpenAI client in both modules that reference it.

    ``config_flow`` does ``from . import _create_client``, which binds the name
    into its own namespace at import time, so patching only the package
    attribute would leave the flow using the real client. The catalog is
    served page-style (``await client.models.list()`` → ``.data``), matching
    the ``models`` module helpers.
    """
    client = MagicMock()
    client.with_options = MagicMock(return_value=client)
    client.models.list = AsyncMock(return_value=SimpleNamespace(data=default_models))
    client.chat.completions.create = AsyncMock()

    with (
        patch("custom_components.noris_ai._create_client", return_value=client),
        patch(
            "custom_components.noris_ai.config_flow._create_client",
            return_value=client,
        ),
    ):
        yield client


@pytest.fixture
def mock_models() -> list[Model]:
    """Gateway model list: usable, external, and filtered-out entries."""
    return [
        Model(id="vllm/gpt-oss-120b", created=0, object="model", owned_by="vllm"),
        Model(id="vllm/qwen3.6-27b", created=0, object="model", owned_by="vllm"),
        Model(id="vllm/release/glm-5-2", created=0, object="model", owned_by="vllm"),
        Model(id="vllm/bge-reranker-v2-m3", created=0, object="model", owned_by="vllm"),
        Model(
            id="vllm/harrier-oss-v1-0.6b", created=0, object="model", owned_by="vllm"
        ),
        Model.model_construct(
            id="anthropic/claude-sonnet-5",
            created=0,
            object="model",
            owned_by="anthropic",
            name="Claude Sonnet 5",
        ),
    ]


@pytest.fixture
def mock_openai(mock_models: list[Model]) -> Iterator[MagicMock]:
    """Patch the AsyncOpenAI class used by the integration."""
    client = MagicMock()
    client.with_options = MagicMock(return_value=client)
    client.models.list = AsyncMock(return_value=SimpleNamespace(data=mock_models))
    client.chat.completions.create = AsyncMock()
    with patch("custom_components.noris_ai.AsyncOpenAI", return_value=client):
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry with conversation, AI task, STT, and TTS subentries."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="noris AI",
        data={CONF_API_KEY: "sk-bf-test"},
        subentries_data=[
            ConfigSubentryData(
                data={CONF_MODEL: CHAT_MODEL},
                subentry_type=CONVERSATION_SUBENTRY_TYPE,
                title=DEFAULT_CONVERSATION_NAME,
                unique_id=None,
            ),
            ConfigSubentryData(
                data={CONF_MODEL: CHAT_MODEL},
                subentry_type=AI_TASK_SUBENTRY_TYPE,
                title=DEFAULT_AI_TASK_NAME,
                unique_id=None,
            ),
            ConfigSubentryData(
                data={CONF_MODEL: AUDIO_MODEL},
                subentry_type=STT_SUBENTRY_TYPE,
                title=DEFAULT_STT_NAME,
                unique_id=None,
            ),
            ConfigSubentryData(
                data={CONF_MODEL: SPEECH_MODEL},
                subentry_type=TTS_SUBENTRY_TYPE,
                title=DEFAULT_TTS_NAME,
                unique_id=None,
            ),
        ],
    )


@pytest.fixture
def mock_plain_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry with only the API key (no subentries)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="noris AI",
        data={CONF_API_KEY: "sk-bf-test"},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_config_entry_with_conversation(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry with one conversation agent (recommended settings)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="noris AI",
        data={CONF_API_KEY: "sk-bf-test"},
        subentries_data=[
            ConfigSubentryData(
                data={
                    CONF_MODEL: DEFAULT_MODEL,
                    CONF_RECOMMENDED: True,
                    "llm_hass_api": ["assist"],
                },
                subentry_type=CONVERSATION_SUBENTRY_TYPE,
                title="Test Agent",
                unique_id=None,
            )
        ],
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_config_entry_with_ai_task(hass: HomeAssistant) -> MockConfigEntry:
    """A config entry with one AI task entity (recommended settings)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="noris AI",
        data={CONF_API_KEY: "sk-bf-test"},
        subentries_data=[
            ConfigSubentryData(
                data={CONF_MODEL: DEFAULT_MODEL, CONF_RECOMMENDED: True},
                subentry_type=AI_TASK_SUBENTRY_TYPE,
                title="Test Task",
                unique_id=None,
            )
        ],
    )
    entry.add_to_hass(hass)
    return entry


async def setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry
) -> MockConfigEntry:
    """Add the config entry to hass (if needed) and set it up.

    Serves both fixture families: entries that pre-added themselves to hass
    (``mock_plain_config_entry``, ``mock_config_entry_with_*``) are set up
    directly; entries that did not (``mock_config_entry``) are added first.
    """
    if entry.entry_id not in {e.entry_id for e in hass.config_entries.async_entries()}:
        entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
