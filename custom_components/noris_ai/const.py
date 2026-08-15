"""Constants for the noris AI integration."""

import logging

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
