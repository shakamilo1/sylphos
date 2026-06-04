from __future__ import annotations

"""OpenClaw Gateway OpenAI-compatible HTTP client."""

import asyncio
import json
import logging
import socket
from typing import Any
from urllib import error, request

from sylphos.config.settings import OpenClawSettings, get_openclaw_settings
from sylphos.llm.base import BaseAgentClient
from sylphos.llm.openclaw_client import (
    OpenClawAuthError,
    OpenClawConnectionError,
    OpenClawResponseError,
    OpenClawTimeoutError,
    SpeechReplyAdapter,
)
from sylphos.llm.types import OpenClawResult

_SYSTEM_PROMPT = "你是 Sylphos 的本地语音控制代理。用户通过语音输入，回答要简短、适合语音朗读。如果已经执行了操作，请直接说明结果。"


class OpenClawHTTPClient(BaseAgentClient):
    """Stage-1 OpenClaw client using ``POST /v1/chat/completions``."""

    def __init__(self, *, settings: OpenClawSettings | None = None) -> None:
        self.settings = settings or get_openclaw_settings()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.reply_adapter = SpeechReplyAdapter(max_spoken_chars=self.settings.max_spoken_chars)

    def ask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        active_session_key = session_key or self.settings.session_key
        payload = self._build_payload(text=text, session_key=active_session_key)
        headers = self._build_headers(session_key=active_session_key)
        url = self._chat_completions_url()

        self.logger.info(
            "OpenClaw HTTP request: url=%s model=%s session_key=%s chars=%d token_present=%s",
            url,
            self.settings.model,
            active_session_key,
            len(text),
            bool(self.settings.token),
        )

        response_payload = self._post_json(url=url, payload=payload, headers=headers)
        raw_text, metadata = self._extract_text(response_payload)
        spoken_text = self.reply_adapter.adapt(raw_text)
        if not spoken_text:
            raise OpenClawResponseError("OpenClaw returned content that became empty after speech adaptation.")

        self.logger.info(
            "OpenClaw HTTP response: model=%s session_key=%s raw_chars=%d spoken_chars=%d finish_reason=%s",
            metadata.get("model") or self.settings.model,
            active_session_key,
            len(raw_text),
            len(spoken_text),
            metadata.get("finish_reason"),
        )
        return OpenClawResult(
            raw_text=raw_text,
            spoken_text=spoken_text,
            session_key=active_session_key,
            model=str(metadata.get("model") or self.settings.model),
            metadata=metadata,
        )

    async def aask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        return await asyncio.to_thread(self.ask, text, session_key=session_key)

    def _build_payload(self, *, text: str, session_key: str) -> dict[str, Any]:
        return {
            "model": self.settings.model,
            "user": session_key,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }

    def _build_headers(self, *, session_key: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "x-openclaw-session-key": session_key,
            "x-openclaw-message-channel": self.settings.message_channel,
        }
        if self.settings.token:
            headers["Authorization"] = f"Bearer {self.settings.token}"
        return headers

    def _chat_completions_url(self) -> str:
        return f"{self.settings.base_url.rstrip('/')}/v1/chat/completions"

    def _post_json(self, *, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as resp:
                data = resp.read()
        except error.HTTPError as exc:
            if exc.code == 401:
                raise OpenClawAuthError("OpenClaw authentication failed with HTTP 401.") from exc
            if exc.code == 403:
                raise OpenClawAuthError("OpenClaw authorization failed with HTTP 403.") from exc
            if exc.code == 404:
                raise OpenClawResponseError("OpenClaw chat completions API was not found or is not enabled.") from exc
            raise OpenClawResponseError(f"OpenClaw HTTP error {exc.code}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise OpenClawTimeoutError(f"OpenClaw request timed out after {self.settings.timeout_seconds} seconds.") from exc
        except socket.timeout as exc:
            raise OpenClawTimeoutError(f"OpenClaw request timed out after {self.settings.timeout_seconds} seconds.") from exc
        except error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise OpenClawTimeoutError(
                    f"OpenClaw request timed out after {self.settings.timeout_seconds} seconds."
                ) from exc
            raise OpenClawConnectionError("OpenClaw Gateway is unreachable. Is it running locally?") from exc
        except OSError as exc:
            raise OpenClawConnectionError("OpenClaw Gateway connection failed.") from exc

        try:
            parsed = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenClawResponseError("OpenClaw returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise OpenClawResponseError("OpenClaw returned a non-object JSON response.")
        return parsed

    def _extract_text(self, response_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if "error" in response_payload:
            raise OpenClawResponseError(f"OpenClaw execution failed: {response_payload['error']}")

        choices = response_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise OpenClawResponseError("OpenClaw response is missing choices.")

        first = choices[0]
        if not isinstance(first, dict):
            raise OpenClawResponseError("OpenClaw response choice is malformed.")

        message = first.get("message")
        raw_text = ""
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                raw_text = content
            elif isinstance(content, list):
                raw_text = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        if not raw_text and isinstance(first.get("text"), str):
            raw_text = str(first["text"])
        raw_text = raw_text.strip()
        if not raw_text:
            raise OpenClawResponseError("OpenClaw returned empty content.")

        metadata = {
            "finish_reason": first.get("finish_reason"),
            "usage": response_payload.get("usage"),
            "run_id": response_payload.get("run_id") or response_payload.get("id"),
            "model": response_payload.get("model") or self.settings.model,
            # Keep for UI/debugging only. Do not write raw_response to logs by default:
            # it may contain tool output, local paths, or sensitive content.
            "raw_response": response_payload,
        }
        return raw_text, metadata
