"""Tests for the response-parsing helpers in entity.py."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import voluptuous as vol

from custom_components.noris_ai.entity import (
    _decode_tool_arguments,
    _extract_thinking,
    _format_structure_output,
    _split_thinking,
    _strip_markdown_fence,
)
from homeassistant.exceptions import HomeAssistantError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"city": "Nurnberg"}', '{"city": "Nurnberg"}'),
        ('```json\n{"city": "Nurnberg"}\n```', '{"city": "Nurnberg"}'),
        ('```\n{"city": "Nurnberg"}\n```', '{"city": "Nurnberg"}'),
        ('```{"city": "Nurnberg"}```', '{"city": "Nurnberg"}'),
    ],
)
def test_strip_markdown_fence(raw: str, expected: str) -> None:
    """Fenced payloads are unwrapped; bare payloads are untouched."""
    assert _strip_markdown_fence(raw) == expected


def test_decode_tool_arguments_plain_json() -> None:
    """Well-formed arguments decode directly."""
    assert _decode_tool_arguments('{"a": 1}') == {"a": 1}


def test_decode_tool_arguments_recovers_from_fence() -> None:
    """Fenced arguments are recovered rather than failing the tool call."""
    assert _decode_tool_arguments('```json\n{"a": 1}\n```') == {"a": 1}


def test_decode_tool_arguments_raises_on_garbage() -> None:
    """Unrecoverable arguments raise a HomeAssistantError."""
    with pytest.raises(HomeAssistantError, match="Unexpected tool argument"):
        _decode_tool_arguments("not json at all")


def test_split_thinking_extracts_think_tags() -> None:
    """Inline <think> markup is split out of the visible content."""
    cleaned, thinking = _split_thinking("<think>hmm</think>Das Licht ist an.")

    assert cleaned == "Das Licht ist an."
    assert thinking == "hmm"


def test_split_thinking_without_tags() -> None:
    """Content without markup passes through with no thinking."""
    assert _split_thinking("Das Licht ist an.") == ("Das Licht ist an.", None)


def test_split_thinking_only_thinking() -> None:
    """Content that is entirely thinking yields None as the answer."""
    cleaned, thinking = _split_thinking("<think>hmm</think>")

    assert cleaned is None
    assert thinking == "hmm"


def test_extract_thinking_prefers_reasoning_field() -> None:
    """vLLM's ``reasoning`` field wins over inline markup."""
    message = SimpleNamespace(
        content="Antwort", model_extra={"reasoning": "weil es dunkel ist"}
    )

    assert _extract_thinking(message) == ("Antwort", "weil es dunkel ist")


def test_extract_thinking_falls_back_to_reasoning_content() -> None:
    """Older vLLM builds expose ``reasoning_content`` instead."""
    message = SimpleNamespace(content="Antwort", model_extra={"reasoning_content": "x"})

    assert _extract_thinking(message) == ("Antwort", "x")


def test_extract_thinking_falls_back_to_inline_markup() -> None:
    """With no reasoning field, inline <think> markup is used."""
    message = SimpleNamespace(content="<think>hmm</think>Antwort", model_extra={})

    assert _extract_thinking(message) == ("Antwort", "hmm")


def test_format_structure_output_builds_strict_schema() -> None:
    """Structured output is requested as a strict JSON schema."""
    result = _format_structure_output("wetter", vol.Schema({vol.Required("t"): str}))

    assert result["type"] == "json_schema"
    assert result["json_schema"]["name"] == "wetter"
    assert result["json_schema"]["strict"] is True
    assert "t" in result["json_schema"]["schema"]["properties"]


def test_format_structure_output_defaults_name() -> None:
    """An empty name falls back to 'data'."""
    result = _format_structure_output("", vol.Schema({}))

    assert result["json_schema"]["name"] == "data"
