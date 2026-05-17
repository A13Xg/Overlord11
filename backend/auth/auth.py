"""
Overlord11 — Authentication Manager
=====================================
Handles user verification, session token issuance, and token validation.

Password storage uses SHA-256 with a per-user salt:
    stored_hash = sha256(salt + plaintext_password).hexdigest()

Session tokens are random 32-byte hex strings stored in an in-memory dict
with a configurable TTL (default: 8 hours). Tokens are validated on each
protected API request via the FastAPI dependency `require_auth`.

To add or change a user:
    1. Edit backend/auth/users.json directly.
    2. Compute the new hash: sha256(salt + new_password).hexdigest()
    3. Restart the server (or call auth_manager.reload_users()).

Auth can be disabled globally by setting AUTH_ENABLED = False below — useful
for local development where no login gate is needed.
"""

import hashlib
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Set OVERLORD11_AUTH_DISABLED=1 in environment to bypass auth entirely.
# Useful for local dev / CI runs where the login flow would be a blocker.
AUTH_ENABLED: bool = os.environ.get("OVERLORD11_AUTH_DISABLED", "0") != "1"

# Session token TTL in seconds (default 8 hours)
SESSION_TTL_SECONDS: int = int(os.environ.get("OVERLORD11_SESSION_TTL", "28800"))

# Where user definitions are stored
_USERS_FILE: Path = Path(__file__).resolve().parent / "users.json"

log = logging.getLogger("overlord11.auth")


# ---------------------------------------------------------------------------
# Session store — in-memory token → {username, role, expires_at}
# ---------------------------------------------------------------------------

_sessions: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """
    Manages user verification and session lifecycle.

    All methods are synchronous and thread-safe for the FastAPI single-event-loop
    model (no concurrent writes to _sessions from async workers).
    """

    def __init__(self) -> None:
        # In-memory user table loaded from users.json
        self._users: dict[str, dict] = {}
        self.reload_users()

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    def reload_users(self) -> None:
        """Reload the users.json file from disk."""
        if not _USERS_FILE.exists():
            log.warning("users.json not found at %s — no users loaded", _USERS_FILE)
            self._users = {}
            return
        try:
            data = json.loads(_USERS_FILE.read_text(encoding="utf-8"))
            self._users = data.get("users", {})
            log.info("Loaded %d user(s) from %s", len(self._users), _USERS_FILE)
        except Exception as exc:
            log.error("Failed to load users.json: %s", exc)
            self._users = {}

    def verify_password(self, username: str, plaintext: str) -> bool:
        """
        Return True if the plaintext password matches the stored SHA-256 hash.

        Hash computation: sha256(salt + plaintext_password)
        This is a simple but effective approach for an internal tool.
        For production use, prefer bcrypt/argon2 with a proper cost factor.
        """
        user = self._users.get(username)
        if not user:
            return False
        salt = user.get("salt", "")
        expected_hash = user.get("hash", "")
        computed = hashlib.sha256((salt + plaintext).encode("utf-8")).hexdigest()
        # Use constant-time comparison to prevent timing attacks
        return secrets.compare_digest(computed, expected_hash)

    def get_user_role(self, username: str) -> Optional[str]:
        """Return the user's role string or None if user not found."""
        user = self._users.get(username)
        return user.get("role") if user else None

    def list_users(self) -> list[dict]:
        """Return a safe list of user info (no hashes or salts)."""
        return [
            {
                "username": uname,
                "role": info.get("role", "user"),
                "display_name": info.get("display_name", uname),
            }
            for uname, info in self._users.items()
        ]

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def create_session(self, username: str) -> str:
        """
        Create a new session token for the given username.

        Returns a cryptographically random 64-character hex token.
        The token is stored in _sessions with an expiry timestamp.
        """
        token = secrets.token_hex(32)   # 256 bits of randomness
        _sessions[token] = {
            "username": username,
            "role": self.get_user_role(username) or "user",
            "created_at": time.time(),
            "expires_at": time.time() + SESSION_TTL_SECONDS,
        }
        log.info("Session created for user '%s' (expires in %ds)", username, SESSION_TTL_SECONDS)
        return token

    def validate_token(self, token: str) -> Optional[dict]:
        """
        Validate a session token.

        Returns the session dict {username, role, created_at, expires_at}
        if the token is valid and not expired, otherwise None.

        Expired sessions are removed lazily on validation.
        """
        session = _sessions.get(token)
        if not session:
            return None
        if time.time() > session["expires_at"]:
            # Token has expired — clean it up
            del _sessions[token]
            log.debug("Expired session removed for token ...%s", token[-8:])
            return None
        return session

    def revoke_token(self, token: str) -> bool:
        """Revoke (delete) a session token. Returns True if it existed."""
        existed = token in _sessions
        _sessions.pop(token, None)
        if existed:
            log.info("Session revoked for token ...%s", token[-8:])
        return existed

    def purge_expired(self) -> int:
        """Remove all expired sessions. Returns count of purged sessions."""
        now = time.time()
        expired = [t for t, s in _sessions.items() if now > s["expires_at"]]
        for t in expired:
            del _sessions[t]
        return len(expired)

    def active_session_count(self) -> int:
        """Return the number of currently active (non-expired) sessions."""
        self.purge_expired()
        return len(_sessions)


# Module-level singleton
auth_manager = AuthManager()


# ---------------------------------------------------------------------------
# FastAPI dependency — use in any protected route
# ---------------------------------------------------------------------------

# Token is expected in the Authorization header as:  Bearer <token>
_auth_header = APIKeyHeader(name="Authorization", auto_error=False)


async def require_auth(authorization: Optional[str] = Security(_auth_header)) -> dict:
    """
    FastAPI dependency that validates the Bearer token from the Authorization header.

    Usage:
        @router.get("/protected")
        async def protected_route(session: dict = Depends(require_auth)):
            return {"user": session["username"]}

    When AUTH_ENABLED is False (dev mode), returns a synthetic admin session
    so all routes work without a token.
    """
    if not AUTH_ENABLED:
        # Dev bypass — return synthetic admin session
        return {"username": "dev", "role": "admin", "created_at": 0, "expires_at": float("inf")}

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Strip "Bearer " prefix if present
    token = authorization.removeprefix("Bearer ").strip()
    session = auth_manager.validate_token(token)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return session


async def optional_auth(authorization: Optional[str] = Security(_auth_header)) -> Optional[dict]:
    """
    Like require_auth but returns None instead of raising 401.
    Useful for endpoints that show different content to authenticated users.
    """
    if not AUTH_ENABLED:
        return {"username": "dev", "role": "admin", "created_at": 0, "expires_at": float("inf")}
    if not authorization:
        return None
    token = authorization.removeprefix("Bearer ").strip()
    return auth_manager.validate_token(token)
