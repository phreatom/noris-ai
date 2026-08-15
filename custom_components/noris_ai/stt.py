"""Speech-to-text support for noris AI."""

from __future__ import annotations

from collections.abc import AsyncIterable

import openai

from homeassistant.components import stt
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_MODEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NorisAIConfigEntry
from .const import (
    DOMAIN,
    LOGGER,
    STT_SUBENTRY_TYPE,
    STT_SUPPORTED_LANGUAGES,
    STT_TIMEOUT,
)
from .helpers import pcm_to_wav

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: NorisAIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up speech-to-text entities."""
    for subentry in config_entry.get_subentries_of_type(STT_SUBENTRY_TYPE):
        async_add_entities(
            [NorisAISttEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class NorisAISttEntity(stt.SpeechToTextEntity):
    """noris AI speech-to-text engine.

    Does not extend NorisAIEntity: that base class exists to drive the chat-log
    loop (tools, thinking extraction), none of which applies to transcription.
    """

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        entry: NorisAIConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Initialize the speech-to-text entity."""
        self.entry = entry
        self.subentry = subentry
        self.model = subentry.data[CONF_MODEL]
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="noris network AG",
            model=self.model,
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    @property
    def supported_languages(self) -> list[str]:
        """Return the languages the transcription model supports."""
        return STT_SUPPORTED_LANGUAGES

    @property
    def supported_formats(self) -> list[stt.AudioFormats]:
        """Return the supported audio formats."""
        return [stt.AudioFormats.WAV]

    @property
    def supported_codecs(self) -> list[stt.AudioCodecs]:
        """Return the supported audio codecs."""
        return [stt.AudioCodecs.PCM]

    @property
    def supported_bit_rates(self) -> list[stt.AudioBitRates]:
        """Return the supported bit rates."""
        return [stt.AudioBitRates.BITRATE_16]

    @property
    def supported_sample_rates(self) -> list[stt.AudioSampleRates]:
        """Return the supported sample rates."""
        return [stt.AudioSampleRates.SAMPLERATE_16000]

    @property
    def supported_channels(self) -> list[stt.AudioChannels]:
        """Return the supported channel counts."""
        return [stt.AudioChannels.CHANNEL_MONO]

    async def async_process_audio_stream(
        self, metadata: stt.SpeechMetadata, stream: AsyncIterable[bytes]
    ) -> stt.SpeechResult:
        """Transcribe an audio stream.

        Never raises: a failure is reported as an ERROR result so the pipeline
        can tell the user, rather than propagating into the voice satellite.
        """
        audio = b""
        async for chunk in stream:
            audio += chunk

        if not audio:
            LOGGER.debug("Empty audio stream, nothing to transcribe")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        # The gateway rejects headerless PCM with "Invalid or unsupported
        # audio file", so the samples need a WAV container.
        wav_audio = pcm_to_wav(
            audio,
            metadata.sample_rate.value,
            metadata.bit_rate.value // 8,
            metadata.channel.value,
        )

        client = self.entry.runtime_data

        try:
            # response_format is left at its default: the gateway mishandles
            # "text" by nesting the whole JSON body inside the text field.
            response = await client.with_options(
                timeout=STT_TIMEOUT
            ).audio.transcriptions.create(
                file=("audio.wav", wav_audio, "audio/wav"),
                model=self.model,
                language=metadata.language.split("-")[0],
            )
        # AuthenticationError and PermissionDeniedError subclass
        # APIStatusError, which subclasses OpenAIError, so this ordering
        # (auth -> APIStatusError -> APITimeoutError -> OpenAIError) is
        # load-bearing: reordering it silently breaks the reauth path.
        except (openai.AuthenticationError, openai.PermissionDeniedError) as err:
            LOGGER.error("Authentication failed during transcription: %s", err)
            self.entry.async_start_reauth(self.hass)
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        except openai.APIStatusError as err:
            if err.status_code == 404:
                LOGGER.error(
                    "Model %s does not support transcription. Reconfigure the "
                    "speech-to-text entity to use an audio model",
                    self.model,
                )
            else:
                LOGGER.error("Error talking to transcription API: %s", err)
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        except openai.APITimeoutError:
            LOGGER.error("Transcription timed out after %s seconds", STT_TIMEOUT)
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)
        except openai.OpenAIError as err:
            LOGGER.error("Error talking to transcription API: %s", err)
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        text = (response.text or "").strip()
        if not text:
            LOGGER.warning("Transcription returned an empty result")
            return stt.SpeechResult(None, stt.SpeechResultState.ERROR)

        # Transcripts are voice content: debug level only, never higher.
        LOGGER.debug("Transcribed %d bytes of audio", len(audio))
        return stt.SpeechResult(text, stt.SpeechResultState.SUCCESS)
