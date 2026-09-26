"""Voice input module: browser mic clips -> Gemini STT -> transcript."""

from .transcription import (
    GeminiClipTranscriber,
    UnsupportedAudioFormatError,
    VoiceConfigurationError,
    VoiceProviderError,
    decode_audio_b64,
    normalize_transcribe_mime_type,
    resolve_voice_api_key,
)

__all__ = [
    "GeminiClipTranscriber",
    "UnsupportedAudioFormatError",
    "VoiceConfigurationError",
    "VoiceProviderError",
    "decode_audio_b64",
    "normalize_transcribe_mime_type",
    "resolve_voice_api_key",
]
