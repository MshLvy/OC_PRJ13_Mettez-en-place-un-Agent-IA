"""Mongo CRUD and receipts: explicit actions, fake storage, no provider/DB calls."""
from copy import deepcopy
from unittest.mock import Mock
import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.sessions import MongoStore,Receipts,SessionDraft,SessionService,SessionFailure
from app.conversation import ConversationService
from app.conversation_mistral import Generation,Output
from test_conversation import request

class FakeStore:
    def __init__(self,rows=None):self.rows={} if rows is None else rows;self.calls=[]
    def status(self):return 'test_double_not_persistent'
    def insert(self,d):self.calls.append('insert');self.rows[d['_id']]=deepcopy(d)
    def get(self,i):self.calls.append('get');return deepcopy(self.rows.get(i))
    def list(self,after,limit):
        self.calls.append('list');return [deepcopy(v) for k,v in sorted(self.rows.items()) if not after or k>after][:limit]
    def delete(self,i):self.calls.append('delete');return self.rows.pop(i,None) is not None
    def close(self):pass

def draft(**kw):
    b=request(request_generation=False)
    return dict(opening='sicilienne',fen=b.fen,history=b.history,snapshot=b.snapshot,**kw)

def generation():
    body=request(request_generation=False);r=ConversationService().ask(body)
    body.request_generation=True
    r.status='answered';r.generation=Generation(status='generated',provider='groq_api',engine='Groq',model='openai/gpt-oss-120b',actual_model='openai/gpt-oss-120b',executed=True,answer=Output(scope='position',paragraphs=[{'text':'Le pion c5 contrôle d4.','citation_ids':[r.passages[0].chunk_id]}],moves_uci=[]))
    return body,r

def test_crud_fake_storage_and_pagination_no_memory_production_fallback():
    fake=FakeStore()
    with TestClient(create_app(session_store=fake)) as c:
        a=c.post('/api/v1/sessions',json=draft());assert a.status_code==201
        ident=a.json()['id'];assert len(ident)==32 and a.json()['schema_version']==1
        assert a.json()['exchanges']==[]
        assert c.get('/api/v1/sessions/'+ident).json()==a.json()
        assert c.get('/api/v1/sessions?limit=1').json()['items'][0]['id']==ident
        b=c.post('/api/v1/sessions',json=draft()).json()
        first=c.get('/api/v1/sessions?limit=1').json();second=c.get('/api/v1/sessions?limit=1&after='+first['next_cursor']).json()
        assert len(second['items'])==1 and first['items'][0]['id']!=second['items'][0]['id']
        assert c.delete('/api/v1/sessions/'+ident).json()=={'status':'deleted','id':ident}
        assert c.get('/api/v1/sessions/'+ident).status_code==404
        assert c.delete('/api/v1/sessions/'+ident).status_code==404
    assert ident not in fake.rows

@pytest.mark.parametrize('change',[{'fen':'bad'},{'history':['e2e5']},{'history':[]},{'snapshot':'b'*64},{'opening':'other'},{'answer':{'text':'arbitrary'}},{'mongo_uri':'mongodb://evil'},{'receipts':['bad']},{'receipts':['x'*32769]},{'receipts':['x']*6}])
def test_invalid_and_arbitrary_writes_blocked_without_storage(change):
    fake=FakeStore();data=draft();data.update(change)
    with TestClient(create_app(session_store=fake)) as c:
        response=c.post('/api/v1/sessions',json=data)
    assert response.status_code==422 and not fake.calls
    assert 'mongodb://evil' not in response.text


def test_receipt_verified_signature_snapshot_family_expiry_and_no_corpus_text_saved():
    now=[100.0];receipt=Receipts(clock=lambda:now[0]);body,r=generation();token=receipt.issue(body,r);assert token
    store=FakeStore();service=SessionService(store,receipt)
    saved=service.create(SessionDraft(**draft(receipts=[token])))
    assert saved.exchanges[0].answer.paragraphs[0].text=='Le pion c5 contrôle d4.'
    serialized=json.dumps(next(iter(store.rows.values())))
    assert r.passages[0].text not in serialized and token not in serialized and 'prompt' not in serialized and 'reasoning' not in serialized
    for bad in (token[:-1]+('0' if token[-1]!='0' else '1'),'bad'):
        with pytest.raises(SessionFailure,match='RECEIPT'):service.create(SessionDraft(**draft(receipts=[bad])))
    modified=draft(receipts=[token]);modified['opening']='francaise'
    with pytest.raises(SessionFailure,match='RECEIPT'):service.create(SessionDraft(**modified))
    initial=request([],request_generation=False)
    changed=SessionDraft(opening='sicilienne',fen=initial.fen,history=[],snapshot=initial.snapshot,receipts=[token])
    with pytest.raises(SessionFailure,match='RECEIPT'):service.create(changed)
    now[0]=1001
    with pytest.raises(SessionFailure,match='RECEIPT'):service.create(SessionDraft(**draft(receipts=[token])))
    assert store.calls==['insert']

@pytest.mark.parametrize('status',['generation_disabled','provider_unavailable','abstain','test_double','deterministic'])
def test_unapproved_or_test_answer_never_receipted(status):
    body,r=generation();r.generation.status=status
    assert Receipts().issue(body,r) is None


def test_secret_like_text_not_receipted_and_no_real_key_lookup():
    body,r=generation();body.question='GROQ_API_KEY=PRIVATE_VALUE'
    assert Receipts().issue(body,r) is None
    body,r=generation();body.question='A'*40
    assert Receipts().issue(body,r) is None
    body,r=generation();r.generation.test_transport=True
    assert Receipts().issue(body,r) is None


def test_disabled_and_unavailable_crud_do_not_break_game_conversation_or_video():
    for store,code in [(MongoStore(enabled='false'),'SESSIONS_DISABLED'),(MongoStore(enabled='true',password_lookup=lambda:''),'SESSIONS_UNAVAILABLE')]:
        with TestClient(create_app(session_store=store)) as c:
            assert c.post('/api/v1/sessions',json=draft()).json()['detail']['code']==code
            assert c.get('/api/v1/sessions').json()['detail']['code']==code
            assert c.get('/api/v1/healthcheck').status_code==200
            assert c.post('/api/v1/game/state',json={'history':[]}).status_code==200
            assert c.post('/api/v1/videos/search',json={'opening':'sicilienne'}).json()['status']=='disabled'
            assert c.post('/api/v1/advisor/conversation',json=request(request_generation=False).model_dump()).status_code==200


def test_status_and_startup_do_not_read_mongo_password_or_connect():
    password=Mock(side_effect=AssertionError('NO_SECRET'));factory=Mock(side_effect=AssertionError('NO_CONNECTION'))
    store=MongoStore(enabled='true',password_lookup=password,client_factory=factory)
    with TestClient(create_app(session_store=store)) as c:
        assert c.get('/api/v1/sessions/status').json()['status']=='configured_not_probed'
        assert c.get('/api/v1/healthcheck').status_code==200
    password.assert_not_called();factory.assert_not_called()


def test_generation_route_receipt_does_not_write_or_query_mongo():
    fake=FakeStore();app=create_app(session_store=fake);body,result=generation()
    app.state.conversation.ask=Mock(return_value=result)
    with TestClient(app) as c:
        r=c.post('/api/v1/advisor/conversation',json=body.model_dump())
        assert r.json()['session_receipt'] and fake.calls==[]
        saved=c.post('/api/v1/sessions',json=draft(receipts=[r.json()['session_receipt']]))
        assert saved.status_code==201 and len(saved.json()['exchanges'])==1
    assert fake.calls==['insert']

@pytest.mark.parametrize('path',['?limit=0','?limit=21','?after=bad','/bad'])
def test_invalid_list_or_id_sanitized(path):
    fake=FakeStore()
    with TestClient(create_app(session_store=fake)) as c:r=c.get('/api/v1/sessions'+path)
    assert r.status_code==422 and not fake.calls


def test_driver_configuration_real_sdk_constructed_without_connection():
    # Actual installed PyMongo parser exercised, connect=False. No Mongo server.
    store=MongoStore(enabled='true',password_lookup=lambda:'a'*64)
    try:
        collection=store.collection();assert collection.name=='sessions'
        assert collection.write_concern.document=={'j':True,'w':1}
        assert store.client.options.retry_reads is False and store.client.options.retry_writes is False
        assert store.client.options.pool_options.max_pool_size==2
        assert store.client.options.server_selection_timeout==0.7
    finally:store.close()


def test_driver_error_redaction_and_acknowledgement_guards():
    collection=Mock();client=Mock();client.__getitem__=Mock(return_value={'sessions':collection})
    factory=Mock(return_value=client);store=MongoStore(enabled='true',password_lookup=lambda:'a'*64,client_factory=factory)
    collection.insert_one.side_effect=TimeoutError('PRIVATE_PASSWORD_a'*10)
    with pytest.raises(SessionFailure,match='^SESSIONS_UNAVAILABLE$'):store.insert({'_id':'b'*32})
    collection.insert_one.side_effect=None;collection.insert_one.return_value.acknowledged=False
    with pytest.raises(SessionFailure,match='WRITE_UNCONFIRMED'):store.insert({'_id':'b'*32})
    collection.delete_one.return_value.acknowledged=False
    with pytest.raises(SessionFailure,match='DELETE_UNCONFIRMED'):store.delete('b'*32)
    assert factory.call_count==1


def test_application_restart_fake_storage_only_and_receipt_key_rotation():
    # Shared fake dictionary is NOT physical persistence proof.
    rows={}
    with TestClient(create_app(session_store=FakeStore(rows))) as c:saved=c.post('/api/v1/sessions',json=draft()).json()
    with TestClient(create_app(session_store=FakeStore(rows))) as c:assert c.get('/api/v1/sessions/'+saved['id']).status_code==200
    body,r=generation();token=Receipts().issue(body,r)
    with pytest.raises(SessionFailure):Receipts().read(token,SessionDraft(**draft()))


def test_document_utf8_size_limit_fails_before_storage():
    signer=Receipts();body,r=generation();receipts=[]
    for i in range(5):
        body.question='Pourquoi c5 ? '+str(i)
        r.generation.answer=Output(scope='position',paragraphs=[{'text':'😀'*1600,'citation_ids':[r.passages[0].chunk_id]}]*3,moves_uci=[])
        token=signer.issue(body,r);assert token;receipts.append(token)
    store=FakeStore()
    with pytest.raises(SessionFailure,match='SESSION_TOO_LARGE'):SessionService(store,signer).create(SessionDraft(**draft(receipts=receipts)))
    assert not store.calls


def test_corrupted_database_record_is_not_returned():
    store=FakeStore();service=SessionService(store,Receipts());saved=service.create(SessionDraft(**draft()))
    store.rows[saved.id]['history']=['e2e5']
    with pytest.raises(SessionFailure,match='SESSION_DATA_INVALID'):service.get(saved.id)


def test_unrequested_generation_receipt_and_invalid_config_fail_closed():
    body,r=generation();body.request_generation=False
    assert Receipts().issue(body,r) is None
    password=Mock(side_effect=AssertionError('NO_SECRET'));store=MongoStore(enabled='invalid',password_lookup=password)
    assert store.status()=='unavailable'
    with pytest.raises(SessionFailure,match='MONGO_CONFIGURATION_INVALID'):store.get('a'*32)
    password.assert_not_called()
