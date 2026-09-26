"""
voice/transcription.py - Google Gemini clip transcription helpers.

Current architecture:
    Frontend mic -> mono WAV -> HTTP -> Gemini generateContent STT
    -> transcript -> chat draft textarea.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Final

from app.config import settings
from app.integrations.ai.google import generate

logger = logging.getLogger(__name__)

# Browser recordings are converted to mono WAV before reaching the backend.
AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1

SUPPORTED_TRANSCRIBE_MIME_TYPES: Final[set[str]] = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mp3",
    "audio/mpeg",
    "audio/aiff",
    "audio/aac",
    "audio/ogg",
    "audio/flac",
}
MAX_AUDIO_BYTES = 8 * 1024 * 1024

_MISSING_VOICE_KEY_MESSAGE = (
    "Voice transcription needs GOOGLE_AI_API_KEY or GEMINI_API_KEY. "
    "Add a Google AI Studio key to backend/.env and restart the backend."
)


class VoiceConfigurationError(RuntimeError):
    """Raised when local voice transcription config is missing or invalid."""


class UnsupportedAudioFormatError(ValueError):
    """Raised when the client sends audio Gemini generateContent cannot read."""


class VoiceProviderError(RuntimeError):
    """Raised when Gemini rejects or fails a transcription request."""


def resolve_voice_api_key() -> str:
    """Return the Google key used by voice, accepting Gemini's key as fallback."""
    key = settings.GOOGLE_AI_API_KEY or settings.GEMINI_API_KEY
    if not key:
        raise VoiceConfigurationError(_MISSING_VOICE_KEY_MESSAGE)
    return key


def normalize_transcribe_mime_type(mime_type: str | None) -> str:
    normalized = (mime_type or "audio/wav").split(";", 1)[0].strip().lower()
    if normalized not in SUPPORTED_TRANSCRIBE_MIME_TYPES:
        supported = ", ".join(sorted(SUPPORTED_TRANSCRIBE_MIME_TYPES))
        raise UnsupportedAudioFormatError(
            f"Unsupported voice audio format '{mime_type or 'unknown'}'. "
            f"Send WAV audio from the browser. Supported formats: {supported}."
        )
    return normalized


def matches_audio_signature(data: bytes, mime_type: str) -> bool:
    """Reject obvious MIME spoofing before any paid transcription request."""
    if mime_type in {"audio/wav", "audio/x-wav", "audio/wave"}:
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    if mime_type in {"audio/mp3", "audio/mpeg"}:
        return data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    if mime_type == "audio/aiff":
        return len(data) >= 12 and data[:4] == b"FORM" and data[8:12] in {b"AIFF", b"AIFC"}
    if mime_type == "audio/aac":
        return len(data) >= 2 and data[0] == 0xFF and data[1] & 0xF6 == 0xF0
    if mime_type == "audio/ogg":
        return data.startswith(b"OggS")
    if mime_type == "audio/flac":
        return data.startswith(b"fLaC")
    return False


def _looks_like_model_configuration_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        ("not found" in message and "model" in message)
        or "not supported for generatecontent" in message
        or "listmodels" in message
    )


class GeminiClipTranscriber:
    """
    Thin wrapper around Gemini generateContent for speech-to-text only.

    Usage:
        transcriber = GeminiClipTranscriber()
        transcript = await transcriber.transcribe(audio_bytes, lang="ar")
    """

    def __init__(self) -> None:
        self._api_key = resolve_voice_api_key()

    async def transcribe(
        self,
        audio_bytes: bytes,
        lang: str = "ar",
        mime_type: str = "audio/wav",
    ) -> str:
        """
        Transcribe audio bytes to text using Gemini.

        Args:
            audio_bytes: Raw audio (WAV preferred, 16kHz mono)
            lang: Language hint ('ar', 'en', 'mixed')
            mime_type: Audio MIME type

        Returns:
            Transcript string (Arabic or English depending on input)
        """
        normalized_mime_type = normalize_transcribe_mime_type(mime_type)

        lang_hint = {
            "ar": "Arabic",
            "en": "English",
            "mixed": "Arabic and/or English",
        }.get(lang, "Arabic")

        prompt = (
            f"Transcribe the following audio accurately. "
            f"The speaker is using {lang_hint}. "
            f"Return ONLY the transcript text, nothing else."
        )

        try:
            response = await asyncio.to_thread(
                generate,
                api_key=self._api_key,
                model=settings.GEMINI_TRANSCRIBE_MODEL,
                prompt=prompt,
                max_output_tokens=512,
                media=audio_bytes,
                media_mime_type=normalized_mime_type,
            )
            transcript = response.strip()
            if not transcript:
                raise VoiceProviderError(
                    "Gemini returned an empty transcript. Please try again with a clearer recording."
                )
            logger.info("Transcribed %d bytes -> %d chars", len(audio_bytes), len(transcript))
            return transcript

        except VoiceProviderError:
            raise
        except Exception as exc:
            logger.error("Gemini transcription failed: %s", exc)
            if _looks_like_model_configuration_error(exc):
                raise VoiceProviderError(
                    "Voice transcription is configured with an unavailable Gemini model. "
                    "Set GEMINI_TRANSCRIBE_MODEL=gemini-2.5-flash in backend/.env "
                    "and restart the backend."
                ) from exc
            raise VoiceProviderError(
                "Gemini voice transcription failed. Please try again in a moment."
            ) from exc


def decode_audio_b64(audio_b64: str) -> bytes:
    """Decode base64-encoded audio from the frontend request."""
    if len(audio_b64) > ((MAX_AUDIO_BYTES + 2) // 3) * 4:
        raise ValueError("Audio clip exceeds the 8 MiB limit")
    try:
        data = base64.b64decode(audio_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"Invalid base64 audio data: {exc}") from exc
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise ValueError("Audio clip is empty or exceeds the 8 MiB limit")
    return data
