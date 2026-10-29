"""Tests simulés du mode live ; aucune connexion fournisseur pendant pytest."""

from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import quote

import chess
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.explorer import ENDPOINT, ExplorerError, OpeningExplorer
from app.explorer_fixtures import SYNTHETIC_MASTERS_INITIAL
from app.explorer_live import SecretConfigurationError, live_client, read_token
from app.main import create_app

INITIAL = chess.STARTING_FEN
FAKE_TOKEN = "simulated-test-credential"


@pytest.fixture
def token_file(tmp_path):
    path = tmp_path / "token"
    path.write_text(FAKE_TOKEN + "\n", encoding="ascii")
    return str(path)


def test_live_bearer_legal_moves_and_metadata_compatibility(token_file):
    requests = []
    # Forme réaliste ; les chiffres ci-dessous restent ceux de la fixture
    # SYNTHÉTIQUE I02. Aucune capture chiffrée P71 n'existe dans le handoff.
    payload = deepcopy(SYNTHETIC_MASTERS_INITIAL)
    payload.update(opening=None, topGames=[])
    payload["moves"][0].update(averageRating=2400, opening={"eco": "B00", "name": "Test"})

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer " + FAKE_TOKEN
        return httpx.Response(200, json=payload)

    with live_client(token_file, transport=httpx.MockTransport(handler)) as client:
        assert "authorization" not in client.headers
        assert FAKE_TOKEN not in repr(client.auth)
        result = OpeningExplorer(client, "live").moves(INITIAL)
    assert result.source_mode == "live" and result.position_statistics.games == 20
    assert result.moves[0].statistics.games == 10 and result.moves[0].san == "e4"
    assert len(requests) == 1
    assert dict(requests[0].url.params) == {"fen": INITIAL, "moves": "12", "topGames": "0"}


@pytest.mark.parametrize("url", [
    "https://example.org/masters", "http://explorer.lichess.org/masters",
    "https://explorer.lichess.org:444/masters", "https://explorer.lichess.org/other",
    "https://user@explorer.lichess.org/masters",
])
def test_bearer_never_sent_to_other_target(token_file, url):
    requests = []
    with live_client(token_file, transport=httpx.MockTransport(requests.append)) as client:
        with pytest.raises(SecretConfigurationError, match="LICHESS_AUTH_TARGET_REJECTED"):
            client.get(url)
    assert requests == []


def test_redirect_not_followed_even_to_official_host(token_file):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": ENDPOINT})

    with live_client(token_file, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExplorerError, match="UPSTREAM_INVALID_RESPONSE"):
            OpeningExplorer(client, "live").moves(INITIAL)
    assert len(requests) == 1


@pytest.mark.parametrize("status,code,api_status", [
    (401, "UPSTREAM_AUTHORIZATION_FAILED", 502),
    (403, "UPSTREAM_AUTHORIZATION_FAILED", 502),
    (429, "UPSTREAM_RATE_LIMITED", 503),
])
def test_live_http_errors_typed_no_retry_or_secret_in_response(token_file, status, code, api_status,
                                                            monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, text=FAKE_TOKEN, headers={"Retry-After": "30"})

    monkeypatch.setenv("EXPLORER_MODE", "live")
    monkeypatch.setenv("LICHESS_API_TOKEN_FILE", token_file)
    with live_client(token_file, transport=httpx.MockTransport(handler)) as transport_client:
        monkeypatch.setattr("app.main.live_client", lambda _: transport_client)
        with TestClient(create_app()) as client:
            response = client.get("/api/v1/moves/" + quote(INITIAL, safe=""))
    assert response.status_code == api_status and response.json()["detail"]["code"] == code
    assert len(requests) == 1 and FAKE_TOKEN not in response.text


def test_live_timeout_is_safe_and_never_retried(token_file):
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout(FAKE_TOKEN)

    with live_client(token_file, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ExplorerError, match="UPSTREAM_TIMEOUT") as error:
            OpeningExplorer(client, "live").moves(INITIAL)
    assert len(requests) == 1 and FAKE_TOKEN not in str(error.value)


@pytest.mark.parametrize("content", [b"", b" \n", b"bad\r\nheader", b"x" * 4097, b"\xff"])
def test_invalid_secret_never_echoed(tmp_path, content):
    path = tmp_path / "token"
    path.write_bytes(content)
    with pytest.raises(SecretConfigurationError, match="^LICHESS_SECRET_INVALID$"):
        read_token(str(path))


@pytest.mark.parametrize("kind", ["missing", "directory", "denied"])
def test_unreadable_secret_safe_diagnostic(tmp_path, monkeypatch, kind):
    path = tmp_path / "missing" if kind == "missing" else tmp_path
    if kind == "denied":
        monkeypatch.setattr("pathlib.Path.open", lambda *a, **kw: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(SecretConfigurationError, match="^LICHESS_SECRET_UNREADABLE$"):
        read_token(str(path))


@pytest.mark.parametrize("mode", ["disabled", "synthetic_fixture"])
def test_non_live_ignores_missing_secret_and_inherited_env_token(monkeypatch, tmp_path, mode):
    monkeypatch.setenv("EXPLORER_MODE", mode)
    monkeypatch.setenv("LICHESS_API_TOKEN_FILE", str(tmp_path / "missing"))
    monkeypatch.setenv("LICHESS_API_TOKEN", FAKE_TOKEN)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/healthcheck").status_code == 200


def test_live_startup_healthcheck_invalid_and_terminal_fen_zero_calls(token_file, monkeypatch):
    requests = []
    monkeypatch.setenv("EXPLORER_MODE", "live")
    monkeypatch.setenv("LICHESS_API_TOKEN_FILE", token_file)
    with live_client(token_file, transport=httpx.MockTransport(requests.append)) as transport_client:
        monkeypatch.setattr("app.main.live_client", lambda _: transport_client)
        app = create_app()
        with TestClient(app) as client:
            assert client.get("/api/v1/healthcheck").json() == {"status": "ok"}
            assert client.get("/api/v1/moves/bad").status_code == 422
            response = client.get("/api/v1/moves/" + quote("7k/6Q1/6K1/8/8/8/8/8 b - - 0 1", safe=""))
            assert response.json()["source_mode"] == "live" and response.json()["status"] == "terminal"
        assert transport_client.is_closed
    assert requests == []


def test_unknown_mode_still_rejected(monkeypatch):
    monkeypatch.setenv("EXPLORER_MODE", "unknown")
    with pytest.raises(ValueError, match="EXPLORER_MODE"):
        create_app()


def test_runtime_secret_reference_is_not_rejected_by_token_format(tmp_path):
    # Référence INVENTÉE, pas une valeur de l'environnement courant.
    path = tmp_path / "reference"
    path.write_text("runtime:secret-reference:test-only", encoding="ascii")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"moves": []})

    with live_client(str(path), transport=httpx.MockTransport(handler)) as client:
        result = OpeningExplorer(client, "live").moves(INITIAL)
    assert result.status == "empty" and len(requests) == 1


def test_replay_synthetic_metadata_remains_offline(token_file):
    # Public synthetic unit fixture, not a captured supplier response.
    from copy import deepcopy
    capture=deepcopy(SYNTHETIC_MASTERS_INITIAL)
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json=capture)
    with live_client(token_file,transport=httpx.MockTransport(handler)) as client:
        result=OpeningExplorer(client,'live').moves(INITIAL)
    assert result.position_statistics.games==20 and len(result.moves)==2
    assert len(calls)==1 and [m.uci for m in result.moves]==['e2e4','d2d4']
