"""Boucle réelle de jeu Python, sources outils mock et fixture explicitement inventée."""
from threading import Lock
from types import SimpleNamespace as NS
import chess
import chess.engine
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.game import GameService,TurnRequest,HistoryRequest,rebuild,state_from,snapshot,GameError,apply_move
from app.stockfish import StockfishService,StockfishError,RawEvaluation,EngineGate
from app.config import StockfishSettings
from app.explorer import ExplorerError

@pytest.fixture(autouse=True)
def isolate(monkeypatch):monkeypatch.setenv('GAME_ALLOW_TOOLS','false');monkeypatch.setenv('YOUTUBE_MODE','disabled')

def request(history=None,move=None,**kwargs):
    history=history or []
    return TurnRequest(mode='computer',human_color='white',history=history,revision=len(history),snapshot=snapshot(history),move=move,**kwargs)

def game(**kwargs):return GameService(None,None,**kwargs)

def test_three_successive_human_turns_and_sicilian_response():
    service=game();history=[]
    for human,automatic in [('e2e4','c7c5'),('g1f3','d7d6'),('d2d4','c5d4')]:
        r=service.turn(request(history,human));assert [p.uci for p in r.applied]==[human,automatic]
        history=r.state.history
        assert r.state.fen==rebuild(history)[0].fen(en_passant='fen')
        assert r.state.turn=='white' and r.choice.synthetic and r.choice.source=='synthetic_fixture'
    assert len(history)==6

def test_computer_white_starts_once_when_human_black():
    body=request();body.human_color='black'
    r=game().turn(body)
    assert r.state.history==['e2e4'] and r.state.turn=='black'
    repeat=game().turn(body)
    assert repeat.state==r.state

def test_study_both_camps_one_move_each():
    service=game();history=[]
    for text in ('e2e4','e7e5','g1f3'):
        body=request(history,text);body.mode='study';r=service.turn(body)
        assert len(r.applied)==1 and r.choice.source=='none';history=r.state.history

@pytest.mark.parametrize('move',['e2e5','e7e5','e1e3'])
def test_illegal_human_moves(move):
    with pytest.raises(GameError,match='ILLEGAL_MOVE'):game().turn(request(move=move))

@pytest.mark.parametrize('change',[{'revision':1},{'snapshot':'0'*64}])
def test_snapshot_mismatch(change):
    body=request(move='e2e4')
    for k,v in change.items():setattr(body,k,v)
    with pytest.raises(GameError,match='SNAPSHOT'):game().turn(body)

def test_human_cannot_play_for_computer():
    body=request(move='e2e4');body.human_color='black'
    with pytest.raises(GameError,match='NOT_HUMAN_TURN'):game().turn(body)

def test_missing_human_move_not_automatic():
    with pytest.raises(GameError,match='HUMAN_MOVE_REQUIRED'):game().turn(request())

@pytest.mark.parametrize('bad',[{'history':['x']},{'history':['e2e4']*257},{'fen':'forged'},{'mode':'unknown'}])
def test_http_bad_contract(bad):
    with TestClient(create_app()) as client:
        payload=request(move='e2e4').model_dump();payload.update(bad)
        r=client.post('/api/v1/game/turn',json=payload)
    assert r.status_code==422

def test_http_state_and_turn_are_authoritative():
    with TestClient(create_app()) as client:
        state=client.post('/api/v1/game/state',json={'history':[]}).json()
        r=client.post('/api/v1/game/turn',json={**request(move='e2e4').model_dump(),'snapshot':state['snapshot']})
    assert r.status_code==200 and r.json()['state']['history']==['e2e4','c7c5']
    assert r.json()['applied'][0]['san']=='e4' and r.json()['applied'][1]['san']=='c5'

def test_tools_disabled_never_calls_provider():
    class Forbidden:
        def __getattr__(self,name):raise AssertionError('NO_TOOL_CALL')
    service=GameService(Forbidden(),Forbidden())
    r=service.turn(request(move='e2e4',source='theory_then_engine'))
    assert r.status=='unavailable' and r.state.history==['e2e4'] and r.choice.source=='none'

def candidate(uci,n):return NS(uci=uci,statistics=NS(games=n))

def test_theory_most_played_legal_then_uci_not_best_claim():
    explorer=NS(source_mode='synthetic_fixture',moves=lambda fen:NS(moves=[candidate('c7c5',10),candidate('e7e5',10),candidate('a2a3',99)]))
    r=GameService(explorer,None,allow_tools=True).turn(request(move='e2e4',source='theory_then_engine'))
    assert r.applied[-1].uci=='c7c5' and r.choice.synthetic
    assert r.choice.reason=='MOST_PLAYED_LEGAL_NOT_BEST_MOVE'

@pytest.mark.parametrize('failure',['empty','error'])
def test_theory_empty_or_error_falls_back_to_engine(failure):
    def moves(fen):
        if failure=='error':raise ExplorerError('UPSTREAM_TIMEOUT',504)
        return NS(moves=[])
    calls=[]
    engine=NS(choose_move=lambda fen:(calls.append(fen) or NS(uci='c7c5')))
    r=GameService(NS(moves=moves),engine,allow_tools=True).turn(request(move='e2e4',source='theory_then_engine'))
    assert len(calls)==1 and r.choice.source=='stockfish' and not r.choice.synthetic
    assert r.errors and r.state.history==['e2e4','c7c5']

def test_no_available_tool_no_invented_legal_fallback():
    def missing(fen):raise StockfishError('STOCKFISH_DISABLED',503)
    r=GameService(NS(moves=lambda fen:NS(moves=[])),NS(choose_move=missing),allow_tools=True).turn(request(move='e2e4',source='theory_then_engine'))
    assert r.status=='unavailable' and r.state.history==['e2e4'] and r.errors[-1]=='STOCKFISH_DISABLED'

def test_illegal_engine_move_never_applied():
    r=GameService(None,NS(choose_move=lambda fen:NS(uci='a2a3')),allow_tools=True).turn(request(move='e2e4',source='engine'))
    assert r.status=='unavailable' and r.state.history==['e2e4']

def test_stockfish_choose_move_uses_bounded_uci_result_not_score_guess():
    calls=[]
    async def runner(settings,board,gate):
        calls.append(board.fen());return RawEvaluation({'score':chess.engine.PovScore(chess.engine.Cp(23),board.turn),'depth':8},chess.Move.from_uci('e2e4'),'Stockfish fixture')
    service=StockfishService(StockfishSettings(enabled=True),runner,EngineGate())
    result=service.choose_move(chess.STARTING_FEN)
    assert result.uci=='e2e4' and result.san=='e4' and len(calls)==1
    assert result.limits.threads==1 and result.limits.hash_mb==16 and result.limits.analysis_timeout_seconds==2

def test_disabled_stockfish_choose_move_explicit():
    with pytest.raises(StockfishError,match='DISABLED'):StockfishService(StockfishSettings()).choose_move(chess.STARTING_FEN)

def test_terminal_fools_mate_and_no_moves_after():
    history=['f2f3','e7e5','g2g4','d8h4']
    r=game().turn(request(history));assert r.status=='terminal' and r.state.result=='0-1' and not r.applied
    with pytest.raises(GameError,match='TERMINAL'):rebuild(history+['a2a3'])

def test_repetition_draw_uses_reconstructed_history():
    history=['g1f3','g8f6','f3g1','f6g8']*2
    state=state_from(*rebuild(history));assert state.terminal and state.result=='1/2-1/2' and state.termination=='threefold_repetition'

@pytest.mark.parametrize('fen,termination',[
    ('7k/5K2/6Q1/8/8/8/8/8 b - - 0 1','stalemate'),
    ('8/8/8/8/8/8/8/K6k w - - 0 1','insufficient_material')])
def test_terminal_position_helper(fen,termination):
    # Fixtures directes du helper, pas entrée FEN exposée par /game.
    state=state_from(chess.Board(fen),[]);assert state.terminal and state.termination==termination

def test_castling_en_passant_and_promotion_are_real_legal_moves():
    scenarios=[(['e2e4','e7e5','g1f3','b8c6','f1c4','g8f6'],'e1g1','O-O'),
        (['e2e4','a7a6','e4e5','d7d5'],'e5d6','exd6'),
        *[(['a2a4','h7h5','a4a5','h5h4','a5a6','h4h3','a6b7','h3g2'],'b7a8'+piece,'bxa8='+piece.upper()) for piece in 'qrbn']]
    for history,move,san in scenarios:
        body=request(history,move);body.mode='study';r=game().turn(body)
        assert r.applied[0].san.startswith(san) and r.state.history[-1]==move

def test_opening_cutoff_not_full_competition_engine():
    history=['e2e4','c7c5','g1f3','d7d6','d2d4','c5d4','f3d4','g8f6','b1c3','a7a6','f1e2','e7e6','e1g1','f8e7','f2f4','e8g8','c1e3','b8c6','d1e1','c8d7','a2a3','a8c8','e1g3','b7b5']
    r=game().turn(request(history));assert r.status=='opening_complete' and not r.applied

def test_busy_and_budget_no_unbounded_fallback():
    gate=Lock();gate.acquire()
    with pytest.raises(GameError,match='BUSY'):game(gate=gate).turn(request(move='e2e4'))
    gate.release()
    times=iter([0.,100.,100.]);service=GameService(None,None,allow_tools=True,clock=lambda:next(times))
    r=service.turn(request(move='e2e4',source='theory_then_engine'))
    assert r.status=='unavailable' and r.state.history==['e2e4']
