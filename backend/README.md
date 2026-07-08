# Backend

FastAPI service implementing `steering-docs/AUTH_ARCHITECTURE_6.md`: username+password
login backed by Supabase Auth (synthetic email under the hood), role stored in
`app_metadata.role`, and JWT verification for protected routes. RLS on the Supabase
side is the sole data-access enforcement point — this app does not re-implement it.

JWTs are verified against Supabase's public JWKS (modern asymmetric signing keys,
ES256), not a legacy HS256 shared secret — this project's tokens are ES256, and a
static-secret check would reject every one of them. See `app/security.py`.

## Setup

1. Copy `.env.example` to `.env` and fill in the Supabase project's URL, publishable
   key, secret key (Project Settings → API Keys → Publishable and secret API keys
   tab), and the frontend's origin for CORS.
2. In the Supabase SQL editor, run `sql/schema.sql` (creates `user_directory` and
   documents the RLS policy pattern to apply to case/record tables).
3. In the Dashboard: disable **only** "Allow new users to sign up"
   (Authentication → Sign In / Providers). Leave the Email provider itself enabled —
   it's what `signInWithPassword` runs on for every user, not just public self-signup.
4. Provision demo accounts:
   ```
   cp scripts/demo_users.example.json scripts/demo_users.json  # edit passwords first
   python -m scripts.provision_users --from-json scripts/demo_users.json
   ```
5. Run the API:
   ```
   uvicorn app.main:app --reload
   ```

## Endpoints

- `POST /auth/login` — `{username, password}` → Supabase session/JWT.
- `GET /auth/me` — verifies the bearer JWT, returns `{id, role}` from
  `app_metadata.role`. For frontend redirect checks, not authorization.
