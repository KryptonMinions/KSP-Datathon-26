"""Zoho Catalyst REST access — the single seam for every Catalyst API call
(Cache, SmartBrowz today; Stratus/QuickML as they're wired in), matching the
existing app/supabase.py / app/llm/client.py pattern (plain httpx, no vendor
SDK — O-3's "no vendor SDK" convention extended to Catalyst).

All endpoints share one OAuth2 refresh-token exchange
(accounts.zoho.<tld>/oauth/v2/token) regardless of which Catalyst service is
being called — verified live against Cache and SmartBrowz (browser360) before
being centralized here.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

from app.config import Settings


class CatalystError(Exception):
    pass


class _TokenCache:
    """Process-global cached access token, refreshed ~60s before expiry."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock_holder: bool = False

    async def get(self, settings: Settings) -> str:
        now = time.monotonic()
        if self._token and now < self._expires_at:
            return self._token
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                settings.catalyst_oauth_token_url,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.catalyst_oauth_client_id,
                    "client_secret": settings.catalyst_oauth_client_secret,
                    "refresh_token": settings.catalyst_oauth_refresh_token,
                },
            )
        if resp.status_code != 200:
            raise CatalystError(f"Catalyst OAuth refresh failed: {resp.status_code} {resp.text}")
        body = resp.json()
        self._token = body["access_token"]
        self._expires_at = now + body.get("expires_in", 3600) - 60
        return self._token


_token_cache = _TokenCache()


def _api_base(settings: Settings) -> str:
    """Derives api.catalyst.zoho.<tld> from the token URL's own TLD, so we
    don't need a separate config var for it (verified: baas calls that
    worked used this exact host pattern, distinct from the OAuth response's
    own `api_domain`, which is for other Zoho products, not Catalyst)."""
    tld = urlparse(settings.catalyst_oauth_token_url).netloc.rsplit(".", 1)[-1] or "com"
    return f"https://api.catalyst.zoho.{tld}"


async def catalyst_headers(settings: Settings, *, json_body: bool = True) -> dict[str, str]:
    token = await _token_cache.get(settings)
    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def cache_url(settings: Settings, segment_id: str) -> str:
    return f"{_api_base(settings)}/baas/v1/project/{settings.catalyst_project_id}/segment/{segment_id}/cache"


async def convert_html_to_pdf(html: str, settings: Settings) -> bytes:
    """SmartBrowz (internal service name: browser360) HTML->PDF. Verified
    live: POST {api_base}/browser360/v1/project/{id}/convert with
    {"output_options": {"output_type": "pdf"}, "html": ...} returns raw PDF
    bytes directly (content-type: application/pdf) — no Stratus round trip
    needed for a stateless generate-and-return flow."""
    url = f"{_api_base(settings)}/browser360/v1/project/{settings.catalyst_project_id}/convert"
    headers = await catalyst_headers(settings)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url, headers=headers,
            json={"output_options": {"output_type": "pdf"}, "html": html},
        )
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF-"):
        raise CatalystError(f"SmartBrowz PDF generation failed: {resp.status_code} {resp.text[:300]}")
    return resp.content
