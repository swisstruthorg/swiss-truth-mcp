"""
swiss-truth-adduser — Ersten Admin-Benutzer anlegen

Verwendung:
  swiss-truth-adduser                          # interaktiv
  swiss-truth-adduser admin admin@example.com  # Username + E-Mail als Argumente
"""
from __future__ import annotations

import asyncio
import getpass
import sys
import uuid

from swiss_truth_mcp.auth.security import hash_password
from swiss_truth_mcp.db.neo4j_client import get_driver, close_driver
from swiss_truth_mcp.db.schema import setup_schema
from swiss_truth_mcp.db import queries
from swiss_truth_mcp.validation.trust import now_iso


async def _run() -> None:
    args = sys.argv[1:]

    print("👤  Swiss Truth — Benutzer anlegen")
    print("=" * 40)

    # Username
    if len(args) >= 1:
        username = args[0]
    else:
        username = input("Benutzername: ").strip()
    if not username:
        print("❌  Kein Benutzername angegeben.", file=sys.stderr)
        sys.exit(1)

    # E-Mail
    if len(args) >= 2:
        email = args[1]
    else:
        email = input("E-Mail: ").strip()

    # Rolle
    role_input = input("Rolle [admin/reviewer] (Standard: admin): ").strip().lower()
    role = role_input if role_input in ("admin", "reviewer") else "admin"

    # Passwort
    password = getpass.getpass("Passwort: ")
    if len(password) < 8:
        print("❌  Passwort muss mindestens 8 Zeichen haben.", file=sys.stderr)
        sys.exit(1)
    confirm = getpass.getpass("Passwort bestätigen: ")
    if password != confirm:
        print("❌  Passwörter stimmen nicht überein.", file=sys.stderr)
        sys.exit(1)

    driver = get_driver()
    async with driver.session() as session:
        await setup_schema(session)

        existing = await queries.get_user_by_username(session, username)
        if existing:
            print(f"❌  Benutzername '{username}' ist bereits vergeben.", file=sys.stderr)
            await close_driver()
            sys.exit(1)

        await queries.create_user(session, {
            "id":            str(uuid.uuid4()),
            "username":      username,
            "email":         email,
            "password_hash": hash_password(password),
            "role":          role,
            "active":        True,
            "created_at":    now_iso(),
        })

    await close_driver()

    print()
    print(f"✅  Benutzer '{username}' ({role}) erfolgreich angelegt!")
    print(f"→  Login: https://swisstruth.org/login")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
