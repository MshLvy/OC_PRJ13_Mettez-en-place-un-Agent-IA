"""Fixtures FEN : règles locales, jamais suggestions d'un modèle ou d'une API."""

import chess
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.positions import FenValidationError, diagnose_fen

INITIAL = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
MATE = "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"
STALEMATE = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_initial_position_has_twenty_legal_moves():
    result = diagnose_fen(INITIAL)
    assert result.fen_normalized == INITIAL
    assert result.side_to_move == "white"
    assert result.legal_moves_count == 20
    assert "e2e4" in result.legal_moves_uci
    assert "e2e5" not in result.legal_moves_uci  # Texte plausible, coup illégal.
    assert not result.legal_moves_truncated
    assert not result.is_check
    assert not result.is_terminal
    assert result.history_available is False
    assert result.repetition_status == "unknown_without_history"


@pytest.mark.parametrize("fen", [
    "", "not a fen", INITIAL.split()[0],
    INITIAL.replace(" 0 1", " 0"), INITIAL + " extra",
    INITIAL.replace("rnbqkbnr", "9"),
    INITIAL.replace(" w ", " x "),
    INITIAL.replace("KQkq", "KQK"),
    INITIAL.replace("KQkq", "HAha"),  # Shredder-FEN hors convention orthodoxe.
    INITIAL.replace("rnbqkbnr", "rnbqkbnr~"),
    INITIAL.replace(" - 0 1", " e4 0 1"),
    INITIAL.replace(" 0 1", " -1 1"),
    INITIAL.replace(" 0 1", " +0 1"),
    INITIAL.replace(" 0 1", " 0 0"),
])
def test_rejects_incomplete_or_nonstandard_fen(fen):
    with pytest.raises(FenValidationError) as error:
        diagnose_fen(fen)
    assert error.value.code == "INVALID_FEN_FORMAT"


@pytest.mark.parametrize("fen,issue", [
    ("7k/8/8/8/8/8/8/8 w - - 0 1", "NO_WHITE_KING"),
    ("8/8/8/8/8/8/8/K7 w - - 0 1", "NO_BLACK_KING"),
    ("7k/8/8/8/8/8/8/K6P w - - 0 1", "PAWNS_ON_BACKRANK"),
    ("7k/8/8/8/8/8/8/K7 w K - 0 1", "BAD_CASTLING_RIGHTS"),
    (INITIAL.replace(" - 0 1", " e3 0 1"), "INVALID_EP_SQUARE"),
    ("8/8/8/8/8/8/4k3/4K3 w - - 0 1", "OPPOSITE_CHECK"),
    ("7k/6Q1/6K1/8/8/8/8/8 w - - 0 1", "OPPOSITE_CHECK"),
])
def test_rejects_incoherent_position(fen, issue):
    with pytest.raises(FenValidationError) as error:
        diagnose_fen(fen)
    assert error.value.code == "INVALID_POSITION"
    assert issue in error.value.issues


@pytest.mark.parametrize("fen,termination,check", [
    (MATE, "checkmate", True), (STALEMATE, "stalemate", False),
])
def test_terminal_positions_have_no_legal_move(fen, termination, check):
    result = diagnose_fen(fen)
    assert result.is_terminal
    assert result.termination == termination
    assert result.is_check is check
    assert result.is_checkmate is (termination == "checkmate")
    assert result.is_stalemate is (termination == "stalemate")
    assert result.legal_moves_count == 0
    assert result.legal_moves_uci == []


def test_check_without_mate_allows_only_check_evasions():
    fen = "4k3/8/8/8/8/8/4R3/K7 b - - 0 1"
    result = diagnose_fen(fen)
    assert result.is_check and not result.is_terminal
    board = chess.Board(fen)
    for uci in result.legal_moves_uci:
        move = chess.Move.from_uci(uci)
        assert board.is_legal(move)
        board.push(move)
        assert not board.is_attacked_by(chess.WHITE, board.king(chess.BLACK))
        board.pop()


def test_king_only_draw_can_still_have_legal_moves():
    result = diagnose_fen("7k/8/8/8/8/8/8/K7 w - - 0 1")
    assert result.is_insufficient_material and result.is_terminal
    assert result.termination == "insufficient_material"
    assert result.legal_moves_count > 0


def test_seventyfive_moves_uses_supplied_counter_without_claim():
    result = diagnose_fen("7k/8/8/8/8/8/R7/K7 w - - 150 76")
    assert result.termination == "seventyfive_moves"
    assert result.is_terminal
    assert result.history_available is False


def test_normalization_preserves_uncapturable_en_passant_target():
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    result = diagnose_fen("  " + fen.replace(" ", "  ") + "  ")
    assert result.fen_normalized == fen
    assert result.side_to_move == "black"


def test_many_legal_moves_are_counted_and_returned_with_a_bound():
    fen = "8/7k/8/3Q4/8/2Q1Q3/8/K7 w - - 0 1"
    result = diagnose_fen(fen)
    assert result.legal_moves_count > 64
    assert len(result.legal_moves_uci) == 64
    assert result.legal_moves_truncated


def test_http_initial_position(client):
    response = client.post("/api/v1/positions/validate", json={"fen": INITIAL})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["legal_moves_count"] == 20
    assert body["history_available"] is False
    assert "e2e4" in body["legal_moves_uci"]


@pytest.mark.parametrize("body", [{}, {"fen": None}, {"fen": 42}, {"fen": ""},
                                      {"fen": "a" * 257}, {"fen": INITIAL, "move": "e2e4"}])
def test_http_rejects_invalid_request_schema(client, body):
    assert client.post("/api/v1/positions/validate", json=body).status_code == 422


@pytest.mark.parametrize("fen,code", [("bad fen", "INVALID_FEN_FORMAT"),
                                       ("7k/8/8/8/8/8/8/8 w - - 0 1", "INVALID_POSITION")])
def test_http_rejects_invalid_fen_with_explained_error(client, fen, code):
    response = client.post("/api/v1/positions/validate", json={"fen": fen})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize("fen,termination", [(MATE, "checkmate"), (STALEMATE, "stalemate")])
def test_http_terminal_diagnostic(client, fen, termination):
    response = client.post("/api/v1/positions/validate", json={"fen": fen})
    assert response.status_code == 200
    assert response.json()["termination"] == termination
    assert response.json()["legal_moves_count"] == 0


def test_http_wrong_method_and_malformed_json(client):
    assert client.get("/api/v1/positions/validate").status_code == 405
    assert client.post("/api/v1/positions/validate", content="{", headers={"Content-Type": "application/json"}).status_code == 422
