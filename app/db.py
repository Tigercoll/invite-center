from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def session(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS apps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    callback_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    token_version INTEGER NOT NULL DEFAULT 1,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
                    role TEXT NOT NULL DEFAULT 'member',
                    default_target TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, app_id)
                );

                CREATE TABLE IF NOT EXISTS invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    invite_token TEXT NOT NULL UNIQUE,
                    role TEXT NOT NULL DEFAULT 'member',
                    target TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    note TEXT NOT NULL DEFAULT '',
                    expires_at TEXT NOT NULL,
                    used_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(app_id, email, used_at)
                );

                CREATE TABLE IF NOT EXISTS password_resets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    reset_token TEXT NOT NULL UNIQUE,
                    expires_at TEXT NOT NULL,
                    used_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS registration_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_id INTEGER NOT NULL REFERENCES apps(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    review_note TEXT NOT NULL DEFAULT '',
                    review_role TEXT NOT NULL DEFAULT '',
                    review_target TEXT NOT NULL DEFAULT '',
                    review_metadata_json TEXT NOT NULL DEFAULT '{}',
                    approved_invite_token TEXT NOT NULL DEFAULT '',
                    submitted_at TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL DEFAULT '',
                    reviewed_by TEXT NOT NULL DEFAULT '',
                    last_notified_at TEXT NOT NULL DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_registration_applications_app_id
                ON registration_applications(app_id);

                CREATE INDEX IF NOT EXISTS idx_registration_applications_email
                ON registration_applications(email);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_registration_applications_pending_unique
                ON registration_applications(app_id, email)
                WHERE status = 'pending';
                """
            )
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
            if "token_version" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 1")
