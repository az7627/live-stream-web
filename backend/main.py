"""
Live Stream Web Backend — FastAPI application.

Endpoints
---------
- GET  /api/health
- GET  /api/streams
-
GET  /api/streams/{name}/exists
- POST /api/streams/create
- POST /api/streams/validate_push
- POST /api/streams/validate_view
- POST /api/streams/{name}/end
- WS   /ws/{stream_name}            (danmaku)
- GET  /hls/{path:path}             (HLS segments)
- GET  /*                            (static frontend files)
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from auth import hash_password, verify_password

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
DB_PATH = BASE_DIR / "data" / "live_stream.db"
MEDIA_HLS = BASE_DIR / "media" / "hls"

os.makedirs(BASE_DIR / "data", exist_ok=True)
os.makedirs(MEDIA_HLS, exist_ok=True)


def normalize_name(name: str) -> str:
    """Lowercase, allow only [a-z0-9_-], collapse runs of `-`."""
    n = re.sub(r"[^a-z0-9_-]", "-", name.strip().lower())
    n = re.sub(r"-+", "-", n).strip("-")
    return n

# ── Database helpers ───────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS streams (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT UNIQUE NOT NULL,
                view_password_hash TEXT NOT NULL,
                view_password_salt TEXT NOT NULL,
                status           TEXT DEFAULT 'waiting'
                                 CHECK(status IN ('waiting','live','ended')),
                created_at       TIMESTAMP DEFAULT (datetime('now')),
                started_at       TIMESTAMP,
                ended_at         TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_streams_name ON streams(name);
        """)


# ── Pydantic schemas ──────────────────────────────────────────────────────

class CreateStreamReq(BaseModel):
    name: str
    view_password: str


class ValidatePushReq(BaseModel):
    stream_name: str
    password: str


class ValidateViewReq(BaseModel):
    stream_name: str
    password: str


# ── Admin schemas ─────────────────────────────────────────────────────────

class AdminReq(BaseModel):
    password: str  # push password


class UpdateViewPasswordReq(BaseModel):
    password: str
    view_password: str


class ChangePushPasswordReq(BaseModel):
    old_password: str
    new_password: str


# ── Danmaku WebSocket manager ──────────────────────────────────────────────

class DanmakuManager:
    """Manages WebSocket connections grouped by stream name."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def join(self, room: str, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms[room].add(ws)

    def leave(self, room: str, ws: WebSocket) -> None:
        self._rooms[room].discard(ws)
        if not self._rooms[room]:
            del self._rooms[room]

    async def broadcast(self, room: str, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._rooms.get(room, set()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._rooms[room].discard(ws)
        if room in self._rooms and not self._rooms[room]:
            del self._rooms[room]


danmaku = DanmakuManager()


# ── App ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Live Stream",
    version="1.0.0",
    lifespan=lifespan,
)


# ── API routes ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/validate_push_password")
def validate_push_password(req: ValidatePushReq):
    """Validate the push password only (no stream check).
    Called by the web UI before creating a stream."""
    with get_conn() as conn:
        push_hash = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_hash'"
        ).fetchone()
        push_salt = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_salt'"
        ).fetchone()

    if not push_hash or not push_salt:
        raise HTTPException(
            500, "推流密码未配置 — 请先运行 change_push_password.py"
        )
    if not verify_password(req.password, push_hash["value"], push_salt["value"]):
        raise HTTPException(403, "推流密码错误")

    return {"success": True}


@app.get("/api/streams")
def list_streams():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, status, created_at, started_at FROM streams "
            "WHERE status != 'ended' ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/streams/{name}/exists")
def stream_exists(name: str):
    name = normalize_name(name)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM streams WHERE name = ?", (name,)
        ).fetchone()
    return {"exists": row is not None}


@app.post("/api/streams/create")
def create_stream(req: CreateStreamReq):
    name = normalize_name(req.name)
    if not name:
        raise HTTPException(400, "Stream name is required")
    if len(name) > 64:
        raise HTTPException(400, "Stream name too long (max 64 chars)")
    if not req.view_password:
        raise HTTPException(400, "Viewing password is required")
    if len(req.view_password) < 4:
        raise HTTPException(400, "Viewing password must be at least 4 characters")

    hashed, salt = hash_password(req.view_password)

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM streams WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            raise HTTPException(400, "Stream name already taken")
        conn.execute(
            "INSERT INTO streams (name, view_password_hash, view_password_salt) "
            "VALUES (?, ?, ?)",
            (name, hashed, salt),
        )
        conn.commit()

    return {"success": True, "stream_name": name}


@app.get("/api/streams/{name}/stream-key")
def get_stream_key(name: str):
    """Return the OBS stream key with auth sign for this stream.

    The sign is computed the same way NMS's ``verifyAuth`` does it:
      sign = MD5('/live/' + name + '-' + expires + '-' + secret)

    where ``secret`` is the SHA256 push-password hash stored in the DB.
    """
    name = normalize_name(name)
    with get_conn() as conn:
        secret_row = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_hash'"
        ).fetchone()

    if not secret_row:
        # No push password configured — return plain stream key
        return {"stream_key": name}

    secret = secret_row["value"]
    expires = "9999999999"  # far future (~2286), never expires
    digest = hashlib.md5(
        f"/live/{name}-{expires}-{secret}".encode()
    ).hexdigest()
    sign = f"{expires}-{digest}"
    stream_key = f"{name}?expires={expires}&sign={sign}"
    return {"stream_key": stream_key, "expires": expires}


@app.post("/api/streams/validate_push")
def validate_push(req: ValidatePushReq):
    """Called by Node-Media-Server when OBS tries to publish."""
    stream_name = normalize_name(req.stream_name)

    with get_conn() as conn:
        push_hash = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_hash'"
        ).fetchone()
        push_salt = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_salt'"
        ).fetchone()

    if not push_hash or not push_salt:
        raise HTTPException(
            500, "Push password not configured – run change_push_password.py"
        )
    if not verify_password(req.password, push_hash["value"], push_salt["value"]):
        raise HTTPException(403, "Invalid push password")

    with get_conn() as conn:
        stream = conn.execute(
            "SELECT id, status FROM streams WHERE name = ?",
            (stream_name,),
        ).fetchone()
        if not stream:
            raise HTTPException(404, "Stream not found — create it via the web UI first")

        new_status = "live" if stream["status"] == "waiting" else stream["status"]
        if stream["status"] == "waiting":
            conn.execute(
                "UPDATE streams SET status = 'live', started_at = ? WHERE name = ?",
                (datetime.now(timezone.utc).isoformat(), stream_name),
            )
            conn.commit()

    return {"success": True, "stream_name": stream_name}


@app.post("/api/streams/validate_view")
def validate_view(req: ValidateViewReq):
    stream_name = normalize_name(req.stream_name)
    with get_conn() as conn:
        stream = conn.execute(
            "SELECT view_password_hash, view_password_salt, status "
            "FROM streams WHERE name = ?",
            (stream_name,),
        ).fetchone()

    if not stream:
        raise HTTPException(404, "Stream not found")
    if not verify_password(
        req.password, stream["view_password_hash"], stream["view_password_salt"]
    ):
        raise HTTPException(403, "Invalid viewing password")

    return {"success": True, "status": stream["status"]}


@app.post("/api/streams/{name}/end")
def end_stream(name: str):
    name = normalize_name(name)
    with get_conn() as conn:
        conn.execute(
            "UPDATE streams SET status = 'ended', ended_at = ? WHERE name = ?",
            (datetime.now(timezone.utc).isoformat(), name),
        )
        conn.commit()
    return {"success": True}


@app.post("/api/admin/streams")
def admin_list_streams(req: AdminReq):
    """List all streams (including ended). Requires push password."""
    _verify_admin(req.password)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, status, created_at, started_at, ended_at FROM streams ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/streams/{name}/delete")
def admin_delete_stream(name: str, req: AdminReq):
    """Delete a stream and its HLS files. Requires push password."""
    _verify_admin(req.password)
    name = normalize_name(name)
    with get_conn() as conn:
        conn.execute("DELETE FROM streams WHERE name = ?", (name,))
        conn.commit()
    # Clean up HLS files
    stream_dir = MEDIA_HLS / "live" / name
    if stream_dir.exists():
        import shutil
        shutil.rmtree(stream_dir)
    return {"success": True}


@app.post("/api/admin/streams/{name}/end")
def admin_end_stream(name: str, req: AdminReq):
    """Mark a stream as ended. Requires push password."""
    _verify_admin(req.password)
    name = normalize_name(name)
    with get_conn() as conn:
        conn.execute(
            "UPDATE streams SET status = 'ended', ended_at = ? WHERE name = ?",
            (datetime.now(timezone.utc).isoformat(), name),
        )
        conn.commit()
    return {"success": True}


@app.post("/api/admin/streams/{name}/update-password")
def admin_update_view_password(name: str, req: UpdateViewPasswordReq):
    """Change the viewing password for a stream. Requires push password."""
    _verify_admin(req.password)
    name = normalize_name(name)
    if not req.view_password or len(req.view_password) < 4:
        raise HTTPException(400, "View password must be at least 4 characters")
    hashed, salt = hash_password(req.view_password)
    with get_conn() as conn:
        conn.execute(
            "UPDATE streams SET view_password_hash = ?, view_password_salt = ? WHERE name = ?",
            (hashed, salt, name),
        )
        conn.commit()
    return {"success": True}


@app.post("/api/admin/change-push-password")
def admin_change_push_password(req: ChangePushPasswordReq):
    """Change the server-wide push password. Requires current push password."""
    with get_conn() as conn:
        push_hash = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_hash'"
        ).fetchone()
        push_salt = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_salt'"
        ).fetchone()

    if not push_hash or not push_salt:
        raise HTTPException(500, "Push password not configured")

    if not verify_password(req.old_password, push_hash["value"], push_salt["value"]):
        raise HTTPException(403, "Current push password is incorrect")

    if len(req.new_password) < 6:
        raise HTTPException(400, "New password must be at least 6 characters")

    hashed, salt = hash_password(req.new_password)
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("push_password_salt", salt),
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("push_password_hash", hashed),
        )
        conn.commit()
    return {"success": True}


# ── Helper ─────────────────────────────────────────────────────────────────

def _verify_admin(password: str) -> None:
    with get_conn() as conn:
        push_hash = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_hash'"
        ).fetchone()
        push_salt = conn.execute(
            "SELECT value FROM config WHERE key = 'push_password_salt'"
        ).fetchone()
    if not push_hash or not push_salt:
        raise HTTPException(500, "Push password not configured — run change_push_password.py")
    if not verify_password(password, push_hash["value"], push_salt["value"]):
        raise HTTPException(403, "Invalid admin password")


# ── Danmaku WebSocket ─────────────────────────────────────────────────────

@app.websocket("/ws/{stream_name}")
async def ws_danmaku(websocket: WebSocket, stream_name: str):
    await danmaku.join(stream_name, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "danmaku":
                text = data.get("text", "").strip()
                if not text or len(text) > 200:
                    continue
                await danmaku.broadcast(
                    stream_name,
                    {
                        "type": "danmaku",
                        "text": text,
                        "color": data.get("color", "#FFFFFF"),
                    },
                )
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        danmaku.leave(stream_name, websocket)


# ── Static files (HLS) ────────────────────────────────────────────────────

app.mount("/hls", StaticFiles(directory=str(MEDIA_HLS)), name="hls")


# ── SPA-like frontend routes ──────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/go-live")
def go_live():
    return FileResponse(str(FRONTEND_DIR / "go-live.html"))


@app.get("/manage")
def manage():
    return FileResponse(str(FRONTEND_DIR / "manage.html"))


@app.get("/watch/{stream_name:path}")
def watch(stream_name: str):
    return FileResponse(str(FRONTEND_DIR / "watch.html"))


@app.get("/static/{rest_of_path:path}")
def static_files(rest_of_path: str):
    """Serve everything under frontend/ (css, js, assets)."""
    file_path = FRONTEND_DIR / rest_of_path
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(str(file_path))


# ── Entry-point (used by start.py) ────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    CERT = Path("C:/Users/a233d/Documents/cert")
    uvicorn.run(
        "main:app",
        host="::",
        port=443,
        ssl_keyfile=str(CERT / "az7627.top.key"),
        ssl_certfile=str(CERT / "az7627.top.pem"),
        log_level="info",
    )
