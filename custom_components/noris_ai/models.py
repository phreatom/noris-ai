"""Model listing helpers for the ai.noris.de gateway."""

from __future__ import annotations

from openai import AsyncOpenAI
from openai.types import Model

from homeassistant.helpers.selector import SelectOptionDict

from .const import AUDIO_MODEL_PATTERN, DEFAULT_MODEL, TTS_MODEL_PATTERN

# Rerankers, embedding models and tiny draft models cannot act as
# chat/agent models.
_EXCLUDED_SUBSTRINGS = ("reranker", "harrier", "embedding")


def is_selectable_model(model_id: str) -> bool:
    """Return True if the model should be offered in the chat picker.

    Besides the excluded name substrings, transcription (Voxtral, Whisper) and
    speech-synthesis (Kokoro, CosyVoice) models are filtered out by name:
    they are not chat models, and the gateway catalog's modality metadata
    cannot be used for this (see ``AUDIO_MODEL_PATTERN`` in const.py).
    """
    lowered = model_id.lower()
    if any(part in lowered for part in _EXCLUDED_SUBSTRINGS):
        return False
    return not (
        AUDIO_MODEL_PATTERN.search(model_id) or TTS_MODEL_PATTERN.search(model_id)
    )


def _channel_from_id(model_id: str) -> str | None:
    """Extract the deployment channel from a model id.

    Model ids follow the pattern ``vllm/<channel>/<slug>`` (e.g.
    ``vllm/release/qwen3.8-27b``, ``vllm/qsu/glm-5-3``).  The channel
    distinguishes production (``release``) from staging (``qsu``)
    deployments that share the same display name.
    """
    parts = model_id.split("/")
    if len(parts) >= 3 and parts[0] == "vllm":
        return parts[1]
    return None


def model_label(model: Model) -> str:
    """Human-readable label with channel disambiguation.

    The gateway serves the same model under multiple channels (e.g.
    ``release`` and ``qsu``) with identical display names.  Appending the
    channel prevents ambiguous duplicates in the model picker.
    """
    extras = model.model_extra or {}
    name = extras.get("name")
    if isinstance(name, str) and name.strip():
        channel = _channel_from_id(model.id)
        if channel:
            return f"{name} ({channel})"
        return name
    return model.id


def sort_key(model: Model) -> tuple[int, str]:
    """Sort on-prem vllm models first, then by label."""
    group = 0 if model.id.startswith("vllm/") else 1
    return (group, model_label(model).lower())


def default_model(options: list[SelectOptionDict]) -> str | None:
    """Pick the best default from the live model list.

    The gateway occasionally renames models with channel prefixes
    (e.g. ``vllm/gpt-oss-120b`` -> ``vllm/release/gpt-oss-120b``), so the
    preferred model is matched by exact id first, then by suffix, before
    falling back to the first on-prem model in the list.
    """
    values = [option["value"] for option in options]
    if DEFAULT_MODEL in values:
        return DEFAULT_MODEL
    suffix = "/" + DEFAULT_MODEL.removeprefix("vllm/")
    for value in values:
        if value.startswith("vllm/") and value.endswith(suffix):
            return value
    return next(
        (value for value in values if value.startswith("vllm/")),
        values[0] if values else None,
    )


async def async_get_model_options(client: AsyncOpenAI) -> list[SelectOptionDict]:
    """Fetch, filter and sort the selectable models."""
    page = await client.with_options(timeout=10.0).models.list()
    models = [m for m in page.data if is_selectable_model(m.id)]
    models.sort(key=sort_key)
    return [
        SelectOptionDict(value=model.id, label=model_label(model)) for model in models
    ]


def _is_audio_model(model: Model) -> bool:
    """Return True for models that can transcribe audio.

    The gateway catalog's modality metadata is unreliable for audio models
    (Voxtral reports text-only input), so transcription models are detected by
    name: ``AUDIO_MODEL_PATTERN`` over the model id and, when present, over
    the ``hugging_face_id`` metadata (the stronger signal — it is null for
    many models, hence the fallback to the id).
    """
    extra = getattr(model, "model_extra", None) or {}
    hugging_face_id = extra.get("hugging_face_id") or ""
    return bool(
        AUDIO_MODEL_PATTERN.search(hugging_face_id)
        or AUDIO_MODEL_PATTERN.search(model.id)
    )


def is_stt_model(model: Model) -> bool:
    """Return True for gateway-hosted models usable as a transcription engine.

    Only ``vllm/``-prefixed models are offered: external audio models would
    leave the gateway's data-privacy envelope.
    """
    return model.id.startswith("vllm/") and _is_audio_model(model)


def is_tts_model(model: Model) -> bool:
    """Return True for models that can synthesise speech.

    Like audio detection, speech capability cannot be read from the catalog's
    modality metadata; speech models live under their own providers
    (Kokoro-TTS/, Cosyvoice3/) and are matched by name. The ``vllm/`` prefix is
    deliberately NOT required here.
    """
    return bool(TTS_MODEL_PATTERN.search(model.id))


async def async_get_audio_model_options(
    client: AsyncOpenAI,
) -> list[SelectOptionDict]:
    """Fetch and sort the transcription-capable models."""
    page = await client.with_options(timeout=10.0).models.list()
    models = [m for m in page.data if is_stt_model(m)]
    models.sort(key=sort_key)
    return [
        SelectOptionDict(value=model.id, label=model_label(model)) for model in models
    ]


async def async_get_speech_model_options(
    client: AsyncOpenAI,
) -> list[SelectOptionDict]:
    """Fetch and sort the speech-synthesis models."""
    page = await client.with_options(timeout=10.0).models.list()
    models = [m for m in page.data if is_tts_model(m)]
    models.sort(key=sort_key)
    return [
        SelectOptionDict(value=model.id, label=model_label(model)) for model in models
    ]
