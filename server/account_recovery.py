"""Explicit local owner credential recovery; never grants additional access."""
import sqlite3
from pathlib import Path
from .app import generate_password_hash, transaction


def recover_owner_access(path, workspace, expected_user_id, password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError('Password must contain 12–1024 characters')
    if not workspace or not expected_user_id:
        raise ValueError('Workspace and expected user are required')
    password_hash = generate_password_hash(password)
    # rw refuses missing databases; do not initialize schema or change journal mode.
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=rw', uri=True, isolation_level=None)
    try:
        with transaction(db):
            owner = db.execute('SELECT owner FROM workspaces WHERE id=?', (workspace,)).fetchone()
            user = db.execute('SELECT id FROM users WHERE id=?', (expected_user_id,)).fetchone()
            if not owner or owner[0] != expected_user_id or not user:
                raise ValueError('Target owner does not match')
            db.execute('UPDATE users SET password=? WHERE id=?', (password_hash, expected_user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?', (expected_user_id,))
    finally:
        db.close()
