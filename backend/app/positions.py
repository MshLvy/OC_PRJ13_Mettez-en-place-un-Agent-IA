"""Diagnostic échiquéen local, indépendant du transport HTTP et d'un LLM."""

import re
from dataclasses import dataclass
from typing import Literal

import chess

MAX_FEN_LENGTH = 256
MAX_RETURNED_MOVES = 64
Termination = Literal["checkmate", "stalemate", "insufficient_material", "seventyfive_moves"]


class FenValidationError(ValueError):
    def __init__(self, code: str, issues: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.issues = issues


@dataclass(frozen=True)
class PositionDiagnostic:
    valid: bool
    fen_normalized: str
    side_to_move: Literal["white", "black"]
    legal_moves_count: int
    legal_moves_uci: list[str]
    legal_moves_truncated: bool
    is_check: bool
    is_checkmate: bool
    is_stalemate: bool
    is_insufficient_material: bool
    is_terminal: bool
    termination: Termination | None
    history_available: bool = False
    repetition_status: str = "unknown_without_history"


def diagnose_fen(fen: str) -> PositionDiagnostic:
    """Accepte une FEN orthodoxe complète ; ne prouve pas sa trajectoire passée."""
    if not isinstance(fen, str) or not 1 <= len(fen) <= MAX_FEN_LENGTH:
        raise FenValidationError("INVALID_FEN_FORMAT")
    fields = fen.split()
    if len(fields) != 6:
        raise FenValidationError("INVALID_FEN_FORMAT")
    placement, turn, castling, ep, halfmove, fullmove = fields
    # La bibliothèque tolère des extensions/champs absents : notre contrat non.
    if (
        not re.fullmatch(r"[prnbqkPRNBQK1-8/]+", placement)
        or turn not in ("w", "b")
        or not re.fullmatch(r"-|K?Q?k?q?", castling)
        or not re.fullmatch(r"-|[a-h][36]", ep)
        or not re.fullmatch(r"[0-9]+", halfmove)
        or not re.fullmatch(r"[0-9]+", fullmove)
        or int(fullmove) < 1
    ):
        raise FenValidationError("INVALID_FEN_FORMAT")
    try:
        board = chess.Board(" ".join(fields), chess960=False)
    except ValueError:
        raise FenValidationError("INVALID_FEN_FORMAT") from None
    status = board.status()
    if status != chess.STATUS_VALID:
        issues = tuple(flag.name for flag in chess.Status if status & flag)
        raise FenValidationError("INVALID_POSITION", issues)

    legal_moves = sorted(move.uci() for move in board.legal_moves)
    checkmate = board.is_checkmate()
    stalemate = board.is_stalemate()
    insufficient = board.is_insufficient_material()
    termination: Termination | None = None
    if checkmate:
        termination = "checkmate"
    elif stalemate:
        termination = "stalemate"
    elif insufficient:
        termination = "insufficient_material"
    elif board.is_seventyfive_moves():
        termination = "seventyfive_moves"
    return PositionDiagnostic(
        valid=True,
        # Conserve une cible en passant valide, même sans capture légale actuelle.
        fen_normalized=board.fen(en_passant="fen"),
        side_to_move="white" if board.turn == chess.WHITE else "black",
        legal_moves_count=len(legal_moves),
        legal_moves_uci=legal_moves[:MAX_RETURNED_MOVES],
        legal_moves_truncated=len(legal_moves) > MAX_RETURNED_MOVES,
        is_check=board.is_check(),
        is_checkmate=checkmate,
        is_stalemate=stalemate,
        is_insufficient_material=insufficient,
        is_terminal=termination is not None,
        termination=termination,
    )
