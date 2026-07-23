"""Admin-only demo account provisioning (AUTH_ARCHITECTURE_6.md Build
Checklist step 2). Run against a Supabase project with public signup
disabled, using the project's secret key (never sent to any client).

Usage:
    python -m scripts.provision_users --username io.demo --password '<pw>' --role investigating_officer
    python -m scripts.provision_users --from-json scripts/demo_users.json

demo_users.json is a list of {"username", "password", "role"} objects.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.roles import Role  # noqa: E402
from app.supabase import SupabaseError, admin_create_user  # noqa: E402


async def provision_one(
    username: str, password: str, role: Role, officer_id: str | None = None
) -> None:
    settings = get_settings()
    try:
        await admin_create_user(username, password, role, settings, officer_id)
        suffix = f", officer_id={officer_id}" if officer_id else ""
        print(f"provisioned {username} ({role.value}{suffix})")
    except SupabaseError as exc:
        print(f"FAILED {username}: {exc}", file=sys.stderr)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--role", choices=[r.value for r in Role])
    parser.add_argument("--officer-id")
    parser.add_argument("--from-json", type=Path)
    args = parser.parse_args()

    if args.from_json:
        accounts = json.loads(args.from_json.read_text())
        for account in accounts:
            await provision_one(
                account["username"],
                account["password"],
                Role(account["role"]),
                account.get("officer_id"),
            )
    elif args.username and args.password and args.role:
        await provision_one(args.username, args.password, Role(args.role), args.officer_id)
    else:
        parser.error("either --from-json, or all of --username/--password/--role")


if __name__ == "__main__":
    asyncio.run(main())
