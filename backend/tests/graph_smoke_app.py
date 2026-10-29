"""Application de preuve HTTP, embarquée UNIQUEMENT dans la cible Docker test.

Vrai Uvicorn/LangGraph, outils injectés : jamais une preuve Lichess/Stockfish live.
"""
import os
import socket

import chess
import chess.engine
import httpx2 as httpx

from app.main import create_app
from app import stockfish

CASE = os.getenv('GRAPH_SMOKE_CASE', 'success')
if CASE not in ('success', 'rate_limit', 'engine_timeout'):
    raise ValueError('INVALID_GRAPH_SMOKE_CASE')
CALLS = []


def forbidden(*args, **kwargs):
    raise AssertionError('REAL_IO_FORBIDDEN_IN_GRAPH_SMOKE')


# Filets de sécurité de cette application de test, aucun effet dans le runtime.
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
stockfish.spawn_engine = forbidden


def explorer_transport(request):
    CALLS.append('explorer')
    if CASE == 'rate_limit':
        return httpx.Response(429, headers={'Retry-After': '9'})
    return httpx.Response(200, json={'moves': [{'uci':'e2e4'}]})


async def engine_runner(settings, board, gate):
    CALLS.append('engine')
    if CASE == 'engine_timeout':
        raise stockfish.StockfishError('STOCKFISH_TIMEOUT',504)
    return stockfish.RawEvaluation({'depth':8,'score':chess.engine.PovScore(chess.engine.Cp(42),board.turn)},
                                  chess.Move.from_uci('d2d4'),'Stockfish simulated')


app = create_app(explorer_client=httpx.Client(transport=httpx.MockTransport(explorer_transport)),
                 stockfish_runner=engine_runner)


@app.get('/smoke/evidence', include_in_schema=False)
def evidence():
    return {'kind':'REAL_LANGGRAPH_HTTP_WITH_SIMULATED_TOOLS','case':CASE,'calls':CALLS,
            'real_network_guard':True,'real_engine_guard':True}
