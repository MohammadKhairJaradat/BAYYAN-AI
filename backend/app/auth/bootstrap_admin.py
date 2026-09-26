"""Explicit local operator command for granting the first administrator role.

Run after the account exists: uv run python -m app.auth.bootstrap_admin USERNAME
"""

import argparse
import asyncio

from sqlalchemy import select

from app.models.connection import async_session_factory
from app.models.database import SecurityAuditEvent, User


async def bootstrap(username: str) -> bool:
    async with async_session_factory() as db:
        user = (await db.execute(select(User).where(User.username == username).with_for_update())).scalar_one_or_none()
        if user is None:
            raise ValueError("Account does not exist; register it first")
        if user.is_admin:
            return False
        user.is_admin = True
        db.add(SecurityAuditEvent(
            action="admin.bootstrap", actor_user_id=user.id, target_user_id=user.id,
        ))
        await db.commit()
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant the first BAYYAN administrator role to an existing account")
    parser.add_argument("username", help="Exact username of an already registered account")
    args = parser.parse_args()
    changed = asyncio.run(bootstrap(args.username))
    print("Administrator role granted" if changed else "Account is already an administrator")


if __name__ == "__main__":
    main()
