"""Create the first administrator interactively after a deliberate DB upgrade.

Run from backend/: python bootstrap_admin.py
No password or session secret is accepted from command-line arguments.
"""

from __future__ import annotations

from getpass import getpass

from email_validator import validate_email, EmailNotValidError
from sqlalchemy import select

from app.auth import PASSWORD_HASHER
from app.database import SessionLocal
from app.models import User


def main() -> int:
    with SessionLocal() as session:
        if session.scalar(select(User.id).where(User.role == "ADMIN", User.is_active.is_(True))):
            print("An active administrator already exists; no changes made.")
            return 1
        try:
            email = validate_email(input("Admin e-posta: ").strip(), check_deliverability=False).normalized.lower()
        except EmailNotValidError:
            print("Invalid email; no changes made.")
            return 1
        if session.scalar(select(User.id).where(User.email == email)):
            print("Account already exists; no changes made.")
            return 1
        name = input("Görünen ad: ").strip()
        password = getpass("Parola (en az 12 karakter): ")
        confirm = getpass("Parola tekrar: ")
        if not name or len(name) > 100 or not 12 <= len(password) <= 128 or password != confirm:
            print("Invalid name or password; no changes made.")
            return 1
        session.add(User(email=email, display_name=name, password_hash=PASSWORD_HASHER.hash(password),
                         role="ADMIN", is_active=True))
        session.commit()
        print("Administrator created.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
