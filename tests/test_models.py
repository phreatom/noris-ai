"""Tests for the model helper functions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from openai.types import Model

from custom_components.noris_ai.const import DEFAULT_MODEL
from custom_components.noris_ai.models import (
    async_get_audio_model_options,
    async_get_model_options,
    async_get_speech_model_options,
    default_model,
    is_selectable_model,
    is_stt_model,
    is_tts_model,
    model_label,
)
from homeassistant.helpers.selector import SelectOptionDict


def test_filter_excludes_rerankers_and_drafts() -> None:
    assert is_selectable_model("vllm/gpt-oss-120b")
    assert is_selectable_model("anthropic/claude-sonnet-5")
    assert not is_selectable_model("vllm/bge-reranker-v2-m3")
    assert not is_selectable_model("vllm/prod/jina-reranker-v2-base-multilingual")
    assert not is_selectable_model("vllm/harrier-oss-v1-0.6b")
    assert not is_selectable_model("vllm/prod/harrier-oss-v1-0.6b")
    assert not is_selectable_model("vllm/release/qwen3-embedding-8b")


def test_filter_excludes_audio_and_speech_models_from_chat_picker() -> None:
    """Transcription and speech-synthesis models are not chat models.

    The chat picker must not offer Voxtral (a transcription model) or
    Kokoro/CosyVoice (speech synthesis) even though their ids contain none of
    the excluded reranker/draft/embedding substrings.
    """
    assert not is_selectable_model("vllm/qsu/voxtral-small-24b-2507")
    assert not is_selectable_model("vllm/release/whisper-large-v3")
    assert not is_selectable_model("Kokoro-TTS/release/kokoro-tts-german-martin")
    assert not is_selectable_model("Cosyvoice3/release/cosyvoice3-0.5b-rl")
    # A non-vllm chat model stays selectable: the chat picker offers
    # external chat models (anthropic), just not audio/speech ones.
    assert is_selectable_model("anthropic/claude-sonnet-5")


def _options(*values: str) -> list[SelectOptionDict]:
    return [SelectOptionDict(value=value, label=value) for value in values]


def test_default_model_prefers_exact_match() -> None:
    options = _options(
        "vllm/release/glm-5-2", DEFAULT_MODEL, "anthropic/claude-sonnet-5"
    )
    assert default_model(options) == DEFAULT_MODEL


def test_default_model_matches_channel_prefixed_rename() -> None:
    """Gateway renames like vllm/gpt-oss-120b -> vllm/release/gpt-oss-120b."""
    options = _options(
        "vllm/release/glm-5-2",
        "vllm/release/gpt-oss-120b",
        "anthropic/claude-sonnet-5",
    )
    assert default_model(options) == "vllm/release/gpt-oss-120b"


def test_default_model_falls_back_to_first_onprem() -> None:
    options = _options("vllm/release/glm-5-2", "anthropic/claude-sonnet-5")
    assert default_model(options) == "vllm/release/glm-5-2"


def test_default_model_empty_list() -> None:
    assert default_model([]) is None


def test_model_label_uses_display_name_for_anthropic() -> None:
    anthropic = Model.model_construct(
        id="anthropic/claude-sonnet-5",
        created=0,
        object="model",
        owned_by="anthropic",
        name="Claude Sonnet 5",
    )
    vllm = Model(id="vllm/gpt-oss-120b", created=0, object="model", owned_by="vllm")
    assert model_label(anthropic) == "Claude Sonnet 5"
    assert model_label(vllm) == "vllm/gpt-oss-120b"


async def test_options_sorted_vllm_first(mock_models: list[Model]) -> None:
    client = MagicMock()
    client.with_options = MagicMock(return_value=client)
    client.models.list = AsyncMock(return_value=SimpleNamespace(data=mock_models))

    options = await async_get_model_options(client)

    values = [o["value"] for o in options]
    assert values == [
        "vllm/gpt-oss-120b",
        "vllm/qwen3.6-27b",
        "vllm/release/glm-5-2",
        "anthropic/claude-sonnet-5",
    ]
    labels = [o["label"] for o in options]
    assert labels[-1] == "Claude Sonnet 5"


def _client(models: list[Model]) -> MagicMock:
    client = MagicMock()
    client.with_options = MagicMock(return_value=client)
    client.models.list = AsyncMock(return_value=SimpleNamespace(data=models))
    return client


async def test_audio_options_match_by_id_and_hugging_face_id() -> None:
    """Audio options keep name-matched vllm models, sorted, labelled.

    One model matches via its id (Voxtral), one via hugging_face_id metadata
    (Whisper). Chat models, rerankers and non-vllm audio models stay out —
    the stt picker only offers gateway-hosted transcription models.
    """
    models = [
        Model(
            id="vllm/qsu/voxtral-small-24b-2507",
            created=0,
            object="model",
            owned_by="vllm",
        ),
        Model.model_construct(
            id="vllm/qsu/some-audio-deployment",
            created=0,
            object="model",
            owned_by="vllm",
            hugging_face_id="openai/whisper-large-v3",
        ),
        Model(id="vllm/gpt-oss-120b", created=0, object="model", owned_by="vllm"),
        Model(
            id="anthropic/claude-sonnet-5",
            created=0,
            object="model",
            owned_by="anthropic",
        ),
    ]
    # Matches the audio pattern but is not hosted under vllm/ — excluded.
    models.append(
        Model(id="openai/whisper-1", created=0, object="model", owned_by="openai")
    )

    options = await async_get_audio_model_options(_client(models))

    assert [o["value"] for o in options] == [
        "vllm/qsu/some-audio-deployment",
        "vllm/qsu/voxtral-small-24b-2507",
    ]


async def test_audio_options_empty_when_no_match() -> None:
    """A catalog without audio models yields an empty list (flow aborts)."""
    models = [
        Model(id="vllm/gpt-oss-120b", created=0, object="model", owned_by="vllm"),
        Model(id="vllm/bge-reranker-v2-m3", created=0, object="model", owned_by="vllm"),
    ]

    assert await async_get_audio_model_options(_client(models)) == []


async def test_speech_options_match_by_name() -> None:
    """Speech options keep pattern-matched speech models, sorted by label."""
    models = [
        Model(
            id="Kokoro-TTS/release/kokoro-tts-german-martin",
            created=0,
            object="model",
            owned_by="kokoro",
        ),
        Model(
            id="Cosyvoice3/release/cosyvoice3-0.5b-rl",
            created=0,
            object="model",
            owned_by="cosyvoice",
        ),
        Model(id="vllm/gpt-oss-120b", created=0, object="model", owned_by="vllm"),
        # Reranker-like and chat models never appear in the tts picker.
        Model(id="vllm/bge-reranker-v2-m3", created=0, object="model", owned_by="vllm"),
    ]

    options = await async_get_speech_model_options(_client(models))

    assert [o["value"] for o in options] == [
        "Cosyvoice3/release/cosyvoice3-0.5b-rl",
        "Kokoro-TTS/release/kokoro-tts-german-martin",
    ]


async def test_speech_options_empty_when_no_match() -> None:
    """A catalog without speech models yields an empty list (flow aborts)."""
    models = [
        Model(id="vllm/gpt-oss-120b", created=0, object="model", owned_by="vllm"),
    ]

    assert await async_get_speech_model_options(_client(models)) == []


def _model(model_id: str, **extra: str) -> Model:
    return Model.model_construct(
        id=model_id, created=0, object="model", owned_by="vllm", **extra
    )


def test_stt_filter_accepts_voxtral_by_hugging_face_id() -> None:
    """Audio capability is detected from the hugging_face_id metadata."""
    model = _model(
        "vllm/qsu/some-opaque-name",
        hugging_face_id="mistralai/Voxtral-Small-24B-2507",
    )
    assert is_stt_model(model) is True


def test_stt_filter_accepts_whisper_by_id() -> None:
    """A future Whisper deployment is picked up from the model id."""
    assert is_stt_model(_model("vllm/release/whisper-large-v3")) is True


def test_stt_filter_tolerates_missing_hugging_face_id() -> None:
    """A missing hugging_face_id must not raise; many models have none.

    A chat model without the metadata is not a transcription engine.
    """
    assert is_stt_model(_model("vllm/release/gpt-oss-120b")) is False


def test_stt_filter_rejects_chat_models() -> None:
    """Text models are not offered as transcription engines."""
    assert is_stt_model(_model("vllm/qsu/glm-5-2")) is False


def test_tts_filter_accepts_speech_models() -> None:
    """Both speech model families on the gateway are TTS engines."""
    assert is_tts_model(_model("Kokoro-TTS/release/kokoro-tts-german-martin")) is True
    assert is_tts_model(_model("Cosyvoice3/release/cosyvoice3-0.5b-rl")) is True


def test_tts_filter_rejects_chat_and_transcription_models() -> None:
    """Chat models and the transcription model are not synthesisers."""
    assert is_tts_model(_model("vllm/release/gpt-oss-120b")) is False
    assert (
        is_tts_model(
            _model(
                "vllm/qsu/voxtral-small-24b-2507",
                hugging_face_id="mistralai/Voxtral-Small-24B-2507",
            )
        )
        is False
    )
