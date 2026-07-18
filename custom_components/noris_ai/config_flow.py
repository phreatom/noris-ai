"""Config flow for the noris AI integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from openai import AsyncOpenAI, AuthenticationError, OpenAIError, PermissionDeniedError
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_MODEL
from homeassistant.core import callback
from homeassistant.helpers import llm
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TemplateSelector,
)

from . import _create_client, _validate_api_key
from .const import (
    AI_TASK_SUBENTRY_TYPE,
    CONF_PROMPT,
    CONVERSATION_SUBENTRY_TYPE,
    DOMAIN,
    RECOMMENDED_CONVERSATION_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_API_KEY_DATA_SCHEMA = vol.Schema({vol.Required(CONF_API_KEY): str})


def _is_selectable_model(model_id: str) -> bool:
    """Return True for on-prem vLLM chat models worth offering to the user.

    Only ``vllm/*`` models are exposed (the anthropic-routed models are hidden
    so no data leaves the on-prem infrastructure). Rerankers and the tiny
    ``harrier-oss`` draft model are not usable as chat/agent models.
    """
    if not model_id.startswith("vllm/"):
        return False
    lowered = model_id.lower()
    if "reranker" in lowered:
        return False
    if "harrier" in lowered:
        return False
    return True


async def _fetch_model_options(entry: ConfigEntry) -> list[SelectOptionDict]:
    """Fetch and filter selectable models from the gateway."""
    client: AsyncOpenAI = entry.runtime_data
    return [
        SelectOptionDict(value=model.id, label=model.id)
        async for model in client.with_options(timeout=10.0).models.list()
        if _is_selectable_model(model.id)
    ]


class NorisAIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for noris AI."""

    VERSION = 1
    MINOR_VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this handler."""
        return {
            CONVERSATION_SUBENTRY_TYPE: ConversationFlowHandler,
            AI_TASK_SUBENTRY_TYPE: AITaskFlowHandler,
        }

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match(user_input)
            client = _create_client(self.hass, user_input[CONF_API_KEY])
            try:
                await _validate_api_key(client)
            except (AuthenticationError, PermissionDeniedError):
                errors["base"] = "invalid_auth"
            except OpenAIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="noris AI",
                    data=user_input,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_API_KEY_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication dialog."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = _create_client(self.hass, user_input[CONF_API_KEY])
            try:
                await _validate_api_key(client)
            except (AuthenticationError, PermissionDeniedError):
                errors["base"] = "invalid_auth"
            except OpenAIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates=user_input,
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_API_KEY_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the API key on an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            self._async_abort_entries_match(user_input)
            client = _create_client(self.hass, user_input[CONF_API_KEY])
            try:
                await _validate_api_key(client)
            except (AuthenticationError, PermissionDeniedError):
                errors["base"] = "invalid_auth"
            except OpenAIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_API_KEY_DATA_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


class ConversationFlowHandler(ConfigSubentryFlow):
    """Handle the conversation agent subentry flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to create a conversation agent."""
        return await self.async_step_init(user_input)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage conversation agent configuration."""
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)
            return self.async_create_entry(
                title=user_input[CONF_MODEL], data=user_input
            )

        try:
            model_options = await _fetch_model_options(self._get_entry())
        except OpenAIError:
            return self.async_abort(reason="cannot_connect")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")

        hass_apis: list[SelectOptionDict] = [
            SelectOptionDict(label=api.name, value=api.id)
            for api in llm.async_get_apis(self.hass)
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL): SelectSelector(
                        SelectSelectorConfig(
                            options=model_options,
                            mode=SelectSelectorMode.DROPDOWN,
                            sort=True,
                        ),
                    ),
                    vol.Optional(
                        CONF_PROMPT,
                        description={
                            "suggested_value": RECOMMENDED_CONVERSATION_OPTIONS[
                                CONF_PROMPT
                            ]
                        },
                    ): TemplateSelector(),
                    vol.Optional(
                        CONF_LLM_HASS_API,
                        default=RECOMMENDED_CONVERSATION_OPTIONS[CONF_LLM_HASS_API],
                    ): SelectSelector(
                        SelectSelectorConfig(options=hass_apis, multiple=True)
                    ),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Reconfigure a conversation agent (prompt + LLM APIs; model is fixed)."""
        subentry = self._get_reconfigure_subentry()
        existing = subentry.data

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)
            user_input[CONF_MODEL] = existing[CONF_MODEL]
            return self.async_update_and_abort(
                self._get_entry(), subentry, data=user_input
            )

        hass_apis: list[SelectOptionDict] = [
            SelectOptionDict(label=api.name, value=api.id)
            for api in llm.async_get_apis(self.hass)
        ]
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PROMPT,
                        description={
                            "suggested_value": existing.get(
                                CONF_PROMPT,
                                RECOMMENDED_CONVERSATION_OPTIONS[CONF_PROMPT],
                            )
                        },
                    ): TemplateSelector(),
                    vol.Optional(
                        CONF_LLM_HASS_API,
                        default=existing.get(
                            CONF_LLM_HASS_API,
                            RECOMMENDED_CONVERSATION_OPTIONS[CONF_LLM_HASS_API],
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(options=hass_apis, multiple=True)
                    ),
                }
            ),
        )


class AITaskFlowHandler(ConfigSubentryFlow):
    """Handle the AI Task subentry flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to create an AI Task entity."""
        return await self.async_step_init(user_input)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage AI Task configuration."""
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_MODEL], data=user_input
            )

        try:
            model_options = await _fetch_model_options(self._get_entry())
        except OpenAIError:
            return self.async_abort(reason="cannot_connect")
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected exception")
            return self.async_abort(reason="unknown")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL): SelectSelector(
                        SelectSelectorConfig(
                            options=model_options,
                            mode=SelectSelectorMode.DROPDOWN,
                            sort=True,
                        ),
                    ),
                }
            ),
        )
