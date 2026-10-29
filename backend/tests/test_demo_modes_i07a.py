"""Independent capabilities; all providers and engines below are test doubles."""
from unittest.mock import Mock
import chess
from fastapi.testclient import TestClient
from app.main import create_app
from app.demo import DemoService
from app.conversation import ConversationRequest
from app.game import snapshot,rebuild
from test_demo_modes import setup,body,turn_request,fake_engine

def test_live_mode_authorized_with_both_resources_absent_no_invocations(monkeypatch):
    monkeypatch.setenv('DEMO_ENABLED','true');monkeypatch.setenv('DEMO_ALLOW_LIVE','true')
    monkeypatch.setenv('GAME_ALLOW_TOOLS','false')
    app=create_app();app.state.stockfish.evaluate=Mock(side_effect=AssertionError('NO_ENGINE'))
    app.state.demo.live_explorer.moves=Mock(side_effect=AssertionError('NO_PROVIDER'))
    with TestClient(app,client=('127.0.0.1',5)) as client:
        assert client.get('/api/v1/demo/capabilities').json()['allowed_modes']==['simulation','live']
        r=client.post('/api/v1/demo/analysis',json=body(mode='live')).json()['data']
        assert r['status']=='partial' and r['tools']['explorer']['status']==r['tools']['engine']['status']=='disabled'
        assert all(not x['attempted'] for x in r['provenance'] if x['tool']!='position')
        t=client.post('/api/v1/demo/turn',json=turn_request(mode='live')).json()['data']
        assert t['status']=='unavailable' and t['state']['history']==['e2e4'] and not t['choice']['synthetic']
    app.state.stockfish.evaluate.assert_not_called();app.state.demo.live_explorer.moves.assert_not_called()

def test_live_analysis_engine_only_still_works_without_explorer_or_game(monkeypatch):
    monkeypatch.setenv('DEMO_ENABLED','true');monkeypatch.setenv('DEMO_ALLOW_LIVE','true');monkeypatch.setenv('STOCKFISH_ENABLED','true');monkeypatch.setenv('GAME_ALLOW_TOOLS','false')
    app=create_app(stockfish_runner=fake_engine)
    app.state.demo.live_explorer.moves=Mock(side_effect=AssertionError('NO_PROVIDER'))
    with TestClient(app,client=('127.0.0.1',5)) as client:
        d=client.post('/api/v1/demo/analysis',json=body(mode='live')).json()['data']
        assert d['tools']['engine']['status']=='ok' and d['tools']['engine']['result']['source_mode']=='local_engine'
        assert d['tools']['explorer']['status']=='disabled' and 'fetch_explorer' not in d['graph']['steps']
    app.state.demo.live_explorer.moves.assert_not_called()

def test_simulation_unknown_move_is_unavailable_no_arbitrary_legal_reply(monkeypatch):
    app,client=setup(monkeypatch)
    with client:
        r=client.post('/api/v1/demo/turn',json=turn_request(move='a2a3')).json()['data']
        assert r['status']=='unavailable' and r['state']['history']==['a2a3']
        assert r['errors']==['SIMULATION_NO_POSITION_DATA'] and r['choice']['source']=='none'

def test_simulation_can_request_local_stockfish_separately_without_network(monkeypatch):
    app,client=setup(monkeypatch);monkeypatch.setenv('STOCKFISH_ENABLED','true')
    app=create_app(stockfish_runner=fake_engine)
    app.state.demo.live_explorer.moves=Mock(side_effect=AssertionError('NO_PROVIDER'))
    with TestClient(app,client=('127.0.0.1',5)) as client:
        auto=client.post('/api/v1/demo/analysis',json=body()).json()['data']
        assert auto['tools']['engine']['result']['source_mode']=='synthetic_fixture'
        r=client.post('/api/v1/analysis/orchestrate',json={'fen':chess.STARTING_FEN,'explorer_mode':'disabled','include_engine':True})
        assert r.status_code==200 and r.json()['tools']['engine']['result']['source_mode']=='local_engine'
        assert r.json()['tools']['explorer']['status']=='not_requested'
    app.state.demo.live_explorer.moves.assert_not_called()

def test_rag_remains_usable_with_demo_disabled_or_live_unavailable(monkeypatch):
    monkeypatch.setenv('DEMO_ENABLED','false');monkeypatch.setenv('DEMO_ALLOW_LIVE','false')
    app=create_app();h=['e2e4','c7c5'];b,_=rebuild(h)
    with TestClient(app) as client:
        for mode in ('simulation','live'):
            r=client.post('/api/v1/advisor/conversation',json={'demo_mode':mode,'history':h,'fen':b.fen(en_passant='fen'),'snapshot':snapshot(h),'question':'Pourquoi le pion c5 contrôle d4 dans la Sicilienne ?','request_generation':True})
            assert r.status_code==200 and r.json()['passages'] and r.json()['generation']['status']==('deterministic' if mode=='simulation' else 'provider_unavailable') and r.json()['dense_status']=='integration_pending'
