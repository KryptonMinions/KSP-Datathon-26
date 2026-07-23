"""Thin glue around Supabase's REST APIs (GoTrue + PostgREST).

Kept to plain httpx calls rather than the supabase-py SDK per
AUTH_ARCHITECTURE_6.md's framing of this as "a small, contained piece of
backend glue" -- a lookup plus one Supabase call.
"""

import httpx

from app.config import Settings
from app.roles import Role


class InvalidCredentials(Exception):
    """Username has no synthetic-email mapping, or the password was wrong."""


class SupabaseError(Exception):
    """Unexpected error talking to Supabase."""


def _synthetic_email(username: str, settings: Settings) -> str:
    return f"{username}@{settings.synthetic_email_domain}"


async def lookup_synthetic_email(username: str, settings: Settings) -> str | None:
    """Look up the synthetic email for a username via the provisioning record.

    Uses the project's secret key so this read bypasses RLS -- the
    `user_directory` table itself has RLS enabled with no client-facing
    policies (see sql/schema.sql), so only server-side, secret-key access
    can ever read it.
    """
    async with httpx.AsyncClient(base_url=settings.supabase_url) as client:
        resp = await client.get(
            "/rest/v1/user_directory",
            params={"username": f"eq.{username}", "select": "synthetic_email"},
            headers={
                "apikey": settings.supabase_secret_key,
                "Authorization": f"Bearer {settings.supabase_secret_key}",
            },
        )
    if resp.status_code != 200:
        raise SupabaseError(f"user_directory lookup failed: {resp.status_code} {resp.text}")
    rows = resp.json()
    if not rows:
        return None
    return rows[0]["synthetic_email"]


async def sign_in_with_password(email: str, password: str, settings: Settings) -> dict:
    """Resolve a Supabase session/JWT for the given (synthetic email, password)."""
    async with httpx.AsyncClient(base_url=settings.supabase_url) as client:
        resp = await client.post(
            "/auth/v1/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
            headers={"apikey": settings.supabase_publishable_key},
        )
    if resp.status_code == 400:
        raise InvalidCredentials("Invalid username or password")
    if resp.status_code != 200:
        raise SupabaseError(f"sign-in failed: {resp.status_code} {resp.text}")
    return resp.json()


async def admin_create_user(
    username: str,
    password: str,
    role: Role,
    settings: Settings,
    officer_id: str | None = None,
) -> dict:
    """Provision a demo account: create the Supabase Auth user (secret key
    only) with app_metadata.role (+ optional app_metadata.officer_id, the
    trusted officer-identity source per ORCHESTRATOR_STEERING.md O-11), then
    record the username -> synthetic email mapping used at login time.
    """
    email = _synthetic_email(username, settings)
    app_metadata: dict[str, str] = {"role": role.value}
    if officer_id:
        app_metadata["officer_id"] = officer_id
    async with httpx.AsyncClient(base_url=settings.supabase_url) as client:
        create_resp = await client.post(
            "/auth/v1/admin/users",
            json={
                "email": email,
                "password": password,
                "email_confirm": True,
                "app_metadata": app_metadata,
            },
            headers={
                "apikey": settings.supabase_secret_key,
                "Authorization": f"Bearer {settings.supabase_secret_key}",
            },
        )
        if create_resp.status_code not in (200, 201):
            raise SupabaseError(
                f"user creation failed: {create_resp.status_code} {create_resp.text}"
            )
        user = create_resp.json()

        directory_resp = await client.post(
            "/rest/v1/user_directory",
            json={"username": username, "synthetic_email": email},
            headers={
                "apikey": settings.supabase_secret_key,
                "Authorization": f"Bearer {settings.supabase_secret_key}",
                "Prefer": "return=minimal",
            },
        )
        if directory_resp.status_code not in (200, 201, 204):
            raise SupabaseError(
                f"user_directory insert failed: "
                f"{directory_resp.status_code} {directory_resp.text}"
            )

    return user
