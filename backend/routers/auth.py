"""
Simple username/password auth.
Credentials stored in eval_history/auth.json (editable via Settings).
Default: admin / admin123
Tokens stored in eval_history/sessions.json (cleared on restart by default).
"""
import hashlib
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import HISTORY_FOLDER
from backend.services.file_store import load_or_default, save_json

router = APIRouter(prefix="/api/auth", tags=["auth"])

AUTH_FILE     = lambda: HISTORY_FOLDER / "auth.json"
SESSIONS_FILE = lambda: HISTORY_FOLDER / "auth_sessions.json"

DEFAULT_USER = "admin"
DEFAULT_PASS = "admin123"

# Whether auth is enabled at all (set DEEPEVAL_AUTH=false to disable)
AUTH_ENABLED = os.getenv("DEEPEVAL_AUTH", "true").lower() not in ("false", "0", "off")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _get_users() -> dict:
    data = load_or_default(AUTH_FILE(), None)
    if not data:
        data = {"users": [{
            "username": DEFAULT_USER,
            "password_hash": _hash(DEFAULT_PASS),
            "role": "admin",
        }]}
        save_json(AUTH_FILE(), data)
    return data


def _get_sessions() -> dict:
    return load_or_default(SESSIONS_FILE(), {}) or {}


def _save_session(token: str, username: str, role: str):
    sessions = _get_sessions()
    sessions[token] = {
        "username":  username,
        "role":      role,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "expiresAt": time.strftime("%Y-%m-%dT%H:%M:%S",
                                   time.gmtime(time.time() + 86400 * 30)),  # 30 days
    }
    save_json(SESSIONS_FILE(), sessions)


def _validate_token(token: str) -> Optional[dict]:
    if not token:
        return None
    sessions = _get_sessions()
    return sessions.get(token)


def get_current_user(request: Request) -> Optional[dict]:
    """FastAPI dependency — returns user dict or None (if auth disabled)."""
    if not AUTH_ENABLED:
        return {"username": "admin", "role": "admin"}
    token = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("detoken", "")
    return _validate_token(token)


def require_auth(request: Request) -> dict:
    """FastAPI dependency — raises 401 if not authenticated."""
    if not AUTH_ENABLED:
        return {"username": "admin", "role": "admin"}
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


# ── Routes ────────────────────────────────────────────────────────────────────

class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password:     str


class CreateUserIn(BaseModel):
    username: str
    password: str
    role:     str = "viewer"


@router.get("/status")
def auth_status(request: Request):
    """Check if auth is enabled and whether this request is authenticated."""
    if not AUTH_ENABLED:
        return {"enabled": False, "authenticated": True, "username": "admin", "role": "admin"}
    user = get_current_user(request)
    return {
        "enabled":       True,
        "authenticated": user is not None,
        "username":      user["username"] if user else None,
        "role":          user["role"] if user else None,
    }


@router.post("/login")
def login(body: LoginIn):
    data  = _get_users()
    users = data.get("users", [])
    match = next((u for u in users if u["username"] == body.username), None)
    if not match or match["password_hash"] != _hash(body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = str(uuid.uuid4()).replace("-", "")
    _save_session(token, match["username"], match.get("role", "viewer"))
    resp  = JSONResponse({"success": True, "token": token,
                          "username": match["username"], "role": match.get("role", "viewer")})
    resp.set_cookie("detoken", token, max_age=86400 * 30, httponly=True, samesite="lax")
    return resp


@router.post("/logout")
def logout(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "") or \
            request.cookies.get("detoken", "")
    if token:
        sessions = _get_sessions()
        sessions.pop(token, None)
        save_json(SESSIONS_FILE(), sessions)
    resp = JSONResponse({"success": True})
    resp.delete_cookie("detoken")
    return resp


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request):
    user = require_auth(request)
    data  = _get_users()
    users = data.get("users", [])
    match = next((u for u in users if u["username"] == user["username"]), None)
    if not match or match["password_hash"] != _hash(body.current_password):
        raise HTTPException(status_code=400, detail="Current password incorrect")
    match["password_hash"] = _hash(body.new_password)
    save_json(AUTH_FILE(), data)
    return {"success": True}


@router.get("/users")
def list_users(request: Request):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    data = _get_users()
    return [{"username": u["username"], "role": u.get("role", "viewer")}
            for u in data.get("users", [])]


@router.post("/users")
def create_user(body: CreateUserIn, request: Request):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    data  = _get_users()
    users = data.get("users", [])
    if any(u["username"] == body.username for u in users):
        raise HTTPException(status_code=400, detail="Username already exists")
    users.append({"username": body.username,
                  "password_hash": _hash(body.password),
                  "role": body.role})
    data["users"] = users
    save_json(AUTH_FILE(), data)
    return {"success": True}


@router.delete("/users/{username}")
def delete_user(username: str, request: Request):
    user = require_auth(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    data  = _get_users()
    data["users"] = [u for u in data.get("users", []) if u["username"] != username]
    save_json(AUTH_FILE(), data)
    return {"success": True}
