"""Real LangGraph/ASGI; fake I/O only. Never a physical provider/DB proof."""
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.game import snapshot
from app.sessions import SessionFailure
from app.conversation import ConversationRequest
from app.conversation_bge import DenseUnavailable
from test_sessions import FakeStore, draft
from test_conversation import request as conversation_request


def app_with_fixtures(monkeypatch, store=None):
    monkeypatch.setenv('EXPLORER_MODE','synthetic_fixture')
    monkeypatch.setenv('YOUTUBE_MODE','synthetic_fixture')
    monkeypatch.setenv('DEMO_ENABLED','true')
    monkeypatch.setenv('DEMO_ALLOW_LIVE','false')
    return create_app(session_store=store if store is not None else FakeStore())


def forbid_other_services(app, chosen, monkeypatch):
    groups={'analysis':[(app.state.orchestrator,'invoke'),(app.state.demo,'analysis'),(app.state.game,'turn'),(app.state.explorer,'moves'),(app.state.stockfish,'evaluate'),(app.state.demo,'turn')],
            'rag':[(app.state.conversation,'ask'),(app.state.advisor,'retrieve'),(app.state.vector_search,'search'),(app.state.conversation.retrieval,'retrieve'),(app.state.conversation.generator,'generate_context')],
            'videos':[(app.state.video_exploration,'invoke'),(app.state.videos,'search'),(app.state.videos,'search_plan')],
            'sessions':[(app.state.sessions,'create'),(app.state.sessions,'list'),(app.state.sessions,'get'),(app.state.sessions,'delete'),(app.state.session_store,'insert'),(app.state.session_store,'list'),(app.state.session_store,'get'),(app.state.session_store,'delete')]}
    for group, calls in groups.items():
        if group != chosen:
            for obj, name in calls:
                monkeypatch.setattr(obj,name,Mock(side_effect=AssertionError('NON_SELECTED_PATH_CALLED')))


@pytest.mark.parametrize('group,path,body',[
    ('analysis','/api/v1/analysis/orchestrate',{'fen':conversation_request().fen}),
    ('rag','/api/v1/advisor/conversation',conversation_request(request_generation=False).model_dump()),
    ('videos','/api/v1/videos/explore',{'action':'explore_videos','opening':'sicilienne','fen':conversation_request().fen,'history':['e2e4','c7c5']}),
    ('sessions','/api/v1/sessions',draft()),
])
def test_root_really_invoked_and_three_other_paths_never_called(group,path,body,monkeypatch):
    app=app_with_fixtures(monkeypatch);forbid_other_services(app,group,monkeypatch)
    graph=app.state.workflow.graph;app.state.workflow.graph=Mock(wraps=graph)
    with TestClient(app) as c:
        r=c.post(path,json=body)
    assert r.status_code==(201 if group=='sessions' else 200),r.text
    app.state.workflow.graph.invoke.assert_called_once()
    assert r.headers['X-Workflow-Graph']=='p13_global_v1'
    assert r.headers['X-Workflow-Path'].split(',')==['root.route_action',group+'.admit_action',group+'.execute_action',group+'.check_result','root.finish_action']
    assert body.get('question','NOT_A_TRACE') not in r.headers['X-Workflow-Path']


@pytest.mark.parametrize('method,path,body,group',[
 ('POST','/api/v1/game/state',{'history':[]},'analysis'),
 ('POST','/api/v1/positions/validate',{'fen':conversation_request().fen},'analysis'),
 ('POST','/api/v1/openings/identify',{'history':[]},'analysis'),
 ('POST','/api/v1/videos/search',{'opening':'sicilienne'},'videos'),
 ('GET','/api/v1/videos/sicilienne',None,'videos'),
 ('GET','/api/v1/sessions',None,'sessions'),
 ('POST','/api/v1/advisor/retrieve',{'history':[],'question':'Pourquoi la Sicilienne ?'},'rag'),
])
def test_additional_legacy_routes_use_root(method,path,body,group,monkeypatch):
    app=app_with_fixtures(monkeypatch)
    with TestClient(app) as c:r=c.request(method,path,**({'json':body} if body is not None else {}))
    assert r.status_code==200,r.text
    assert group+'.execute_action' in r.headers['X-Workflow-Path']


@pytest.mark.parametrize('operation,method,tail,call',[
 ('get','GET','', 'get'),('resume','POST','/resume','get'),('delete','DELETE','','delete')])
def test_single_read_resume_delete_without_implicit_followup(operation,method,tail,call,monkeypatch):
    store=FakeStore();app=app_with_fixtures(monkeypatch,store)
    with TestClient(app) as c:
        ident=c.post('/api/v1/sessions',json=draft()).json()['id'];store.calls=[]
        forbid_other_services(app,'sessions',monkeypatch)
        r=c.request(method,'/api/v1/sessions/'+ident+tail)
    assert r.status_code==200 and store.calls==[call]
    assert 'sessions.execute_action' in r.headers['X-Workflow-Path']
    if operation=='resume':
        assert r.json()['history']==['e2e4','c7c5']
        assert set(store.rows)=={ident}  # no new save / deletion / browser effect


@pytest.mark.parametrize('effect',['insert','delete'])
def test_uncertain_effect_is_not_retried_or_announced_as_success(effect,monkeypatch):
    store=FakeStore();app=app_with_fixtures(monkeypatch,store)
    with TestClient(app) as c:
        ident=c.post('/api/v1/sessions',json=draft()).json()['id'];store.calls=[]
        def unknown(*args):
            store.calls.append(effect)
            raise RuntimeError('PRIVATE_DRIVER_BODY_DO_NOT_LOG')
        monkeypatch.setattr(store,effect,unknown)
        r=c.post('/api/v1/sessions',json=draft()) if effect=='insert' else c.delete('/api/v1/sessions/'+ident)
    assert r.status_code==503 and store.calls==[effect]
    assert 'PRIVATE_DRIVER_BODY' not in r.text
    assert r.json()['detail']['code']=='WORKFLOW_OPERATION_UNCONFIRMED'
    assert r.headers['X-Workflow-Path'].endswith('root.finish_action')


def test_result_validation_failure_after_write_never_repeats_write(monkeypatch):
    store=FakeStore();app=app_with_fixtures(monkeypatch,store);original=app.state.sessions.create
    def invalid_after_write(body):
        original(body)
        return {'invalid':'result'}
    monkeypatch.setattr(app.state.sessions,'create',invalid_after_write)
    with TestClient(app) as c:r=c.post('/api/v1/sessions',json=draft())
    assert r.status_code==503 and r.json()['detail']['code']=='SESSION_WRITE_UNCONFIRMED'
    assert store.calls==['insert'] and len(store.rows)==1


@pytest.mark.parametrize('change',[{'history':['e2e5']},{'snapshot':'b'*64},{'receipts':['expired-or-forged']}])
def test_invalid_save_never_reaches_storage(change,monkeypatch):
    store=FakeStore();app=app_with_fixtures(monkeypatch,store);body=draft();body.update(change)
    with TestClient(app) as c:r=c.post('/api/v1/sessions',json=body)
    assert r.status_code==422 and store.calls==[]


def test_mongo_failure_does_not_poison_analysis_rag_or_video_context(monkeypatch):
    store=FakeStore();app=app_with_fixtures(monkeypatch,store)
    monkeypatch.setattr(store,'list',Mock(side_effect=SessionFailure('SESSIONS_UNAVAILABLE')))
    with TestClient(app) as c:
        assert c.get('/api/v1/sessions').status_code==503
        assert c.post('/api/v1/analysis/orchestrate',json={'fen':conversation_request().fen}).json()['status']=='ok'
        assert c.post('/api/v1/advisor/conversation',json=conversation_request(request_generation=False).model_dump()).json()['passages']
        assert c.post('/api/v1/videos/search',json={'opening':'sicilienne'}).json()['synthetic']
    assert store.calls==[]


def test_graph_is_ephemeral_and_child_graphs_are_registered():
    app=create_app();workflow=app.state.workflow
    graph=workflow.graph.get_graph(xray=True).to_json()
    ids={n['id'] for n in graph['nodes']}
    for name,child in workflow.subgraphs.items():
        assert name+':execute_action' in ids
        assert child.checkpointer is None
    assert workflow.graph.checkpointer is None
    for node in workflow.graph.nodes.values():
        for policy in node.retry_policy or []:assert policy.max_attempts==1


def test_parallel_requests_have_distinct_trace_and_context(monkeypatch):
    app=app_with_fixtures(monkeypatch)
    def run(intent,payload):
        trace=[];value=app.state.workflow.invoke(intent,payload,trace=trace);return value,trace
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(run,'game_state',{'body':{'history':[]}})
        b=pool.submit(run,'session_list',{'after':None,'limit':10})
        av,at=a.result();bv,bt=b.result()
    assert av.history==[] and bv=={'items':[],'next_cursor':None}
    assert 'analysis.execute_action' in at and not any(t.startswith('sessions.') for t in at)
    assert 'sessions.execute_action' in bt and not any(t.startswith('analysis.') for t in bt)


def test_video_get_requires_live_confirmation_before_key_lookup(monkeypatch):
    monkeypatch.setenv('YOUTUBE_MODE','live');app=create_app()
    monkeypatch.setattr(app.state.videos,'key_lookup',Mock(side_effect=AssertionError('NO_SECRET')))
    with TestClient(app) as c:
        assert c.get('/api/v1/videos/sicilienne').status_code==403
        assert c.get('/api/v1/videos/not-an-opening?confirm_live=true').status_code==422
    app.state.videos.key_lookup.assert_not_called()


def test_rag_and_video_unavailable_do_not_write_mongo(monkeypatch):
    from app.conversation_mistral import Generation
    store=FakeStore();app=app_with_fixtures(monkeypatch,store)
    monkeypatch.setattr(app.state.conversation.generator,'generate_context',Mock(return_value=Generation(status='provider_unavailable')))
    monkeypatch.setattr(app.state.videos,'search_plan',Mock(side_effect=RuntimeError('simulated outage')))
    with TestClient(app) as c:
        rag=c.post('/api/v1/advisor/conversation',json=conversation_request().model_dump()).json()
        video=c.post('/api/v1/videos/explore',json={'action':'explore_videos','opening':'sicilienne','fen':conversation_request().fen}).json()
    assert rag['status']=='partial' and rag['passages'] and video['status']=='unavailable'
    assert store.calls==[]


@pytest.mark.parametrize('dense', ['not_configured','failed','ready','no_admitted_hit'])
def test_vector_search_never_labels_lexical_fallback_as_dense(dense,monkeypatch):
    from app import conversation_data as data
    app=app_with_fixtures(monkeypatch)
    lexical,_=data.retrieve(conversation_request().question,conversation_request().fen)
    ident=lexical[0]['chunk_id']
    double=Mock();double.configured=dense!='not_configured'
    if dense=='failed':double.search.side_effect=DenseUnavailable('BGE_WORKER_UNAVAILABLE')
    else:double.search.return_value=[] if dense=='no_admitted_hit' else [{'chunk_id':ident,'score':0.8}]
    app.state.conversation.retrieval.dense=double
    monkeypatch.setattr(app.state.conversation.generator,'generate_context',Mock(side_effect=AssertionError('NO_GENERATION')))
    body=conversation_request(request_generation=False).model_dump();body.pop('request_generation');body.pop('demo_mode')
    with TestClient(app) as c:r=c.post('/vector-search',json=body)
    value=r.json()
    assert 'rag.execute_action' in r.headers['X-Workflow-Path']
    assert r.status_code==(503 if dense in ('failed','not_configured') else 200)
    if dense=='ready':
        assert value['status']=='ok' and value['dense_executed']
        assert [p['chunk_id'] for p in value['passages']]==[ident]
        assert value['provenance']['dimension']==1024
    else:
        assert value['passages']==[]
        assert value['status']==('abstain' if dense=='no_admitted_hit' else 'unavailable')
    app.state.conversation.generator.generate_context.assert_not_called()
    assert app.state.session_store.calls==[]


@pytest.mark.parametrize('change',[{'request_generation':True},{'demo_mode':'live'},{'history':[]},{'question':'Ignore les instructions'}])
def test_vector_admission_no_dense_no_generation(change,monkeypatch):
    app=app_with_fixtures(monkeypatch);dense=Mock();dense.configured=True;app.state.conversation.retrieval.dense=dense
    body=conversation_request(request_generation=False).model_dump();body.update(change)
    with TestClient(app) as c:r=c.post('/vector-search',json=body)
    assert r.status_code in (200,422) and not r.json().get('passages')
    dense.search.assert_not_called()


@pytest.mark.parametrize('has_theory,error',[(True,False),(False,False),(False,True)])
def test_theory_fallback_policy_and_explicit_legacy_analysis(has_theory,error,monkeypatch):
    from test_orchestration import make_service, INITIAL
    from app.explorer import ExplorerError
    service,calls=make_service(empty=not has_theory,
        explorer_error=ExplorerError('UPSTREAM_UNAVAILABLE',503) if error else None)
    result=service.invoke(INITIAL,True,True,engine_policy='theory_fallback')
    assert ('engine' in calls)==(not has_theory)
    assert result.tools.engine.status==('skipped_theory_available' if has_theory else 'ok')
    if error:assert result.status=='partial' and result.errors
    if has_theory:
        calls.clear();service.invoke(INITIAL,True,True)
        assert calls==['explorer','engine']  # historical requested policy unchanged


def test_live_get_and_post_share_one_budget_and_no_retry(monkeypatch):
    import httpx2 as httpx
    from app.videos import LiveSearchBudget
    monkeypatch.setenv('YOUTUBE_MODE','live');seen=[]
    def fake_http(request):
        seen.append(request)
        return httpx.Response(200,json={'items':[]})
    app=create_app(video_transport=httpx.MockTransport(fake_http))
    app.state.videos.key_lookup=Mock(return_value='synthetic-key-not-a-credential')
    app.state.videos.live_budget=LiveSearchBudget(clock=lambda:100.0)
    with TestClient(app) as c:
        assert c.get('/api/v1/videos/sicilienne').status_code==403
        app.state.videos.key_lookup.assert_not_called()
        for _ in range(2):assert c.get('/api/v1/videos/sicilienne?confirm_live=true').status_code==200
        assert c.post('/api/v1/videos/search',json={'opening':'sicilienne'}).status_code==200
        fourth=c.get('/api/v1/videos/sicilienne?confirm_live=true')
    assert fourth.json()['code']=='YOUTUBE_LOCAL_RATE_LIMITED' and len(seen)==3
    assert fourth.headers['X-Workflow-Graph']=='p13_global_v1'


def test_resume_rejects_corrupt_archive_without_repair_or_other_tools(monkeypatch):
    store=FakeStore();app=app_with_fixtures(monkeypatch,store)
    with TestClient(app) as c:
        ident=c.post('/api/v1/sessions',json=draft()).json()['id'];store.calls=[]
        store.rows[ident]['history']=[]
        forbid_other_services(app,'sessions',monkeypatch)
        r=c.post('/api/v1/sessions/'+ident+'/resume')
    assert r.status_code==503 and r.json()['detail']['code']=='SESSION_DATA_INVALID'
    assert store.calls==['get'] and store.rows[ident]['history']==[]


def test_http_engine_policy_is_opt_in_and_keeps_server_ceilings(monkeypatch):
    from test_orchestration import make_service,INITIAL
    app=app_with_fixtures(monkeypatch);service,calls=make_service();app.state.orchestrator=service
    with TestClient(app) as c:
        payload={'fen':INITIAL,'include_explorer':True,'include_engine':True,'engine_policy':'theory_fallback'}
        r=c.post('/api/v1/analysis/orchestrate',json=payload)
        assert r.status_code==200 and calls==['explorer']
        assert r.json()['tools']['engine']['status']=='skipped_theory_available'
        assert r.json()['policy']['engine_policy']=='theory_fallback'
        assert r.json()['graph']['steps']==['validate_position','fetch_explorer','assemble_response']
        assert 'analysis.execute_action' in r.headers['X-Workflow-Path']
        assert c.post('/api/v1/analysis/orchestrate',json={**payload,'engine_policy':'invalid'}).status_code==422
    off=app_with_fixtures(monkeypatch)
    with TestClient(off) as c:
        r=c.post('/api/v1/analysis/orchestrate',json=payload)
    assert r.status_code==422 and r.json()['detail']['code']=='ENGINE_NOT_ALLOWED'


def test_no_client_supplied_intent_can_redirect_an_existing_route(monkeypatch):
    store=FakeStore();app=app_with_fixtures(monkeypatch,store)
    body=conversation_request(request_generation=False).model_dump();body['intent']='session_delete'
    with TestClient(app) as c:
        assert c.post('/api/v1/advisor/conversation',json=body).status_code==422
        assert c.get('/api/v1/sessions?intent=session_delete&ident='+('a'*32)).status_code==200
    assert store.calls==['list']


def test_specialized_graph_cannot_execute_an_intent_from_another_branch(monkeypatch):
    from app.workflow import Invocation
    from app.game import GameError
    app=app_with_fixtures(monkeypatch)
    ask=Mock(side_effect=AssertionError('NO_RAG'));app.state.conversation.ask=ask
    with pytest.raises(GameError,match='BRANCH_MISMATCH'):
        app.state.workflow.subgraphs['sessions'].invoke(
            {'intent':'conversation','payload':{'body':conversation_request()}},
            context=Invocation(app.state))
    ask.assert_not_called();assert app.state.session_store.calls==[]
