"""Referee login for the tournament: one shared password unlocks changes.

Without the cookie, everything under the tournament API is read-only, so the
public link can be passed around for people to follow games and standings.
The pickup-night routes are not covered (they stay as open as before).

The password comes from ARBITRO_SENHA. When it's unset (local dev, tests),
nothing is locked, which keeps the old behaviour.
"""
import hashlib
import hmac
import os

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

COOKIE = "arbitro"
COOKIE_MAX_AGE = 4 * 24 * 3600  # the whole tournament weekend
PROTECTED_PREFIXES = ("/api/tournaments", "/api/teams")
READ_METHODS = {"GET", "HEAD", "OPTIONS"}

router = APIRouter()


def _password() -> str:
    return os.environ.get("ARBITRO_SENHA", "")


def _token(password: str) -> str:
    # Derived from the password, so changing it logs everyone out.
    return hmac.new(password.encode(), b"arbitro", hashlib.sha256).hexdigest()


def is_referee(request: Request) -> bool:
    password = _password()
    if not password:
        return True
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(password))


def needs_referee(request: Request) -> bool:
    return request.method not in READ_METHODS and request.url.path.startswith(PROTECTED_PREFIXES)


async def referee_guard(request: Request, call_next):
    if needs_referee(request) and not is_referee(request):
        return JSONResponse({"detail": "Só árbitros podem alterar. Toque em “Entrar como árbitro”."}, status_code=401)
    return await call_next(request)


class LoginRequest(BaseModel):
    senha: str


@router.get("/api/arbitro")
def status(request: Request):
    return {"arbitro": is_referee(request), "login_ativo": bool(_password())}


@router.post("/api/arbitro/login")
def login(req: LoginRequest, request: Request, response: Response):
    password = _password()
    if not password:
        return {"arbitro": True}
    if not hmac.compare_digest(req.senha.encode(), password.encode()):
        raise HTTPException(401, "Senha incorreta")
    response.set_cookie(
        COOKIE, _token(password), max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
        secure=request.headers.get("x-forwarded-proto") == "https",
    )
    return {"arbitro": True}


@router.post("/api/arbitro/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"arbitro": False}
