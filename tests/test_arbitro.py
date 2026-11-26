import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from app.arbitro import COOKIE, LoginRequest, is_referee, login, needs_referee


def request(method="GET", path="/", cookie=None):
    headers = [(b"cookie", f"{COOKIE}={cookie}".encode())] if cookie else []
    return Request({"type": "http", "method": method, "path": path, "headers": headers, "query_string": b""})


def login_cookie(senha):
    response = Response()
    login(LoginRequest(senha=senha), request("POST"), response)
    return response.headers["set-cookie"].split(";")[0].split("=", 1)[1]


@pytest.mark.parametrize("method,path,locked", [
    ("GET", "/api/tournaments/active", False),
    ("GET", "/api/tournaments/2/standings", False),
    ("POST", "/api/tournaments", True),
    ("POST", "/api/tournaments/2/matches/5/scoreboard/point", True),
    ("PATCH", "/api/teams/6", True),
    ("DELETE", "/api/teams/6/players/30", True),
    ("POST", "/api/sessions/1/generate", False),  # pickup nights stay open
    ("PATCH", "/api/players/1", False),
])
def test_only_tournament_writes_need_a_referee(method, path, locked):
    assert needs_referee(request(method, path)) is locked


def test_without_password_set_everyone_is_referee(monkeypatch):
    monkeypatch.delenv("ARBITRO_SENHA", raising=False)
    assert is_referee(request())


def test_with_password_set_a_viewer_is_not_referee(monkeypatch):
    monkeypatch.setenv("ARBITRO_SENHA", "segredo")
    assert not is_referee(request())
    assert not is_referee(request(cookie="forjado"))


def test_wrong_password_is_refused(monkeypatch):
    monkeypatch.setenv("ARBITRO_SENHA", "segredo")
    with pytest.raises(HTTPException) as e:
        login_cookie("errada")
    assert e.value.status_code == 401


def test_login_cookie_makes_a_referee(monkeypatch):
    monkeypatch.setenv("ARBITRO_SENHA", "segredo")
    assert is_referee(request(cookie=login_cookie("segredo")))


def test_changing_the_password_invalidates_old_cookies(monkeypatch):
    monkeypatch.setenv("ARBITRO_SENHA", "segredo")
    cookie = login_cookie("segredo")
    monkeypatch.setenv("ARBITRO_SENHA", "outra")
    assert not is_referee(request(cookie=cookie))
