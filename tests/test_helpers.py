"""Tests for the audio container helper."""

from __future__ import annotations

import io
import wave

from custom_components.noris_ai.helpers import pcm_to_wav

# 100 frames of 16-bit mono silence.
PCM = b"\x00\x00" * 100


def test_pcm_to_wav_writes_a_riff_header() -> None:
    """The result is a RIFF/WAVE container, which the gateway requires."""
    result = pcm_to_wav(PCM, 16000, 2, 1)

    assert result.startswith(b"RIFF")
    assert result[8:12] == b"WAVE"


def test_pcm_to_wav_round_trips_parameters() -> None:
    """Channel count, sample width and frame rate survive the round trip."""
    result = pcm_to_wav(PCM, 16000, 2, 1)

    with wave.open(io.BytesIO(result), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 16000
        assert wav_file.getnframes() == 100


def test_pcm_to_wav_preserves_the_payload() -> None:
    """No sample data is lost or altered."""
    payload = bytes(range(256)) * 4
    result = pcm_to_wav(payload, 16000, 2, 1)

    with wave.open(io.BytesIO(result), "rb") as wav_file:
        assert wav_file.readframes(wav_file.getnframes()) == payload


def test_pcm_to_wav_handles_empty_audio() -> None:
    """An empty payload still produces a valid, zero-frame container."""
    result = pcm_to_wav(b"", 16000, 2, 1)

    with wave.open(io.BytesIO(result), "rb") as wav_file:
        assert wav_file.getnframes() == 0
