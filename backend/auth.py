"""Password hashing utilities — salted SHA256."""

import hashlib
import secrets


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (hash_hex, salt_hex).  If salt is None a random 128-bit salt is
    generated."""
    if salt is None:
        salt = secrets.token_hex(16)          # 128-bit salt
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return h, salt


def verify_password(password: str, hash_hex: str, salt: str) -> bool:
    """Return True iff password matches the stored hash."""
    return hash_password(password, salt)[0] == hash_hex
