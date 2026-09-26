"""Bounded Google Gen AI SDK calls shared by chat, extraction and voice."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

GOOGLE_TIMEOUT_MS = 30_000


def generate(
    *,
    api_key: str,
    model: str,
    prompt: str,
    system_instruction: str | None = None,
    max_output_tokens: int,
    temperature: float | None = None,
    response_mime_type: str | None = None,
    response_schema: dict[str, Any] | None = None,
    media: bytes | None = None,
    media_mime_type: str | None = None,
) -> str:
    """Make one synchronous request; callers place it in a worker thread."""
    if not api_key:
        raise RuntimeError("Google AI API key is not configured")
    if (media is None) != (media_mime_type is None):
        raise ValueError("media and media_mime_type must be supplied together")
    contents: str | list[str | types.Part] = prompt
    if media is not None and media_mime_type is not None:
        contents = [prompt, types.Part.from_bytes(data=media, mime_type=media_mime_type)]
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        response_mime_type=response_mime_type,
        response_schema=response_schema,
    )
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=GOOGLE_TIMEOUT_MS),
    )
    try:
        response = client.models.generate_content(model=model, contents=contents, config=config)
        return response.text or ""
    finally:
        client.close()
