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
