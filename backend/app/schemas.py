from pydantic import BaseModel

from app.roles import Role


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionUser(BaseModel):
    id: str
    role: Role


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    user: SessionUser


class CurrentUser(BaseModel):
    id: str
    role: Role


class VoiceTranscribeResponse(BaseModel):
    """Sarvam Saaras v3 transcript only -- no translation, no downstream
    processing (VOICE_INTAKE_STEERING.md §3, Phase A)."""

    transcript: str
    detected_language: str | None = None
    request_id: str | None = None
