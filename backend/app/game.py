"""Partie stateless : python-chess est l'autorité, jamais une FEN du navigateur."""
from dataclasses import dataclass
import hashlib
import os
import re
from threading import Lock
from time import monotonic
from typing import Literal

import chess
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.explorer import ExplorerError
from app.stockfish import StockfishError

MAX_PLIES = 256
OPENING_PLIES = 24
GAME_BUDGET = 20.0
_GATE = Lock()


class GameError(Exception):
    def __init__(self, code, status=422):
        super().__init__(code);self.code=code;self.status=status


class HistoryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    history: list[str] = Field(default_factory=list, max_length=MAX_PLIES)

    @field_validator('history')
    @classmethod
    def bounded_uci(cls, values):
        if any(not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', v) for v in values):
            raise ValueError('INVALID_UCI')
        return values


class TurnRequest(HistoryRequest):
    mode: Literal['study', 'computer']
    human_color: Literal['white', 'black'] = 'white'
    source: Literal['synthetic_fixture', 'theory_then_engine', 'engine'] = 'synthetic_fixture'
    revision: StrictInt = Field(ge=0, le=MAX_PLIES)
    snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')
    move: str | None = Field(default=None, min_length=4, max_length=5)

    @field_validator('move')
    @classmethod
    def move_uci(cls, value):
        if value is not None and not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?', value):
            raise ValueError('INVALID_UCI')
        return value


class Ply(BaseModel):
    uci: str
    san: str
    fen_after: str


class GameState(BaseModel):
    history: list[str]
    revision: int
    snapshot: str
    fen: str
    turn: Literal['white', 'black']
    legal_moves: list[str]
    played: list[Ply]
    terminal: bool
    result: str | None
    termination: str | None


class Choice(BaseModel):
    source: Literal['none', 'synthetic_fixture', 'lichess_opening_explorer', 'stockfish']
    source_mode: str
    reason: str
    synthetic: bool


class TurnResponse(BaseModel):
    status: Literal['ok', 'unavailable', 'terminal', 'opening_complete']
    state: GameState
    applied: list[Ply]
    choice: Choice
    errors: list[str] = Field(default_factory=list)
    budget_seconds: float = GAME_BUDGET
    retries: Literal[0] = 0


def terminal_outcome(board):
    # Réclamer une nulle seulement sur l'état atteint, pas sur un coup annoncé futur.
    outcome=board.outcome(claim_draw=False)
    if outcome:return outcome
    if board.is_repetition(3):return chess.Outcome(chess.Termination.THREEFOLD_REPETITION,None)
    if board.is_fifty_moves():return chess.Outcome(chess.Termination.FIFTY_MOVES,None)
    return None


def rebuild(history):
    if len(history)>MAX_PLIES:raise GameError('HISTORY_LIMIT')
    board=chess.Board();played=[]
    for text in history:
        if terminal_outcome(board) is not None:raise GameError('MOVE_AFTER_TERMINAL')
        try:move=chess.Move.from_uci(text)
        except ValueError:raise GameError('INVALID_UCI') from None
        if move not in board.legal_moves:raise GameError('ILLEGAL_MOVE')
        san=board.san(move);board.push(move)
        played.append(Ply(uci=text,san=san,fen_after=board.fen(en_passant='fen')))
    return board,played


def snapshot(history):
    # Checksum de synchronisation, pas signature d'identité ni session persistante.
    return hashlib.sha256(('game-v1\n'+'\n'.join(history)).encode('ascii')).hexdigest()


def state_from(board,played):
    outcome=terminal_outcome(board)
    history=[p.uci for p in played]
    return GameState(history=history,revision=len(history),snapshot=snapshot(history),
        fen=board.fen(en_passant='fen'),turn='white' if board.turn else 'black',
        legal_moves=[] if outcome else sorted(m.uci() for m in board.legal_moves),played=played,
        terminal=outcome is not None,result=outcome.result() if outcome else None,
        termination=outcome.termination.name.lower() if outcome else None)


def apply_move(board,text):
    try:move=chess.Move.from_uci(text)
    except ValueError:raise GameError('INVALID_UCI') from None
    if move not in board.legal_moves:raise GameError('ILLEGAL_MOVE')
    san=board.san(move);board.push(move)
    return Ply(uci=text,san=san,fen_after=board.fen(en_passant='fen'))


def fixture_move(board,history):
    # Démo inventée : préférence de ligne, puis ordre légal déterministe, jamais théorie réelle.
    lines=[['e2e4','c7c5','g1f3','d7d6','d2d4','c5d4','f3d4','g8f6','b1c3','a7a6'],
           ['d2d4','d7d5','c2c4','e7e6']]
    for line in lines:
        if history==line[:len(history)] and len(history)<len(line):
            move=chess.Move.from_uci(line[len(history)])
            if move in board.legal_moves:return move.uci()
    return sorted(m.uci() for m in board.legal_moves)[0]


class GameService:
    def __init__(self,explorer,engine,*,allow_tools=False,clock=monotonic,gate=None):
        self.explorer,self.engine=explorer,engine
        self.allow_tools,self.clock,self.gate=allow_tools,clock,gate if gate is not None else _GATE

    def choose(self,board,history,source,deadline):
        if source=='synthetic_fixture':
            return fixture_move(board,history),Choice(source='synthetic_fixture',source_mode='synthetic_fixture',
                reason='SYNTHETIC_LEGAL_DEMO_NOT_THEORY',synthetic=True),[]
        errors=[]
        if not self.allow_tools:
            return None,Choice(source='none',source_mode='disabled',reason='GAME_TOOLS_DISABLED',synthetic=False),['GAME_TOOLS_DISABLED']
        if source=='theory_then_engine':
            if deadline-self.clock()>=15.0:
                try:
                    result=self.explorer.moves(board.fen(en_passant='fen'))
                    candidates=[m for m in result.moves if chess.Move.from_uci(m.uci) in board.legal_moves]
                    if candidates and self.clock()<=deadline:
                        chosen=sorted(candidates,key=lambda m:(-(m.statistics.games if m.statistics else 0),m.uci))[0]
                        mode=self.explorer.source_mode
                        return chosen.uci,Choice(source='lichess_opening_explorer',source_mode=mode,
                            reason='MOST_PLAYED_LEGAL_NOT_BEST_MOVE',synthetic=mode in ('synthetic_fixture','injected_transport')),errors
                    errors.append('THEORY_EMPTY_OR_ILLEGAL')
                except (ExplorerError,ValueError,AttributeError):errors.append('THEORY_UNAVAILABLE')
                except Exception:errors.append('THEORY_INTERNAL_ERROR')
            else:errors.append('GAME_THEORY_BUDGET_EXCEEDED')
        if deadline-self.clock()<5.0:
            errors.append('GAME_ENGINE_BUDGET_EXCEEDED')
        else:
            try:
                result=self.engine.choose_move(board.fen(en_passant='fen'))
                move=chess.Move.from_uci(result.uci)
                if move not in board.legal_moves:raise GameError('ENGINE_ILLEGAL_MOVE')
                if self.clock()>deadline:raise GameError('GAME_DEADLINE_EXCEEDED')
                return result.uci,Choice(source='stockfish',source_mode='local_engine',reason='UCI_BESTMOVE_VALIDATED',synthetic=False),errors
            except StockfishError as error:errors.append(error.code)
            except Exception:errors.append('ENGINE_UNAVAILABLE_OR_ILLEGAL')
        return None,Choice(source='none',source_mode='unavailable',reason='NO_OPPONENT_AVAILABLE',synthetic=False),errors

    def turn(self,request):
        request=TurnRequest.model_validate(request.model_dump())
        board,played=rebuild(request.history)
        if request.revision!=len(request.history) or request.snapshot!=snapshot(request.history):
            raise GameError('GAME_SNAPSHOT_MISMATCH',409)
        if not self.gate.acquire(blocking=False):raise GameError('GAME_BUSY',503)
        try:
            deadline=self.clock()+GAME_BUDGET;applied=[];errors=[]
            choice=Choice(source='none',source_mode='not_requested',reason='NO_AUTOMATIC_MOVE',synthetic=False)
            if terminal_outcome(board) is not None:
                if request.move is not None:raise GameError('MOVE_AFTER_TERMINAL')
                return TurnResponse(status='terminal',state=state_from(board,played),applied=[],choice=choice)
            if request.mode=='computer' and len(played)>=OPENING_PLIES:
                return TurnResponse(status='opening_complete',state=state_from(board,played),applied=[],choice=choice)
            human=(request.human_color=='white')
            if request.mode=='study':
                if request.move is None:raise GameError('MOVE_REQUIRED')
            elif board.turn==human:
                if request.move is None:raise GameError('HUMAN_MOVE_REQUIRED')
            elif request.move is not None:raise GameError('NOT_HUMAN_TURN',409)
            if request.move is not None:
                if len(played)>=MAX_PLIES:raise GameError('HISTORY_LIMIT')
                ply=apply_move(board,request.move);played.append(ply);applied.append(ply)
            status='ok'
            if terminal_outcome(board) is not None:status='terminal'
            elif request.mode=='computer' and len(played)>=OPENING_PLIES:status='opening_complete'
            elif request.mode=='computer' and board.turn!=human:
                move,choice,errors=self.choose(board,[p.uci for p in played],request.source,deadline)
                if move is None:status='unavailable'
                else:
                    ply=apply_move(board,move);played.append(ply);applied.append(ply)
                    if terminal_outcome(board) is not None:status='terminal'
                    elif len(played)>=OPENING_PLIES:status='opening_complete'
            return TurnResponse(status=status,state=state_from(board,played),applied=applied,choice=choice,errors=errors)
        finally:self.gate.release()
