"""Adaptateur Opening Explorer : transport injecté, sans client live par défaut."""

import json
from time import monotonic
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Literal

import chess
import httpx2 as httpx

from app.positions import diagnose_fen

ENDPOINT = "https://explorer.lichess.org/masters"
MOVE_LIMIT = 12
MAX_PROVIDER_MOVES = 256
MAX_RESPONSE_BYTES = 65536
TIMEOUT_SECONDS = 5.0
SourceMode = Literal["disabled", "synthetic_fixture", "injected_transport", "live"]


class ExplorerError(Exception):
    def __init__(self, code: str, http_status: int, retry_after: int | None = None):
        super().__init__(code)
        self.code, self.http_status, self.retry_after = code, http_status, retry_after


@dataclass(frozen=True)
class GameStats:
    white: int
    draws: int
    black: int
    games: int


@dataclass(frozen=True)
class ObservedMove:
    uci: str
    san: str
    statistics: GameStats | None


@dataclass(frozen=True)
class MovesResult:
    status: Literal["ok", "empty", "terminal"]
    fen_normalized: str
    source_mode: SourceMode
    position_statistics: GameStats | None
    moves: list[ObservedMove]
    moves_truncated: bool = False
    source: str = "lichess_opening_explorer"
    base: str = "masters"


def _invalid() -> ExplorerError:
    return ExplorerError("UPSTREAM_INVALID_RESPONSE", 502)


def _stats(payload: dict) -> GameStats | None:
    keys = ("white", "draws", "black")
    if not any(key in payload for key in keys):
        return None
    values = [payload.get(key) for key in keys]
    if any(type(value) is not int or value < 0 for value in values):
        raise _invalid()
    return GameStats(*values, games=sum(values))


def _retry_after(value: str | None) -> int | None:
    if not value:
        return None
    try:
        seconds = int(value) if value.isascii() and value.isdigit() else int(
            (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        )
        return min(3600, max(0, seconds))
    except (ValueError, TypeError, OverflowError):
        return None


class OpeningExplorer:
    def __init__(self, client: httpx.Client | None, source_mode: SourceMode = "disabled"):
        self.client = client
        self.source_mode = source_mode

    def moves(self, fen: str) -> MovesResult:
        diagnostic = diagnose_fen(fen)  # Avant accès transport, même désactivé.
        if diagnostic.is_terminal:
            return MovesResult("terminal", diagnostic.fen_normalized, self.source_mode, None, [])
        if self.client is None:
            raise ExplorerError("EXPLORER_DISABLED", 503)
        params = {"fen": diagnostic.fen_normalized, "moves": MOVE_LIMIT, "topGames": 0}
        started = monotonic()
        try:
            # Un seul appel, pas de redirection ni retry automatique.
            with self.client.stream("GET", ENDPOINT, params=params, timeout=TIMEOUT_SECONDS,
                                    follow_redirects=False) as response:
                if monotonic() - started > 10:
                    raise ExplorerError("UPSTREAM_TIMEOUT", 504)
                if response.status_code in (401, 403):
                    raise ExplorerError("UPSTREAM_AUTHORIZATION_FAILED", 502)
                if response.status_code == 429:
                    raise ExplorerError("UPSTREAM_RATE_LIMITED", 503,
                                        _retry_after(response.headers.get("Retry-After")))
                if response.status_code >= 500:
                    raise ExplorerError("UPSTREAM_UNAVAILABLE", 503)
                if response.status_code != 200:
                    raise _invalid()
                body = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() - started > 10:
                        raise ExplorerError("UPSTREAM_TIMEOUT", 504)
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise _invalid()
        except httpx.TimeoutException:
            raise ExplorerError("UPSTREAM_TIMEOUT", 504) from None
        except httpx.RequestError:
            raise ExplorerError("UPSTREAM_UNAVAILABLE", 503) from None
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeError):
            raise _invalid() from None
        if not isinstance(payload, dict) or not isinstance(payload.get("moves"), list):
            raise _invalid()
        rows = payload["moves"]
        if len(rows) > MAX_PROVIDER_MOVES:
            raise _invalid()
        board = chess.Board(diagnostic.fen_normalized)
        parsed: list[ObservedMove] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("uci"), str):
                raise _invalid()
            try:
                move = chess.Move.from_uci(row["uci"])
            except ValueError:
                raise _invalid() from None
            if not board.is_legal(move) or row["uci"] in seen:
                raise _invalid()
            seen.add(row["uci"])
            san = board.san(move)
            if "san" in row and row["san"] != san:
                raise _invalid()
            parsed.append(ObservedMove(row["uci"], san, _stats(row)))
        return MovesResult(
            "ok" if parsed else "empty", diagnostic.fen_normalized, self.source_mode,
            _stats(payload), parsed[:MOVE_LIMIT], len(parsed) > MOVE_LIMIT,
        )
