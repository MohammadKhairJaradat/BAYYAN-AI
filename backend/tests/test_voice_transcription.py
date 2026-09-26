import pytest

from app.config import settings
from app.voice.transcription import (
    MAX_AUDIO_BYTES,
    GeminiClipTranscriber,
    UnsupportedAudioFormatError,
    VoiceProviderError,
    normalize_transcribe_mime_type,
    resolve_voice_api_key,
    decode_audio_b64,
)


def test_audio_decode_rejects_oversized_and_invalid_base64():
    with pytest.raises(ValueError, match="8 MiB"):
        decode_audio_b64("A" * (((MAX_AUDIO_BYTES + 2) // 3) * 4 + 4))
    with pytest.raises(ValueError, match="Invalid base64"):
        decode_audio_b64("!!!!")


def test_resolve_voice_api_key_prefers_google_ai_key(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "google-ai-key")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")

    assert resolve_voice_api_key() == "google-ai-key"


def test_resolve_voice_api_key_falls_back_to_gemini_key(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "gemini-key")

    assert resolve_voice_api_key() == "gemini-key"


def test_resolve_voice_api_key_requires_a_google_key(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    with pytest.raises(RuntimeError, match="GOOGLE_AI_API_KEY or GEMINI_API_KEY"):
        resolve_voice_api_key()


def test_normalize_transcribe_mime_type_accepts_supported_formats():
    assert normalize_transcribe_mime_type("audio/wav;codecs=1") == "audio/wav"
    assert normalize_transcribe_mime_type("audio/mpeg") == "audio/mpeg"


def test_normalize_transcribe_mime_type_rejects_webm():
    with pytest.raises(UnsupportedAudioFormatError, match="Unsupported voice audio format"):
        normalize_transcribe_mime_type("audio/webm")


@pytest.mark.asyncio
async def test_transcribe_uses_configured_transcribe_model(monkeypatch):
    from app.voice import transcription

    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "google-ai-key")
    monkeypatch.setattr(settings, "GEMINI_TRANSCRIBE_MODEL", "gemini-test-transcriber")
    calls = []
    def fake_generate(**kwargs):
        calls.append(kwargs)
        return "  hello from test  "
    monkeypatch.setattr(transcription, "generate", fake_generate)
    transcriber = GeminiClipTranscriber()

    transcript = await transcriber.transcribe(
        b"RIFF....WAVE",
        lang="ar",
        mime_type="audio/wav",
    )

    assert transcript == "hello from test"
    assert calls[0]["model"] == "gemini-test-transcriber"
    assert calls[0]["media_mime_type"] == "audio/wav"


@pytest.mark.asyncio
async def test_transcribe_maps_gemini_model_errors_to_friendly_message(monkeypatch):
    from app.voice import transcription

    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "google-ai-key")
    def fail_generate(**_kwargs):
        raise Exception(
            "404 models/gemini-2.0-flash-live-preview-04-09 is not found "
            "or is not supported for generateContent. Call ListModels."
        )
    monkeypatch.setattr(transcription, "generate", fail_generate)
    transcriber = GeminiClipTranscriber()

    with pytest.raises(VoiceProviderError, match="GEMINI_TRANSCRIBE_MODEL=gemini-2.5-flash"):
        await transcriber.transcribe(b"RIFF....WAVE", lang="en", mime_type="audio/wav")
