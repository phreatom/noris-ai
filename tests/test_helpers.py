"""Tests for the audio container helper."""

from __future__ import annotations

import io
import wave

import pytest

from custom_components.noris_ai.helpers import pcm_to_wav

# 100 frames of 16-bit mono silence.
PCM = b"\x00\x00" * 100


def test_pcm_to_wav_writes_a_riff_header() -> None:
    """The result is a RIFF/WAVE container, which the gateway requires."""
    result = pcm_to_wav(PCM, 16000, 2, 1)

    assert result.startswith(b"RIFF")
    assert result[8:12] == b"WAVE"


@pytest.mark.parametrize(
    ("rate", "width", "channels", "payload"),
    [
        (16000, 2, 1, b"\x00\x00" * 100),
        # A second, distinct combination: 8 kHz, 1-byte samples, stereo.
        # Catches a hardcoded setsampwidth(2)/setframerate(16000) that the
        # first case alone (which matches those literals) cannot.
        (8000, 1, 2, bytes(range(200)) * 2),
    ],
)
def test_pcm_to_wav_round_trips_parameters(
    rate: int, width: int, channels: int, payload: bytes
) -> None:
    """Channel count, sample width and frame rate survive the round trip."""
    result = pcm_to_wav(payload, rate, width, channels)

    with wave.open(io.BytesIO(result), "rb") as wav_file:
        assert wav_file.getnchannels() == channels
        assert wav_file.getsampwidth() == width
        assert wav_file.getframerate() == rate
        assert wav_file.getnframes() == len(payload) // (width * channels)


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
