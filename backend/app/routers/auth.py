from fastapi import APIRouter, HTTPException, status

from app.schemas import CurrentUser, LoginRequest, LoginResponse, SessionUser
from app.security import CurrentUserDep, SettingsDep
from app.supabase import InvalidCredentials, SupabaseError, lookup_synthetic_email, sign_in_with_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, settings: SettingsDep) -> LoginResponse:
    """Backend-mediated username+password login (AUTH_ARCHITECTURE_4.md,
    Login Identifier - Path A). The client never sees or constructs the
    synthetic email; it only ever sends/receives username/password and a
    session.
    """
    try:
        email = await lookup_synthetic_email(body.username, settings)
        if email is None:
            # Same generic error as a wrong password -- do not leak whether
            # the username exists.
            raise InvalidCredentials()
        session = await sign_in_with_password(email, body.password, settings)
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    except SupabaseError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Authentication service unavailable",
        )

    role = (session["user"].get("app_metadata") or {}).get("role")
    return LoginResponse(
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        expires_in=session["expires_in"],
        token_type=session["token_type"],
        user=SessionUser(id=session["user"]["id"], role=role),
    )


@router.get("/me")
async def me(current_user: CurrentUserDep) -> CurrentUser:
    """Returns the server-verified identity for the caller's JWT.

    Intended for the frontend's post-login redirect check ("If verified
    role != picked shell, redirect to correct shell" -- Role Authority Rule)
    - not as an authorization gate. Actual data access control lives at the
    RLS layer, not here.
    """
    return current_user
