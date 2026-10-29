"""Stockfish UCI local : processus isolé par requête, bornes et arrêt vérifié."""

import asyncio
from dataclasses import dataclass, field
import os
import re
import subprocess
from threading import Lock
from typing import Literal

import chess
import chess.engine

from app.config import StockfishSettings
from app.positions import PositionDiagnostic, diagnose_fen

THREADS = 1
HASH_MB = 16
DEPTH_LIMIT = 20
STARTUP_TIMEOUT = 2.0
ANALYSIS_TIMEOUT = 2.0
QUIT_TIMEOUT = 0.25
KILL_WAIT_TIMEOUT = 0.75
MAX_UCI_BYTES = 262144
MAX_UCI_LINE = 16384


class StockfishError(Exception):
    def __init__(self, code: str, http_status: int):
        super().__init__(code)
        self.code, self.http_status = code, http_status


@dataclass
class EngineGate:
    lock: Lock = field(default_factory=Lock)
    quarantined: bool = False


_GLOBAL_GATE = EngineGate()  # Un seul moteur dans ce processus/worker, sans file.


class BoundedUciProtocol(chess.engine.UciProtocol):
    def __init__(self):
        super().__init__()
        self.output_bytes = 0
        self.output_exceeded = False

    def pipe_data_received(self, fd, data):
        self.output_bytes += len(data)
        buffered = bytes(self.buffer[fd]) + data
        if self.output_exceeded or self.output_bytes > MAX_UCI_BYTES or any(
                len(line) > MAX_UCI_LINE for line in buffered.split(b"\n")):
            self.output_exceeded = True
            if self.transport is not None:
                self.transport.close()  # ferme/kill le processus, pas de log de la sortie brute.
            return
        super().pipe_data_received(fd, data)


async def spawn_engine(path):
    # Aucun shell et aucun argument issu de la FEN. Le moteur local n'a besoin
    # ni du jeton Lichess ni des credentials/proxies du processus applicatif.
    return await BoundedUciProtocol.popen(
        [path], setpgrp=True, stderr=subprocess.DEVNULL,
        env={"PATH": os.defpath, "LANG": "C", "LC_ALL": "C"},
    )


@dataclass(frozen=True)
class RawEvaluation:
    info: dict
    best_move: chess.Move | None
    engine_version: str | None


async def _search(protocol, board, settings):
    analysis = await protocol.analysis(
        board, chess.engine.Limit(time=settings.time_seconds, depth=DEPTH_LIMIT),
        multipv=1, info=chess.engine.INFO_BASIC | chess.engine.INFO_SCORE,
    )
    info = {}
    with analysis:
        async for update in analysis:
            info.update(update)
            if "score" in update:
                # Les bornes d'un ancien score ne doivent pas survivre à un
                # nouveau score sans borne dans les mises à jour agrégées UCI.
                info["lowerbound"] = update.get("lowerbound", False)
                info["upperbound"] = update.get("upperbound", False)
        best = await analysis.wait()
    name = protocol.id.get("name")
    version = name if isinstance(name, str) and re.fullmatch(
        r"Stockfish(?: [A-Za-z0-9.+_-]+){0,4}", name[:129]) and len(name) <= 128 else None
    return RawEvaluation(info, best.move, version)


async def _shutdown(transport, protocol):
    if transport.get_returncode() is None:
        try:
            await asyncio.wait_for(protocol.quit(), QUIT_TIMEOUT)
        except (TimeoutError, chess.engine.EngineError, OSError):
            pass
    if transport.get_returncode() is None:
        try:
            transport.kill()
        except ProcessLookupError:
            pass
    try:
        # shield : ne pas annuler le Future de récolte partagé par le protocole.
        await asyncio.wait_for(asyncio.shield(protocol.returncode), KILL_WAIT_TIMEOUT)
        return True
    except TimeoutError:
        return False
    finally:
        transport.close()


async def run_engine(settings, board, gate):
    transport = protocol = None

    async def prepare():
        nonlocal transport, protocol
        transport, protocol = await spawn_engine(settings.path)
        await protocol.initialize()
        await protocol.configure({"Threads": THREADS, "Hash": HASH_MB})

    try:
        await asyncio.wait_for(prepare(), STARTUP_TIMEOUT)
        return await asyncio.wait_for(_search(protocol, board, settings), ANALYSIS_TIMEOUT)
    except FileNotFoundError:
        raise StockfishError("STOCKFISH_NOT_FOUND", 503) from None
    except TimeoutError:
        raise StockfishError("STOCKFISH_TIMEOUT", 504) from None
    except chess.engine.EngineTerminatedError:
        code = "STOCKFISH_PROTOCOL_ERROR" if protocol and protocol.output_exceeded else "STOCKFISH_UNAVAILABLE"
        raise StockfishError(code, 502 if code.endswith("PROTOCOL_ERROR") else 503) from None
    except (chess.engine.EngineError, ValueError):
        raise StockfishError("STOCKFISH_PROTOCOL_ERROR", 502) from None
    except OSError:
        raise StockfishError("STOCKFISH_UNAVAILABLE", 503) from None
    finally:
        if transport is not None:
            if not await _shutdown(transport, protocol):
                # Ne pas libérer la capacité de spawn si la récolte est incertaine.
                # Le lock est relâché, mais tout nouveau calcul est refusé jusqu'au restart.
                gate.quarantined = True
                raise StockfishError("STOCKFISH_CLEANUP_FAILED", 503)


@dataclass(frozen=True)
class EvaluationScore:
    type: Literal["cp", "mate"]
    value: int
    perspective: Literal["white"] = "white"
    bound: Literal["none", "lower", "upper"] = "none"


@dataclass(frozen=True)
class EvaluationLimits:
    analysis_applied: bool
    time_seconds: float
    depth: int = DEPTH_LIMIT
    threads: int = THREADS
    hash_mb: int = HASH_MB
    multipv: int = 1
    startup_timeout_seconds: float = STARTUP_TIMEOUT
    analysis_timeout_seconds: float = ANALYSIS_TIMEOUT
    quit_timeout_seconds: float = QUIT_TIMEOUT
    kill_wait_timeout_seconds: float = KILL_WAIT_TIMEOUT


@dataclass(frozen=True)
class Evaluation:
    status: Literal["ok", "terminal"]
    fen_normalized: str
    position: PositionDiagnostic
    limits: EvaluationLimits
    engine_version: str | None = None
    depth: int | None = None
    score: EvaluationScore | None = None
    best_move_uci: str | None = None
    best_move_san: str | None = None
    source: Literal["stockfish"] = "stockfish"
    source_mode: Literal["local_engine"] = "local_engine"


def _normalize(raw, board, diagnostic, limits):
    invalid = lambda: StockfishError("STOCKFISH_PROTOCOL_ERROR", 502)
    if (not isinstance(raw, RawEvaluation) or not isinstance(raw.info, dict)
            or not isinstance(raw.best_move, chess.Move) or not board.is_legal(raw.best_move)):
        raise invalid()
    score = raw.info.get("score")
    depth = raw.info.get("depth")
    if (not isinstance(score, chess.engine.PovScore) or
            (depth is not None and (type(depth) is not int or not 0 <= depth <= DEPTH_LIMIT))):
        raise invalid()
    white = score.white()
    kind = "mate" if white.is_mate() else "cp"
    value = white.mate() if kind == "mate" else white.score()
    lower, upper = raw.info.get("lowerbound", False), raw.info.get("upperbound", False)
    if (type(value) is not int or (kind == "mate" and value == 0)
            or type(lower) is not bool or type(upper) is not bool or (lower and upper)):
        raise invalid()
    bound = "lower" if lower else "upper" if upper else "none"
    if score.turn == chess.BLACK and bound != "none":
        bound = "upper" if bound == "lower" else "lower"
    return Evaluation("ok", diagnostic.fen_normalized, diagnostic, limits,
                      raw.engine_version, depth, EvaluationScore(kind, value, bound=bound),
                      raw.best_move.uci(), board.san(raw.best_move))


class StockfishService:
    def __init__(self, settings, runner=None, gate=None):
        self.settings = settings
        self.runner = runner or run_engine
        self.gate = gate or _GLOBAL_GATE

    def evaluate(self, fen):
        diagnostic = diagnose_fen(fen)
        limits = EvaluationLimits(not diagnostic.is_terminal, self.settings.time_seconds)
        if diagnostic.is_terminal:
            return Evaluation("terminal", diagnostic.fen_normalized, diagnostic, limits)
        if not self.settings.enabled:
            raise StockfishError("STOCKFISH_DISABLED", 503)
        if not self.gate.lock.acquire(blocking=False):
            raise StockfishError("STOCKFISH_BUSY", 503)
        try:
            if self.gate.quarantined:
                raise StockfishError("STOCKFISH_UNAVAILABLE", 503)
            board = chess.Board(diagnostic.fen_normalized)
            raw = asyncio.run(self.runner(self.settings, board, self.gate))
            return _normalize(raw, board, diagnostic, limits)
        finally:
            self.gate.lock.release()

    def choose_move(self, fen):
        """Vrai bestmove UCI de la recherche bornée existante, jamais déduit du score."""
        result = self.evaluate(fen)
        if result.status != 'ok' or result.best_move_uci is None:
            raise StockfishError('STOCKFISH_NO_LEGAL_MOVE', 422)
        board = chess.Board(result.fen_normalized)
        move = chess.Move.from_uci(result.best_move_uci)
        if move not in board.legal_moves:
            raise StockfishError('STOCKFISH_PROTOCOL_ERROR', 502)
        return EngineMove(move.uci(), board.san(move), result.engine_version, result.limits)


@dataclass(frozen=True)
class EngineMove:
    uci: str
    san: str
    engine_version: str | None
    limits: EvaluationLimits
