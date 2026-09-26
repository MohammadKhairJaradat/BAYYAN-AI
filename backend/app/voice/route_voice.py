"""HTTP route for microphone clip transcription."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.voice.transcription import MAX_AUDIO_BYTES

from app.auth.dependencies import get_current_active_user
from app.auth.tier_limits import normalize_tier
from app.auth.usage import reserve_usage, settle_usage
from app.models.connection import get_db
from app.models.database import User

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)


class TranscribeRequest(BaseModel):
    audio_b64: str = Field(min_length=1, max_length=((MAX_AUDIO_BYTES + 2) // 3) * 4)
    lang: str = Field(default="ar", max_length=16)
    mime_type: str = Field(default="audio/wav", max_length=100)


class TranscribeResponse(BaseModel):
    transcript: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(
    payload: TranscribeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    """Transcribe one browser-recorded audio clip into text only."""
    from app.voice.transcription import (
        GeminiClipTranscriber,
        UnsupportedAudioFormatError,
        VoiceConfigurationError,
        VoiceProviderError,
        decode_audio_b64,
        normalize_transcribe_mime_type,
        matches_audio_signature,
    )

    try:
        mime_type = normalize_transcribe_mime_type(payload.mime_type)
        audio_bytes = decode_audio_b64(payload.audio_b64)
        if not matches_audio_signature(audio_bytes, mime_type):
            raise ValueError("Audio contents do not match MIME type")
        transcriber = GeminiClipTranscriber()
        reservation_id = await reserve_usage(
            db, user_id=current_user.id, tier=normalize_tier(current_user.subscription_tier),
            operation="voice", idempotency_key=idempotency_key,
        )
        try:
            transcript = await transcriber.transcribe(
                audio_bytes,
                lang=payload.lang,
                mime_type=mime_type,
            )
        finally:
            await settle_usage(db, reservation_id)
    except HTTPException:
        raise
    except VoiceConfigurationError as exc:
        # Missing key or SDK: surface clearly so the frontend can show a useful error.
        raise HTTPException(status_code=503, detail=str(exc))
    except UnsupportedAudioFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except VoiceProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception:
        logger.exception("STT failed")
        raise HTTPException(status_code=500, detail="Transcription failed. Please try again.")

    return TranscribeResponse(transcript=transcript)
