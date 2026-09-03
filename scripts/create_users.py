"""Create or update the two demo users FunnelIQ auth relies on for phase 4.

Idempotent: if a user with the target email already exists, only its
app_metadata is updated -- it is never recreated, deleted, or duplicated,
and its password is never touched. Passwords are never read from CLI args,
env vars or a file; they're typed at a getpass prompt and never touch disk,
argv, os.environ, or stdout/stderr. See docs/planning/PHASE4.md, decisions
D5 and D5a, for the contract this implements.

Usage:
    python scripts/create_users.py

Requires SUPABASE_URL and SUPABASE_SECRET_KEY in .env (see .env.example).
Never prints either value, and never prints a password or token.
"""
from __future__ import annotations

import getpass
import os
import sys

from dotenv import load_dotenv

# The two demo users phase 4 needs -- see PHASE4.md (D5).
# northbound: the ordinary flow. noorg: demonstrates the 403 rejection.
DEMO_USERS = [
    {
        "email": "demo-northbound@funneliq.example.com",
        "app_metadata": {"organization": "northbound", "role": "team_member"},
    },
    {
        "email": "demo-noorg@funneliq.example.com",
        "app_metadata": {"role": "team_member"},  # deliberately no "organization" key
    },
]


def make_client():
    """Build the Supabase admin client from .env. Never prints SUPABASE_SECRET_KEY."""
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    secret_key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not secret_key:
        print(
            "ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set in .env "
            "(see .env.example)",
            file=sys.stderr,
        )
        sys.exit(5)
    from supabase import create_client

    return create_client(url, secret_key)


def find_user_by_email(client, email: str):
    """Linear scan over list_users() -- the admin API has no server-side
    email filter, and this project will only ever have a handful of users.
    ponytail: fine at this scale; paginate if that ever changes."""
    for user in client.auth.admin.list_users():
        if user.email == email:
            return user
    return None


def upsert_demo_user(client, email: str, app_metadata: dict, password: str) -> dict:
    """Create the user if absent; otherwise update app_metadata only.

    Never touches the password of an existing user -- re-running this script
    must not silently change a credential someone may already be using.
    """
    existing = find_user_by_email(client, email)
    if existing is None:
        response = client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,  # pre-verified demo user, no email sent
                "app_metadata": app_metadata,
            }
        )
        user = response.user
        action = "created"
    else:
        response = client.auth.admin.update_user_by_id(
            existing.id, {"app_metadata": app_metadata}
        )
        user = response.user
        action = "updated (app_metadata only, password untouched)"

    return {
        "action": action,
        "email": user.email,
        "id": user.id,
        "app_metadata": user.app_metadata,
    }


def main() -> None:
    client = make_client()
    results = []
    for spec in DEMO_USERS:
        password = getpass.getpass(f"Password for {spec['email']}: ")
        if not password:
            print(f"ERROR: empty password for {spec['email']}", file=sys.stderr)
            sys.exit(6)
        results.append(
            upsert_demo_user(client, spec["email"], spec["app_metadata"], password)
        )

    print("\nDone. No password, key or token was printed at any point.\n")
    for r in results:
        print(f"- {r['action']}: {r['email']} (id={r['id']}) app_metadata={r['app_metadata']}")


if __name__ == "__main__":
    main()
