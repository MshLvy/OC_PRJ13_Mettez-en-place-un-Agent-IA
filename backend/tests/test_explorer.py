"""Opening Explorer entièrement simulé ; aucun résultat live dans ces fixtures."""

from copy import deepcopy
from urllib.parse import quote

import chess
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app.explorer import ENDPOINT, ExplorerError, OpeningExplorer
from app.explorer_fixtures import SYNTHETIC_MASTERS_INITIAL
from app.main import create_app
from app.positions import FenValidationError

INITIAL = chess.STARTING_FEN


@pytest.fixture
def mock_explorer():
    requests = []
    state = {"status": 200, "payload": deepcopy(SYNTHETIC_MASTERS_INITIAL), "headers": {}}

    def handler(request):
        requests.append(request)
        if "exception" in state:
            raise state["exception"]
        if "content" in state:
            return httpx.Response(state["status"], content=state["content"], headers=state["headers"])
        return httpx.Response(state["status"], json=state["payload"], headers=state["headers"])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        yield OpeningExplorer(client, "injected_transport"), client, state, requests


def test_synthetic_success_has_legal_moves_statistics_and_verified_parameters(mock_explorer):
    explorer, _, _, requests = mock_explorer
    result = explorer.moves(INITIAL)
    assert result.status == "ok" and result.base == "masters"
    assert result.position_statistics.games == 20
    assert result.position_statistics.white == 9
    assert [move.uci for move in result.moves] == ["e2e4", "d2d4"]
    assert result.moves[0].san == "e4" and result.moves[0].statistics.games == 10
    assert all(chess.Board(INITIAL).is_legal(chess.Move.from_uci(move.uci)) for move in result.moves)
    assert len(requests) == 1
    assert str(requests[0].url).split("?")[0] == ENDPOINT
    assert dict(requests[0].url.params) == {"fen": INITIAL, "moves": "12", "topGames": "0"}
    assert requests[0].extensions["timeout"]["read"] == 5.0


def test_empty_is_a_success_not_a_network_failure(mock_explorer):
    explorer, _, state, _ = mock_explorer
    state["payload"] = {"white": 0, "draws": 0, "black": 0, "moves": []}
    result = explorer.moves(INITIAL)
    assert result.status == "empty" and result.moves == []
    assert result.position_statistics.games == 0


@pytest.mark.parametrize("fen", ["bad fen", INITIAL.split()[0], "7k/8/8/8/8/8/8/8 w - - 0 1"])
def test_invalid_fen_makes_zero_transport_calls(mock_explorer, fen):
    explorer, _, _, requests = mock_explorer
    with pytest.raises(FenValidationError):
        explorer.moves(fen)
    assert requests == []


@pytest.mark.parametrize("fen", ["7k/6Q1/6K1/8/8/8/8/8 b - - 0 1",
                                "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"])
def test_terminal_position_never_queries_provider(mock_explorer, fen):
    explorer, _, _, requests = mock_explorer
    result = explorer.moves(fen)
    assert result.status == "terminal" and result.moves == [] and requests == []
    assert result.position_statistics is None


@pytest.mark.parametrize("status,code,http_status", [
    (429, "UPSTREAM_RATE_LIMITED", 503), (500, "UPSTREAM_UNAVAILABLE", 503),
    (503, "UPSTREAM_UNAVAILABLE", 503), (401, "UPSTREAM_AUTHORIZATION_FAILED", 502),
    (302, "UPSTREAM_INVALID_RESPONSE", 502),
])
def test_provider_error_has_no_retry(mock_explorer, status, code, http_status):
    explorer, _, state, requests = mock_explorer
    state["status"] = status
    with pytest.raises(ExplorerError) as error:
        explorer.moves(INITIAL)
    assert (error.value.code, error.value.http_status) == (code, http_status)
    assert len(requests) == 1


@pytest.mark.parametrize("exception,code,status", [
    (httpx.ReadTimeout("simulated"), "UPSTREAM_TIMEOUT", 504),
    (httpx.ConnectError("simulated"), "UPSTREAM_UNAVAILABLE", 503),
])
def test_transport_errors_are_typed(mock_explorer, exception, code, status):
    explorer, _, state, requests = mock_explorer
    state["exception"] = exception
    with pytest.raises(ExplorerError) as error:
        explorer.moves(INITIAL)
    assert (error.value.code, error.value.http_status) == (code, status)
    assert len(requests) == 1


@pytest.mark.parametrize("payload", [
    [], {}, {"moves": None}, {"moves": [None]}, {"moves": [{"uci": "bad"}]},
    {"moves": [{"uci": "e2e5"}]}, {"moves": [{"uci": "0000"}]},
    {"moves": [{"uci": "e2e4", "san": "d4"}]},
    {"moves": [{"uci": "e2e4"}, {"uci": "e2e4"}]},
    {"moves": [], "white": -1, "draws": 0, "black": 0},
    {"moves": [], "white": True, "draws": 0, "black": 0},
    {"moves": [], "white": "1", "draws": 0, "black": 0},
    {"moves": [], "white": 1},
    {"moves": [{"uci": "e2e4", "white": 1, "draws": -1, "black": 0}]},
    {"moves": [{}] * 257},
])
def test_invalid_payload_or_illegal_move_rejects_whole_response(mock_explorer, payload):
    explorer, _, state, _ = mock_explorer
    state["payload"] = payload
    with pytest.raises(ExplorerError, match="UPSTREAM_INVALID_RESPONSE"):
        explorer.moves(INITIAL)


@pytest.mark.parametrize("content", [b'{', b'x' * 65537])
def test_invalid_json_and_oversized_body_are_rejected(mock_explorer, content):
    explorer, _, state, _ = mock_explorer
    state["content"] = content
    with pytest.raises(ExplorerError, match="UPSTREAM_INVALID_RESPONSE"):
        explorer.moves(INITIAL)


def test_all_rows_validated_then_response_bounded(mock_explorer):
    explorer, _, state, _ = mock_explorer
    state["payload"] = {"moves": [{"uci": move.uci()} for move in chess.Board().legal_moves]}
    result = explorer.moves(INITIAL)
    assert len(result.moves) == 12 and result.moves_truncated
    assert result.position_statistics is None  # Aucun chiffre inventé.
    state["payload"]["moves"][-1] = {"uci": "e2e5"}
    with pytest.raises(ExplorerError):
        explorer.moves(INITIAL)  # Même une ligne au-delà des 12 doit être valide.


def test_slow_stream_budget_is_checked(mock_explorer, monkeypatch):
    explorer, _, _, _ = mock_explorer
    times = iter([0, 0, 11])
    monkeypatch.setattr("app.explorer.monotonic", lambda: next(times))
    with pytest.raises(ExplorerError, match="UPSTREAM_TIMEOUT"):
        explorer.moves(INITIAL)


@pytest.mark.parametrize("safe", ["", "/"])
def test_asgi_encoded_and_raw_slashes_preserve_fen(mock_explorer, safe):
    _, transport_client, _, requests = mock_explorer
    with TestClient(create_app(transport_client)) as client:
        response = client.get("/api/v1/moves/" + quote(INITIAL, safe=safe))
        assert client.get("/api/v1/healthcheck").json() == {"status": "ok"}
        assert client.post("/api/v1/positions/validate", json={"fen": INITIAL}).status_code == 200
    assert response.status_code == 200
    assert response.json()["fen_normalized"] == INITIAL
    assert response.json()["source_mode"] == "injected_transport"
    assert len(requests) == 1


def test_double_encoding_is_not_decoded_again(mock_explorer):
    _, transport_client, _, requests = mock_explorer
    with TestClient(create_app(transport_client)) as client:
        response = client.get("/api/v1/moves/" + quote(quote(INITIAL, safe=""), safe=""))
    assert response.status_code == 422 and not requests


@pytest.mark.parametrize("status,header,expected", [(429, "30", "30"), (429, "99999", "3600"),
                                                    (429, "invalid", None), (500, None, None)])
def test_http_provider_error_and_retry_after(mock_explorer, status, header, expected):
    _, transport_client, state, requests = mock_explorer
    state["status"] = status
    state["headers"] = {"Retry-After": header} if header else {}
    with TestClient(create_app(transport_client)) as client:
        response = client.get("/api/v1/moves/" + quote(INITIAL, safe=""))
    assert response.status_code == 503
    assert response.headers.get("Retry-After") == expected
    assert len(requests) == 1


def test_default_mode_disabled_and_bad_fen_still_422():
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/moves/" + quote(INITIAL, safe="")).status_code == 503
        assert client.get("/api/v1/moves/bad").status_code == 422


def test_fixture_mode_is_explicit_and_client_closed(monkeypatch):
    monkeypatch.setenv("EXPLORER_MODE", "synthetic_fixture")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/moves/" + quote(INITIAL, safe=""))
    assert response.status_code == 200 and response.json()["source_mode"] == "synthetic_fixture"
    assert app.state.explorer.client.is_closed


def test_live_mode_without_secret_configuration_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPLORER_MODE", "live")
    monkeypatch.setenv("LICHESS_API_TOKEN_FILE", str(tmp_path / "missing"))
    # I04bis : le plafond live n'impose plus la disponibilité au démarrage.
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/healthcheck").status_code == 200
        response = client.get("/api/v1/moves/" + quote(chess.STARTING_FEN, safe=""))
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "LICHESS_SECRET_UNREADABLE"
