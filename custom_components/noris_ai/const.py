"""Constants for the noris AI integration."""

import logging
import re

from homeassistant.const import CONF_LLM_HASS_API, CONF_PROMPT
from homeassistant.helpers import llm

DOMAIN = "noris_ai"
LOGGER = logging.getLogger(__package__)

# ai.noris.de is an OpenAI-compatible gateway. Note that authentication does
# NOT use the standard ``Authorization: Bearer`` header but a custom
# ``x-bf-vk`` header (see ``__init__._create_client``).
BASE_URL = "https://ai.noris.de/v1"

# Custom authentication header used by the ai.noris.de gateway.
AUTH_HEADER = "x-bf-vk"

CONF_MAX_TOKENS = "max_tokens"
CONF_TEMPERATURE = "temperature"

CONVERSATION_SUBENTRY_TYPE = "conversation"
AI_TASK_SUBENTRY_TYPE = "ai_task_data"

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}

# AI Task entities only need a model: the ai_task base class supplies the
# system prompt and the user instructions itself, so a prompt option here
# would have no effect.

STT_SUBENTRY_TYPE = "stt"

# Subentry titles. These become the device name, and Home Assistant slugifies
# the device name into the entity id, so they must read well in both places.
# The chosen model is surfaced separately as ``DeviceInfo.model``, which the UI
# renders beneath the name — titling a subentry with the raw model id instead
# leaves the device card with no indication of what the device actually is.
DEFAULT_CONVERSATION_NAME = "noris AI Conversation Agent"
DEFAULT_AI_TASK_NAME = "noris AI Task"
DEFAULT_STT_NAME = "noris AI Speech-to-text"

# Seconds to wait for a transcription before failing the pipeline. The gateway
# answers a five-second utterance in well under a second; this bound exists so a
# stalled gateway does not hang the voice satellite.
STT_TIMEOUT = 30.0

# Audio capability CANNOT be read from the model catalog: the gateway reports
# Voxtral's input_modalities as text-only even though transcription works.
# Known audio model families are matched by name instead. Do not "simplify" this
# to the modality metadata without re-probing /v1/models first.
AUDIO_MODEL_PATTERN = re.compile(
    r"voxtral|whisper|qwen.*audio|granite-speech", re.IGNORECASE
)

# Voxtral's documented languages, as BCP-47 tags. Deliberately not the ~130
# languages other cloud engines advertise: claiming unsupported languages
# produces confident, wrong transcripts instead of an honest failure to match.
STT_SUPPORTED_LANGUAGES = [
    "de-DE",
    "de-AT",
    "de-CH",
    "en-US",
    "en-GB",
    "en-AU",
    "en-CA",
    "en-IE",
    "en-IN",
    "en-NZ",
    "en-ZA",
    "es-ES",
    "es-MX",
    "es-AR",
    "es-CO",
    "es-US",
    "fr-FR",
    "fr-BE",
    "fr-CA",
    "fr-CH",
    "it-IT",
    "it-CH",
    "nl-NL",
    "nl-BE",
    "pt-PT",
    "pt-BR",
    "hi-IN",
]
