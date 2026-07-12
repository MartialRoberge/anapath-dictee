"""Réinitialise le mot de passe d'un compte MARC (admin ou user) en base.

À exécuter par le propriétaire — le mot de passe reste chez toi, jamais partagé.

Usage :
  cd backend
  DATABASE_URL="postgresql://...frankfurt-postgres.render.com/anapath_database" \
  python ../scripts/reset_password.py --email martial@lexiapro.fr --admin

Le script demande le nouveau mot de passe de façon masquée (getpass) et met à
jour password_hash. Ajoute --admin pour (re)mettre le rôle à admin.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

# Rendre l'import de auth possible (hash bcrypt identique à l'app).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import asyncpg  # noqa: E402
from auth import hash_password  # noqa: E402


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--admin", action="store_true", help="mettre le rôle à admin")
    p.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    args = p.parse_args()

    dsn = args.dsn.replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        print("Fournir --dsn ou DATABASE_URL", file=sys.stderr)
        return 2

    pwd = getpass.getpass(f"Nouveau mot de passe pour {args.email} : ")
    if len(pwd) < 8:
        print("Mot de passe trop court (min 8).", file=sys.stderr)
        return 2
    if getpass.getpass("Confirmer : ") != pwd:
        print("Les mots de passe ne correspondent pas.", file=sys.stderr)
        return 2

    conn = await asyncpg.connect(dsn, ssl="require")
    try:
        existing = await conn.fetchrow(
            "select id, role from users where email=$1", args.email
        )
        pwd_hash = hash_password(pwd)
        if existing:
            role = "admin" if args.admin else existing["role"]
            await conn.execute(
                "update users set password_hash=$1, role=$2 where email=$3",
                pwd_hash, role, args.email,
            )
            print(f"OK — mot de passe réinitialisé pour {args.email} (rôle {role}).")
        else:
            import uuid

            await conn.execute(
                "insert into users (id, email, password_hash, name, role, is_active) "
                "values ($1,$2,$3,$4,$5,true)",
                str(uuid.uuid4()), args.email, pwd_hash, args.email.split("@")[0],
                "admin" if args.admin else "user",
            )
            print(f"OK — compte créé pour {args.email}.")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
