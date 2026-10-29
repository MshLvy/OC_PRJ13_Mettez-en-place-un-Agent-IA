"""Configuration env/fichier et lancement dotenv simulés, sans aucun fournisseur."""

import importlib
from pathlib import Path
import os

import chess
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app import cli
from app.config import Settings
from app.explorer import OpeningExplorer
from app.explorer_live import configured_live_client, SecretConfigurationError
from app.main import create_app

ENV_TOKEN = "simulated-env-credential"
FILE_TOKEN = "simulated-file-credential"


@pytest.fixture(autouse=True)
def restore_dotenv_mutations():
    # Le parseur modifie os.environ directement ; restaurer aussi ses ajouts,
    # que monkeypatch n'a pas nécessairement enregistrés avant le chargement.
    keys = ("APP_NAME", "EXPLORER_MODE", "BACKEND_PORT", "LICHESS_API_TOKEN", "LICHESS_API_TOKEN_FILE")
    original = {key: os.environ.get(key) for key in keys}
    yield
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture
def file_secret(tmp_path):
    path = tmp_path / "token"
    path.write_text(FILE_TOKEN, encoding="ascii")
    return str(path)


@pytest.mark.parametrize("env_token,expected", [(ENV_TOKEN, ENV_TOKEN), (None, FILE_TOKEN),
                                               ("", FILE_TOKEN), ("   ", FILE_TOKEN)])
def test_env_nonblank_wins_otherwise_file(monkeypatch, file_secret, env_token, expected):
    if env_token is not None:
        monkeypatch.setenv("LICHESS_API_TOKEN", env_token)
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer " + expected
        return httpx.Response(200, json={"moves": []})

    with configured_live_client(file_secret, transport=httpx.MockTransport(handler)) as client:
        assert "authorization" not in client.headers
        assert expected not in repr(client.auth)
        assert OpeningExplorer(client, "live").moves(chess.STARTING_FEN).status == "empty"
    assert len(requests) == 1


def test_env_priority_never_opens_file(monkeypatch):
    monkeypatch.setenv("LICHESS_API_TOKEN", ENV_TOKEN)
    monkeypatch.setattr(Path, "open", lambda *a, **kw: pytest.fail("file must not be read"))
    with configured_live_client("not-readable", transport=httpx.MockTransport(lambda r: None)):
        pass


@pytest.mark.parametrize("token", ["x" * 4097, "invalid\nheader", "invalid\rheader",
                                  "invalid\tvalue", "invalid\x7fvalue", "non-ascii-é"])
def test_invalid_env_fails_without_file_fallback_or_leak(monkeypatch, file_secret, token,
                                                       caplog, capsys):
    monkeypatch.setenv("LICHESS_API_TOKEN", token)
    monkeypatch.setattr(Path, "open", lambda *a, **kw: pytest.fail("invalid env must not fall back"))
    with pytest.raises(SecretConfigurationError, match="^LICHESS_SECRET_INVALID$") as error:
        configured_live_client(file_secret)
    assert token not in str(error.value) and token not in caplog.text
    assert token not in capsys.readouterr().out


def test_live_env_startup_healthcheck_no_network_and_closed(monkeypatch):
    monkeypatch.setenv("EXPLORER_MODE", "live")
    monkeypatch.setenv("LICHESS_API_TOKEN", ENV_TOKEN)
    requests = []
    monkeypatch.setattr("app.main.live_client", lambda path: configured_live_client(
        path, transport=httpx.MockTransport(requests.append)))
    app = create_app()
    assert ENV_TOKEN not in repr(Settings.from_env())
    with TestClient(app) as client:
        assert client.get("/api/v1/healthcheck").json() == {"status": "ok"}
        assert client.get("/api/v1/moves/bad").status_code == 422
    assert requests == [] and app.state.explorer.client.is_closed


@pytest.mark.parametrize("mode", ["disabled", "synthetic_fixture"])
def test_non_live_does_not_validate_invalid_env_secret(monkeypatch, mode):
    monkeypatch.setenv("EXPLORER_MODE", mode)
    monkeypatch.setenv("LICHESS_API_TOKEN", "invalid\ncredential")
    monkeypatch.setenv("LICHESS_API_TOKEN_FILE", "/absent-file")
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/healthcheck").status_code == 200


def test_env_auth_still_rejects_other_host_before_transport(monkeypatch):
    monkeypatch.setenv("LICHESS_API_TOKEN", ENV_TOKEN)
    requests = []
    with configured_live_client("unused", transport=httpx.MockTransport(requests.append)) as client:
        with pytest.raises(SecretConfigurationError, match="LICHESS_AUTH_TARGET_REJECTED"):
            client.get("https://example.org/masters")
    assert requests == []


def test_dotenv_quotes_comments_spaces_and_no_interpolation(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    path = tmp_path / ".env"
    path.write_text("APP_NAME='Mon POC échecs' # commentaire\nEXPLORER_MODE=synthetic_fixture\n"
                    "LICHESS_API_TOKEN='reference:${DO_NOT_EXPAND}'\n", encoding="utf-8")
    cli.load_env_file(str(path))
    assert os.environ["APP_NAME"] == "Mon POC échecs"
    assert os.environ["LICHESS_API_TOKEN"] == "reference:${DO_NOT_EXPAND}"
    # EXPLORER_MODE est déjà injecté par la fixture et doit conserver sa valeur.
    assert os.environ["EXPLORER_MODE"] == "disabled"


def test_dotenv_preserves_injected_process_values(tmp_path, monkeypatch):
    monkeypatch.setenv("LICHESS_API_TOKEN", ENV_TOKEN)
    monkeypatch.setenv("APP_NAME", "Déjà injecté")
    monkeypatch.setenv("BACKEND_PORT", "18015")
    path = tmp_path / ".env"
    path.write_text("LICHESS_API_TOKEN=other-fake-token\nAPP_NAME=Other\nBACKEND_PORT=8001\n")
    cli.load_env_file(str(path))
    assert os.environ["LICHESS_API_TOKEN"] == ENV_TOKEN
    assert os.environ["APP_NAME"] == "Déjà injecté"
    assert os.environ["BACKEND_PORT"] == "18015"


def test_imports_and_cli_without_flag_do_not_load_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("EXPLORER_MODE=live\nLICHESS_API_TOKEN=ignored-fake-token\n")
    importlib.reload(cli)
    assert os.getenv("LICHESS_API_TOKEN") is None
    called = []
    monkeypatch.delenv("BACKEND_PORT", raising=False)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **kw: called.append((a, kw)))
    cli.main([])
    assert os.getenv("LICHESS_API_TOKEN") is None
    assert called == [(("app.main:app",), {"host": "127.0.0.1", "port": 8000})]


def test_cli_loads_before_app_and_port_arg_wins(tmp_path, monkeypatch):
    for key in ("EXPLORER_MODE", "APP_NAME", "BACKEND_PORT"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("APP_NAME='POC local'\nEXPLORER_MODE=synthetic_fixture\nBACKEND_PORT=18015\n")
    called = []

    def launch(*args, **kwargs):
        called.append((args, kwargs))
        with TestClient(create_app()) as client:
            assert client.get("/openapi.json").json()["info"]["title"] == "POC local"
            assert client.get("/api/v1/healthcheck").status_code == 200

    monkeypatch.setattr(cli.uvicorn, "run", launch)
    cli.main(["--env-file", str(path), "--port", "18016"])
    assert called[0][1] == {"host": "127.0.0.1", "port": 18016}


@pytest.mark.parametrize("port", ["not-a-port", "0", "65536"])
def test_cli_bad_port_has_safe_diagnostic(monkeypatch, port, capsys):
    monkeypatch.setenv("BACKEND_PORT", port)
    with pytest.raises(SystemExit) as error:
        cli.main([])
    assert error.value.code == 2
    assert capsys.readouterr().err == "BACKEND_PORT must be an integer between 1 and 65535\n"


@pytest.mark.parametrize("case,code", [("missing", "ENV_FILE_UNREADABLE"),
                                      ("directory", "ENV_FILE_UNREADABLE"),
                                      ("encoding", "ENV_FILE_INVALID_ENCODING"),
                                      ("oversized", "ENV_FILE_TOO_LARGE")])
def test_env_file_failures_are_safe(tmp_path, case, code, capsys):
    path = tmp_path / ".env"
    if case == "directory":
        path = tmp_path
    elif case == "encoding":
        path.write_bytes(b"\xff")
    elif case == "oversized":
        path.write_bytes(b"x" * 65537)
    with pytest.raises(cli.EnvFileError, match="^" + code + "$"):
        cli.load_env_file(str(path))
    with pytest.raises(SystemExit) as error:
        cli.main(["--env-file", str(path)])
    assert error.value.code == 2 and capsys.readouterr().err == code + "\n"
