"""SQLite xotira: foydalanuvchilar, suhbatlar (mavzular), xabarlar va kunlik limitlar.

Hamma metodlar oddiy (sinxron). Ularni botdan `await run(db.metod, ...)` deb chaqiramiz,
shunda bot bloklanmaydi.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

UZ_TZ = timezone(timedelta(hours=5))  # O'zbekiston vaqti
DEFAULT_TITLE = "Yangi suhbat"


async def run(fn, *args, **kwargs):
    """Sinxron DB metodini alohida oqimda ishga tushiradi."""
    return await asyncio.to_thread(fn, *args, **kwargs)


def today() -> str:
    return datetime.now(UZ_TZ).strftime("%Y-%m-%d")


class Database:
    def __init__(self, path: str):
        if path.startswith(("postgres://", "postgresql://")):
            from postgres_adapter import Connection
            self._conn = Connection(path)
            self._lock = threading.Lock()
            self._create()
            return
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        self._create()

    # ---------- ichki yordamchilar ----------
    def _exec(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    def _one(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def _insert(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return int(cur.lastrowid)

    def _create(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users(
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    voice_reply INTEGER NOT NULL DEFAULT 0,
                    current_topic INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS topics(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_topics_user ON topics(user_id, id);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_topic ON messages(topic_id, id);
                CREATE TABLE IF NOT EXISTS usage(
                    user_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    requests INTEGER NOT NULL DEFAULT 0,
                    images INTEGER NOT NULL DEFAULT 0,
                    voice_seconds INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, day)
                );
                """
            )
            self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # ---------- foydalanuvchi ----------
    def ensure_user(self, user_id: int, name: str) -> dict:
        row = self._one("SELECT * FROM users WHERE user_id=?", (user_id,))
        if row is None:
            self._exec(
                "INSERT INTO users(user_id, name, created_at) VALUES(?,?,?) ON CONFLICT(user_id) DO NOTHING",
                (user_id, name, self._now()),
            )
            row = self._one("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict(row)

    def get_user(self, user_id: int) -> dict:
        row = self._one("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict(row) if row else self.ensure_user(user_id, "")

    def set_voice_reply(self, user_id: int, on: bool) -> None:
        self._exec("UPDATE users SET voice_reply=? WHERE user_id=?", (1 if on else 0, user_id))

    # ---------- suhbatlar (mavzular) ----------
    def new_topic(self, user_id: int, title: str = DEFAULT_TITLE) -> int:
        self.ensure_user(user_id, "")
        tid = self._insert(
            "INSERT INTO topics(user_id, title, created_at) VALUES(?,?,?)",
            (user_id, title, self._now()),
        )
        self._exec("UPDATE users SET current_topic=? WHERE user_id=?", (tid, user_id))
        return tid

    def current_topic(self, user_id: int) -> int:
        """Joriy suhbat id si. Yo'q bo'lsa, oxirgisini oladi yoki yangisini ochadi."""
        user = self.get_user(user_id)
        tid = user.get("current_topic")
        if tid:
            ok = self._one("SELECT id FROM topics WHERE id=? AND user_id=?", (tid, user_id))
            if ok:
                return int(tid)
        last = self._one("SELECT id FROM topics WHERE user_id=? ORDER BY id DESC LIMIT 1", (user_id,))
        if last:
            self._exec("UPDATE users SET current_topic=? WHERE user_id=?", (last["id"], user_id))
            return int(last["id"])
        return self.new_topic(user_id)

    def list_topics(self, user_id: int, limit: int = 8) -> list:
        rows = self._all(
            "SELECT id, title FROM topics WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    def switch_topic(self, user_id: int, topic_id: int) -> bool:
        ok = self._one("SELECT id FROM topics WHERE id=? AND user_id=?", (topic_id, user_id))
        if not ok:
            return False
        self._exec("UPDATE users SET current_topic=? WHERE user_id=?", (topic_id, user_id))
        return True

    def delete_topic(self, user_id: int, topic_id: int) -> bool:
        ok = self._one("SELECT id FROM topics WHERE id=? AND user_id=?", (topic_id, user_id))
        if not ok:
            return False
        self._exec("DELETE FROM messages WHERE topic_id=?", (topic_id,))
        self._exec("DELETE FROM topics WHERE id=?", (topic_id,))
        self._exec(
            "UPDATE users SET current_topic=NULL WHERE user_id=? AND current_topic=?",
            (user_id, topic_id),
        )
        return True

    def set_title_if_default(self, topic_id: int, text: str) -> None:
        """Suhbat nomi hali standart bo'lsa, birinchi xabardan nom qo'yadi."""
        title = " ".join(text.split())[:40].strip()
        if not title:
            return
        self._exec(
            "UPDATE topics SET title=? WHERE id=? AND title=?",
            (title, topic_id, DEFAULT_TITLE),
        )

    def topic_title(self, topic_id: int) -> str:
        row = self._one("SELECT title FROM topics WHERE id=?", (topic_id,))
        return row["title"] if row else DEFAULT_TITLE

    # ---------- xabarlar ----------
    def add_message(self, topic_id: int, role: str, content: str) -> None:
        self._exec(
            "INSERT INTO messages(topic_id, role, content, created_at) VALUES(?,?,?,?)",
            (topic_id, role, content, self._now()),
        )

    def get_history(self, topic_id: int, limit: int, max_chars: int) -> list:
        """Oxirgi `limit` ta xabar, jami `max_chars` belgidan oshmaydigan qilib (eskisi -> yangisi)."""
        rows = self._all(
            "SELECT role, content FROM messages WHERE topic_id=? ORDER BY id DESC LIMIT ?",
            (topic_id, limit),
        )
        picked, total = [], 0
        for r in rows:  # yangisidan boshlab
            size = len(r["content"])
            if picked and total + size > max_chars:
                break
            picked.append({"role": r["role"], "content": r["content"]})
            total += size
        picked.reverse()
        return picked

    # ---------- limitlar ----------
    def get_usage(self, user_id: int) -> dict:
        row = self._one(
            "SELECT requests, images, voice_seconds FROM usage WHERE user_id=? AND day=?",
            (user_id, today()),
        )
        return dict(row) if row else {"requests": 0, "images": 0, "voice_seconds": 0}

    def add_usage(self, user_id: int, requests: int = 0, images: int = 0, voice_seconds: int = 0) -> None:
        self._exec(
            """
            INSERT INTO usage(user_id, day, requests, images, voice_seconds) VALUES(?,?,?,?,?)
            ON CONFLICT(user_id, day) DO UPDATE SET
                requests = requests + excluded.requests,
                images = images + excluded.images,
                voice_seconds = voice_seconds + excluded.voice_seconds
            """,
            (user_id, today(), requests, images, voice_seconds),
        )

    # ---------- admin statistikasi ----------
    def stats(self) -> dict:
        users = self._one("SELECT COUNT(*) AS n FROM users")["n"]
        row = self._one(
            "SELECT COALESCE(SUM(requests),0) AS r, COALESCE(SUM(images),0) AS i, "
            "COALESCE(SUM(voice_seconds),0) AS v, COUNT(*) AS active FROM usage WHERE day=?",
            (today(),),
        )
        return {
            "users": users,
            "active_today": row["active"],
            "requests": row["r"],
            "images": row["i"],
            "voice_seconds": row["v"],
        }

    def close(self):
        with self._lock:
            self._conn.close()
