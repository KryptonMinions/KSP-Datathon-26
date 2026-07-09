import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sarvamai import AsyncSarvamAI
from sarvamai.core.api_error import ApiError

from app.schemas import VoiceTranscribeResponse
from app.security import CurrentUserDep, SettingsDep

router = APIRouter(prefix="/voice", tags=["voice"])

# Generous proxy for the client's 60s recording cap (VOICE_INTAKE_STEERING.md
# §2/§3) -- the client already enforces duration; this just bounds payload size.
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def _normalize_language(value: str | None) -> str | None:
    """Sarvam reports language codes like "kn-IN" / "en-IN"; the client only
    ever needs the bare `en` | `kn` tag (VOICE_INTAKE_STEERING.md §3)."""
    if not value:
        return None
    code = value.split("-")[0].lower()
    return code if code in ("en", "kn") else None


def _sarvam_content_type(content_type: str | None) -> str:
    """Browsers' MediaRecorder tags its blob "audio/webm;codecs=opus", but
    Sarvam matches Content-Type against an exact allowlist (no parameters)
    and 400s on anything else -- strip to the bare MIME type it expects."""
    base = (content_type or "").split(";")[0].strip().lower()
    return base or "audio/webm"


@router.post("/transcribe")
async def transcribe(
    current_user: CurrentUserDep,
    settings: SettingsDep,
    audio_file: UploadFile = File(...),
) -> VoiceTranscribeResponse:
    """Speech-to-text for voice-sourced Ask input (VOICE_INTAKE_STEERING.md
    Phase A). Returns the code-mixed transcript as Sarvam produced it --
    no translation, no orchestrator/query wiring. The client places the
    result in the editable Ask input box; nothing here auto-sends it.
    """
    if not settings.voice_intake_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice intake disabled")

    audio_bytes = await audio_file.read()
    if not audio_bytes or len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Audio exceeds the allowed size/duration limit",
        )

    client = AsyncSarvamAI(api_subscription_key=settings.sarvam_api_key)
    try:
        result = await client.speech_to_text.transcribe(
            file=(
                audio_file.filename or "recording.webm",
                audio_bytes,
                _sarvam_content_type(audio_file.content_type),
            ),
            model="saaras:v3",
            mode="codemix",
        )
    except ApiError as exc:
        # Never surface raw provider error text to the client (§5).
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Transcription failed",
        ) from exc

    transcript = (result.transcript or "").strip()
    if not transcript:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No speech detected",
        )

    return VoiceTranscribeResponse(
        transcript=transcript,
        detected_language=_normalize_language(result.language_code),
        request_id=result.request_id or str(uuid.uuid4()),
    )
