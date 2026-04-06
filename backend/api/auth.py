"""
Overlord11 — Auth API Router
==============================
Provides login, logout, and session-verification endpoints.

Endpoints:
    POST /api/auth/login    — exchange credentials for a session token
    POST /api/auth/logout   — revoke the current session token
    GET  /api/auth/verify   — check if the current token is valid
    GET  /api/auth/me       — return current user info
    GET  /api/auth/status   — return auth system status (admin only)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth.auth import auth_manager, require_auth, optional_auth, AUTH_ENABLED

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("overlord11.auth.api")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """Credentials submitted by the login form."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Returned on successful login."""
    token: str
    username: str
    role: str
    expires_in: int      # seconds until token expiry
    message: str


class VerifyResponse(BaseModel):
    """Returned by the verify and me endpoints."""
    authenticated: bool
    username: Optional[str] = None
    role: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse, summary="Authenticate and receive a session token")
async def login(body: LoginRequest):
    """
    Validate username + password against the SHA-256 user table.
    Returns a session token valid for SESSION_TTL_SECONDS (default 8 hours).

    The token should be included in subsequent requests as:
        Authorization: Bearer <token>
    """
    log.info("Login attempt for user '%s'", body.username)

    if not auth_manager.verify_password(body.username, body.password):
        # Use a generic error to avoid leaking whether the user exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = auth_manager.create_session(body.username)
    from ..auth.auth import SESSION_TTL_SECONDS
    return LoginResponse(
        token=token,
        username=body.username,
        role=auth_manager.get_user_role(body.username) or "user",
        expires_in=SESSION_TTL_SECONDS,
        message="Authentication successful",
    )


@router.post("/logout", summary="Revoke the current session token")
async def logout(session: dict = Depends(require_auth)):
    """
    Revoke the caller's session token.
    The token is extracted from the Authorization header.

    After logout the token is immediately invalid.
    """
    # Reconstruct the token from the session if needed — require_auth returns the session dict.
    # We use optional_auth in a separate call to get the raw token.
    # Simpler: require_auth already validated it so we look it up by username (best effort).
    # Actually, we need the raw token — let's add it to the session dict.
    # NOTE: The session dict returned by require_auth does not currently include the token.
    # This is fine for logout because we can revoke by scanning _sessions.
    from ..auth.auth import _sessions
    username = session.get("username")
    # Find and revoke all tokens for this user (handles multiple sessions)
    to_revoke = [t for t, s in list(_sessions.items()) if s.get("username") == username]
    for t in to_revoke:
        auth_manager.revoke_token(t)
    return {"message": f"Logged out {username}. {len(to_revoke)} session(s) revoked."}


@router.get("/verify", response_model=VerifyResponse, summary="Check if the current token is valid")
async def verify(session: Optional[dict] = Depends(optional_auth)):
    """
    Returns authentication status without requiring auth.
    Useful for the frontend to check on load whether the user is already logged in.
    """
    if session:
        return VerifyResponse(
            authenticated=True,
            username=session["username"],
            role=session["role"],
            message="Token valid",
        )
    return VerifyResponse(
        authenticated=False,
        message="Not authenticated" if AUTH_ENABLED else "Auth disabled (dev mode)",
    )


@router.get("/me", response_model=VerifyResponse, summary="Return current user info")
async def me(session: dict = Depends(require_auth)):
    """Returns the authenticated user's username and role."""
    return VerifyResponse(
        authenticated=True,
        username=session["username"],
        role=session["role"],
        message="OK",
    )


@router.get("/status", summary="Auth system status (admin only)")
async def auth_status(session: dict = Depends(require_auth)):
    """Returns user list and active session count. Requires admin role."""
    if session.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return {
        "auth_enabled": AUTH_ENABLED,
        "active_sessions": auth_manager.active_session_count(),
        "users": auth_manager.list_users(),
    }
