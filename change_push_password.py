#!/usr/bin/env python3
"""
Change the server-wide push password.

Usage:
    python change_push_password.py

This updates the salted SHA256 hash stored in the SQLite database.
The push password is shared by all streamers — they enter it in OBS
as a query parameter (?password=xxx) in the stream key.
"""

import hashlib
import os
import secrets
import sqlite3
import sys

import getpass

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "live_stream.db")


def main() -> int:
    print("=" * 50)
    print("  Change Push Password")
    print("=" * 50)

    password = getpass.getpass("New push password: ")
    confirm = getpass.getpass("Confirm password:   ")

    if password != confirm:
        print("Error: passwords do not match.")
        return 1

    if len(password) < 6:
        print("Error: password must be at least 6 characters.")
        return 1

    # Generate salt + SHA256 hash
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()

    # Store in SQLite
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("push_password_salt", salt),
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("push_password_hash", h),
        )
        conn.commit()
        print("✓ Push password updated successfully.")
        print("  Salt: " + salt[:8] + "…")
        print("  Hash: " + h[:12] + "…")
    except sqlite3.Error as e:
        print(f"Error writing to database: {e}")
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
