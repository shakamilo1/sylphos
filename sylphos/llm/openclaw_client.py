from __future__ import annotations

"""Factory, exceptions, and speech adapter for OpenClaw integration."""

import re
from dataclasses import replace

from sylphos.config.settings import OpenClawSettings, get_openclaw_settings
from sylphos.llm.base import BaseAgentClient


class OpenClawError(Exception):
    """Base exception for OpenClaw integration errors."""


class OpenClawConnectionError(OpenClawError):
    """Gateway is unreachable or the connection failed."""


class OpenClawAuthError(OpenClawError):
    """OpenClaw rejected authentication or authorization."""


class OpenClawResponseError(OpenClawError):
    """OpenClaw returned malformed, empty, or failed content."""


class OpenClawTimeoutError(OpenClawError):
    """OpenClaw request exceeded the configured timeout."""


_CODE_FENCE_RE = re.compile(r"```(?:[^\n`]*)?\n?|```", re.MULTILINE)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MARKDOWN_MARK_RE = re.compile(r"(?<!\w)([*_~`]{1,3})(?!\w)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_LIST_MARK_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
_ORDERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_QUOTE_RE = re.compile(r"^\s*>\s?", re.MULTILINE)
_RULE_RE = re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE)
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


class SpeechReplyAdapter:
    """Convert full OpenClaw text into a concise CosyVoice-friendly reply."""

    def __init__(self, *, max_spoken_chars: int) -> None:
        self.max_spoken_chars = max(1, max_spoken_chars)

    def adapt(self, raw_text: str) -> str:
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        text = _CODE_FENCE_RE.sub("", text)
        text = _MARKDOWN_LINK_RE.sub(r"\1", text)
        text = _HEADING_RE.sub("", text)
        text = _LIST_MARK_RE.sub("", text)
        text = _ORDERED_LIST_RE.sub("", text)
        text = _QUOTE_RE.sub("", text)
        text = _RULE_RE.sub("", text)
        text = _MARKDOWN_MARK_RE.sub("", text)
        text = _WHITESPACE_RE.sub(" ", text)
        text = _BLANK_LINES_RE.sub("\n\n", text).strip()
        if len(text) <= self.max_spoken_chars:
            return text

        suffix = "后面的内容我已经保留在日志里。"
        limit = max(1, self.max_spoken_chars - len(suffix))
        shortened = text[:limit].rstrip()
        return f"{shortened}{suffix}"


def create_openclaw_client(settings: OpenClawSettings | None = None) -> BaseAgentClient:
    """Create the default OpenClaw agent client for Sylphos Runtime."""

    from sylphos.llm.openclaw_http_client import OpenClawHTTPClient

    return OpenClawHTTPClient(settings=settings or get_openclaw_settings())


def with_openclaw_overrides(settings: OpenClawSettings, **overrides) -> OpenClawSettings:
    """Return a settings copy with test/runtime overrides applied."""

    return replace(settings, **overrides)
