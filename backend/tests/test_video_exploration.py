"""J05/I02 : vrai mini-graphe LangGraph, vidéos exclusivement synthétiques."""
from copy import deepcopy
from threading import Lock

import chess
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.video_exploration import ExploreRequest, VideoExploration, VideoExplorationBusy
from app.videos import VideoDiscovery, ControlledVideoQuery, synthetic_transport

HISTORY = ['e2e4', 'c7c5', 'g1f3']
STEPS = ['validate_context', 'plan_intentions', 'search_intentions', 'assemble_response']


def fen(moves):
    b = chess.Board()
    for m in moves:b.push_uci(m)
    return b.fen(en_passant='fen')


def payload(**kwargs):
    return {'action':'explore_videos', 'opening':'sicilienne', 'fen':fen(HISTORY), 'history':HISTORY, **kwargs}


def item(i):
    return {'id':{'kind':'youtube#video','videoId':f'FIXTURE000{i}'},
            'snippet':{'title':f'SYNTHÉTIQUE {i}', 'channelTitle':'Fixture'}}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv('YOUTUBE_MODE','synthetic_fixture')


def call(data=None, handler=synthetic_transport):
    requests=[]
    def transport(request):requests.append(request);return handler(request)
    with TestClient(create_app(video_transport=httpx.MockTransport(transport))) as client:
        response=client.post('/api/v1/videos/explore',json=data or payload())
    return response,requests


def test_three_intentions_real_graph_and_distinct_queries():
    response,requests=call()
    r=response.json()
    assert response.status_code==200 and r['status']=='ok' and r['video_count']==3
    assert r['steps']==STEPS and r['framework']=='langgraph' and r['attempted_searches']==3
    assert [x['intent'] for x in r['intentions']]==['understand_opening','understand_position','deepen_advice']
    assert len({x['video']['video_id'] for x in r['intentions']})==3
    assert len({q.url.params['q'] for q in requests})==3
    assert all(len(q.url.params['q'])<=240 and q.url.params['maxResults']=='3' for q in requests)
    assert r['intentions'][2]['evidence']['advice_provenance']=='rule_based'
    assert all(x['video']['url'] is None and x['video']['thumbnail_url'] is None for x in r['intentions'])
    assert r['synthetic'] and r['source_mode']=='synthetic_fixture' and r['editorial_review']=='not_reviewed'
    assert all('plan' not in x for x in r['intentions'])


def test_only_opening_without_history():
    r,calls=call(payload(history=None));data=r.json()
    assert data['status']=='partial' and data['video_count']==1 and len(calls)==1
    assert [x['status'] for x in data['intentions']]==['ok','skipped','skipped']
    assert data['intentions'][1]['reason']=='HISTORY_REQUIRED'


def test_question_alone_cannot_claim_structured_advice():
    r,calls=call(payload(question='Pourquoi développer ?'))
    assert len(calls)==2 and r.json()['video_count']==2
    assert r.json()['intentions'][2]['reason']=='QUESTION_IS_NOT_STRUCTURED_ADVICE'


@pytest.mark.parametrize('topic',['develop_minor_pieces','king_safety'])
def test_user_selected_topic_is_rule_checked_and_never_agent_assertion(topic):
    r,calls=call(payload(question='Conseil ?',advice_topic=topic))
    assert len(calls)==3 and r.json()['intentions'][2]['evidence']['advice_provenance']=='user_selected'


def test_unsupported_topic_abstains_not_replaced():
    # No black central pawn in d4/e4/d5/e5, black to move.
    r,calls=call(payload(advice_topic='central_control'))
    assert len(calls)==2 and r.json()['intentions'][2]['reason']=='ADVICE_NOT_SUPPORTED_BY_POSITION'


def test_central_control_rule_positive_for_white():
    history=['e2e4','c7c5']
    r,calls=call(payload(history=history,fen=fen(history),advice_topic='central_control'))
    assert len(calls)==3 and r.json()['intentions'][2]['evidence']['rule']=='central_control'


@pytest.mark.parametrize('changes',[
    {'action':'automatic'}, {'action':None}, {'opening':'finale'}, {'fen':'bad'},
    {'history':['e2e5']}, {'history':['e2e4']}, {'history':['e2e4']*25},
    {'history':['x'*100]}, {'history':['0000']}, {'question':'x'*301},
    {'question':'hello\nworld'}, {'language':'en'}, {'advice_topic':'win_piece'},
    {'advice_provenance':'agent_structured'}, {'trusted':True}, {'q':'arbitrary'},
])
def test_invalid_contract_no_transport(changes):
    def forbidden(request):raise AssertionError('NO_CALL')
    r,requests=call(payload(**changes),forbidden)
    assert r.status_code==422 and not requests
    assert r.json()=={'detail':{'code':'INVALID_VIDEO_REQUEST'}}


def test_action_required():
    data=payload();data.pop('action')
    r,requests=call(data)
    assert r.status_code==422 and not requests


@pytest.mark.parametrize('position,reason',[
    ('7k/6Q1/5K2/8/8/8/8/8 b - - 0 1','TERMINAL_POSITION'),
    ('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 13','OUTSIDE_OPENING_WINDOW'),
])
def test_terminal_or_outside_all_skipped(position,reason):
    r,calls=call(payload(fen=position,history=None))
    assert r.status_code==200 and not calls and r.json()['status']=='empty'
    assert all(x['status']=='skipped' and x['reason']==reason for x in r.json()['intentions'])


def test_unrecognized_or_mismatched_opening_history_cannot_generate_position_theme():
    history=['d2d4','d7d5']
    r,calls=call(payload(history=history,fen=fen(history)))
    assert len(calls)==1 and r.json()['intentions'][1]['reason']=='OPENING_PREFIX_NOT_ESTABLISHED'
    assert not r.json()['intentions'][1]['evidence']['opening_prefix_verified']


def test_global_dedup_chooses_remaining_candidate_stably():
    bodies=[[item(1)],[item(1),item(2)],[item(1),item(2),item(3)]]
    def transport(request):return httpx.Response(200,json={'items':bodies.pop(0)})
    r,calls=call(handler=transport)
    assert len(calls)==3 and [x['video']['video_id'] for x in r.json()['intentions']]==['FIXTURE0001','FIXTURE0002','FIXTURE0003']


def test_all_duplicates_not_filled_or_retried():
    r,calls=call(handler=lambda q:httpx.Response(200,json={'items':[item(1)]}))
    assert len(calls)==3 and r.json()['video_count']==1 and r.json()['status']=='partial'
    assert [x['status'] for x in r.json()['intentions']]==['ok','empty','empty']
    assert r.json()['intentions'][2]['reason']=='GLOBAL_DUPLICATE_CANDIDATES'


def test_partial_provider_failure_keeps_other_intentions():
    count=0
    def transport(q):
        nonlocal count
        count+=1
        return httpx.Response(429) if count==2 else synthetic_transport(q)
    r,calls=call(handler=transport)
    assert len(calls)==3 and r.json()['status']=='partial' and r.json()['video_count']==2
    assert r.json()['intentions'][1]['reason']=='YOUTUBE_RATE_LIMITED'


@pytest.mark.parametrize('response,status,reason',[
    (httpx.Response(200,json={'items':[]}), 'empty','NO_ACCEPTABLE_CANDIDATES'),
    (httpx.Response(500), 'unavailable','YOUTUBE_UPSTREAM_ERROR'),
])
def test_empty_and_unavailable_each_intention(response,status,reason):
    r,calls=call(handler=lambda q:response)
    assert len(calls)==3 and r.json()['status']==status and r.json()['video_count']==0
    assert all(x['status']==status and x['reason']==reason for x in r.json()['intentions'])


def test_disabled_no_mock_invocation(monkeypatch):
    monkeypatch.setenv('YOUTUBE_MODE','disabled')
    def forbidden(q):raise AssertionError('NO_CALL')
    r,calls=call(handler=forbidden)
    assert not calls and r.json()['status']=='disabled' and r.json()['attempted_searches']==0
    assert all(x['status']=='disabled' for x in r.json()['intentions'])


def test_historical_analysis_never_invokes_video_and_preserves_response():
    calls=[]
    def tracked(q):calls.append(q);return synthetic_transport(q)
    with TestClient(create_app(video_transport=httpx.MockTransport(tracked))) as client:
        request={'fen':fen(HISTORY),'include_explorer':False,'include_engine':False}
        before=client.post('/api/v1/analysis/orchestrate',json=request)
        assert not calls
        assert client.post('/api/v1/videos/explore',json=payload()).status_code==200
        assert len(calls)==3
        after=client.post('/api/v1/analysis/orchestrate',json=request)
    assert len(calls)==3
    assert before.status_code==after.status_code==200 and before.json()==after.json()
    assert before.json()['graph']['steps']==['validate_position','assemble_response']
    assert 'videos' not in before.json()


def test_graph_gate_released_and_busy_explicit():
    adapter=VideoDiscovery('synthetic_fixture');gate=Lock();usecase=VideoExploration(adapter,gate=gate)
    gate.acquire()
    with pytest.raises(VideoExplorationBusy):usecase.invoke(ExploreRequest(**payload()))
    gate.release()
    assert usecase.invoke(ExploreRequest(**payload())).video_count==3
    assert not gate.locked();adapter.close()


def test_budget_skips_calls_and_graph_steps_are_real():
    adapter=VideoDiscovery('synthetic_fixture')
    times=iter([0.0,20.0,20.0,20.0])
    usecase=VideoExploration(adapter,clock=lambda:next(times),gate=Lock())
    result=usecase.invoke(ExploreRequest(**payload()))
    assert result.attempted_searches==0 and result.steps==STEPS and result.status=='unavailable'
    assert all(x.reason=='VIDEO_DEADLINE_EXCEEDED' for x in result.intentions)
    adapter.close()


def test_internal_query_refuses_arbitrary_q_and_wrong_plan():
    with pytest.raises(ValidationError):ControlledVideoQuery(opening='sicilienne',intent='understand_opening',q='raw')
    with pytest.raises(ValueError):ControlledVideoQuery(opening='sicilienne',intent='understand_position').render()


def test_legacy_search_query_and_response_unchanged():
    seen=[]
    def transport(q):seen.append(q.url.params['q']);return synthetic_transport(q)
    with TestClient(create_app(video_transport=httpx.MockTransport(transport))) as client:
        a=client.post('/api/v1/videos/search',json={'opening':'sicilienne'}).json()
    assert seen==['défense sicilienne explication ouverture échecs']
    assert [v['video_id'] for v in a['videos']]==['FIXTURE0001','FIXTURE0002','FIXTURE0003']


@pytest.mark.parametrize('opening,moves',[
    ('sicilienne',['e2e4','c7c5']),
    ('francaise',['e2e4','e7e6','d2d4','d7d5']),
    ('caro_kann',['e2e4','c7c6','d2d4','d7d5']),
    ('gambit_dame',['d2d4','d7d5','c2c4']),
    ('espagnole',['e2e4','e7e5','g1f3','b8c6','f1b5']),
    ('italienne',['e2e4','e7e5','g1f3','b8c6','f1c4']),
])
def test_six_explicit_prefixes_are_legal_and_support_limited_rules(opening,moves):
    r,calls=call(payload(opening=opening,history=moves,fen=fen(moves)))
    assert len(calls)==3 and r.json()['intentions'][1]['evidence']['opening_prefix_verified']


def test_no_development_rule_does_not_force_position_or_advice():
    board=chess.Board();history=[]
    for san in 'e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6 Be3 e6 Be2 Be7 O-O O-O f4 Nc6 Qe1 Bd7'.split():
        move=board.parse_san(san);history.append(move.uci());board.push(move)
    r,calls=call(payload(history=history,fen=board.fen(en_passant='fen')))
    assert len(calls)==1
    assert [x['reason'] for x in r.json()['intentions']][1:]==['NO_DEVELOPMENT_RULE','NO_ADMISSIBLE_ADVICE']


def test_king_safety_rule_cannot_claim_uncastled_king_after_castling():
    moves=['e2e4','c7c5','g1f3','d7d6','f1c4','g8f6','e1g1','e7e6']
    r,calls=call(payload(history=moves,fen=fen(moves),advice_topic='king_safety'))
    assert len(calls)==2 and r.json()['intentions'][2]['reason']=='ADVICE_NOT_SUPPORTED_BY_POSITION'
