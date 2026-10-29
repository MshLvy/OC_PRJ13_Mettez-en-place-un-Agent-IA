"""Real adapter path with HTTPX doubles only, no actual API credentials."""
import json
from threading import Lock
from unittest.mock import Mock
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.videos import VideoDiscovery,VideoRequest,LiveSearchBudget,ENDPOINT
from test_video_exploration import payload,item,HISTORY,STEPS,fen

KEY='SYNTHETIC_YOUTUBE_API_KEY'
@pytest.fixture(autouse=True)
def live(monkeypatch):
    monkeypatch.setenv('YOUTUBE_MODE','live')
    monkeypatch.setattr('app.videos.youtube_key',lambda:KEY)
    monkeypatch.setattr('app.videos._LIVE_BUDGET',LiveSearchBudget())

def call(data=None,handler=None):
    calls=[]
    def handle(req):
        calls.append(req)
        assert req.method=='GET' and str(req.url).split('?')[0]==ENDPOINT
        assert req.headers['x-goog-api-key']==KEY and 'key' not in req.url.params
        assert KEY not in str(req.url) and 'fen' not in req.url.params
        assert req.url.params['type']=='video' and req.url.params['safeSearch']=='strict'
        assert req.url.params['relevanceLanguage']=='fr' and req.url.params['maxResults']=='3'
        return handler(req,len(calls)) if handler else httpx.Response(200,json={'items':[item(len(calls))]})
    with TestClient(create_app(video_transport=httpx.MockTransport(handle))) as client:
        result=client.post('/api/v1/videos/explore',json=data or payload())
    return result,calls

@pytest.mark.parametrize('change,count', [({'history':None},1),({'question':'Question libre non transférée'},2),({},3)])
def test_live_one_two_three_intentions_real_graph_but_double_label(change,count):
    r,calls=call(payload(**change));body=r.json()
    assert r.status_code==200 and len(calls)==body['video_count']==count
    assert body['source_mode']=='live' and not body['synthetic'] and body['test_transport']
    assert body['steps']==STEPS and body['editorial_review']=='not_reviewed'
    assert body['deadline_mode']=='cooperative_between_live_calls'
    for row in body['intentions']:
        if row['video']:
            assert row['reason']=='LIVE_CANDIDATE_SELECTED'
            assert row['video']['url']=='https://www.youtube.com/watch?v='+row['video']['video_id']
    assert not any('Question libre' in c.url.params['q'] or payload()['fen'] in c.url.params['q'] for c in calls)

@pytest.mark.parametrize('status,error,code',[(401,{},'YOUTUBE_AUTHORIZATION_FAILED'),(403,{},'YOUTUBE_AUTHORIZATION_FAILED'),(403,{'error':{'errors':[{'reason':'quotaExceeded'}]}},'YOUTUBE_QUOTA_EXCEEDED'),(429,{},'YOUTUBE_RATE_LIMITED')])
def test_auth_quota_rate_failure_halts_remaining_searches_no_retry(status,error,code):
    r,calls=call(handler=lambda req,n:httpx.Response(status,json=error))
    assert len(calls)==1 and r.json()['status']=='unavailable'
    assert all(row['reason']==code for row in r.json()['intentions'])

@pytest.mark.parametrize('kind,code',[('timeout','YOUTUBE_TIMEOUT'),('transport','YOUTUBE_TRANSPORT_ERROR'),('server','YOUTUBE_UPSTREAM_ERROR'),('redirect','YOUTUBE_UPSTREAM_ERROR'),('json','YOUTUBE_INVALID_RESPONSE')])
def test_errors_are_explicit_and_sanitized(kind,code):
    def handle(req,n):
        if kind=='timeout':raise httpx.ReadTimeout('PRIVATE_'+KEY)
        if kind=='transport':raise httpx.ConnectError('PRIVATE_'+KEY)
        if kind=='json':return httpx.Response(200,content=b'PRIVATE_INVALID_JSON')
        return httpx.Response(302 if kind=='redirect' else 500,headers={'Location':'https://evil.example'},json={'error':KEY})
    r,calls=call(payload(history=None),handle)
    assert len(calls)==1 and r.json()['intentions'][0]['reason']==code
    assert KEY not in r.text and 'PRIVATE_' not in r.text and 'evil.example' not in r.text

@pytest.mark.parametrize('key',['',None,'bad key','short'])
def test_key_missing_invalid_no_http(monkeypatch,key):
    lookup=Mock(return_value=key);monkeypatch.setattr('app.videos.youtube_key',lookup)
    r,calls=call()
    assert not calls and lookup.call_count==1 and r.json()['intentions'][0]['reason']=='YOUTUBE_KEY_UNAVAILABLE'


def test_no_secret_or_search_at_construction_health_or_disabled(monkeypatch):
    key=Mock(side_effect=AssertionError('NO_KEY'));monkeypatch.setattr('app.videos.youtube_key',key)
    calls=[]
    with TestClient(create_app(video_transport=httpx.MockTransport(lambda req:calls.append(req)))) as client:
        assert client.get('/api/v1/healthcheck').status_code==200
    key.assert_not_called();assert not calls
    for mode in ('disabled','synthetic_fixture'):
        adapter=VideoDiscovery(mode,key_lookup=key)
        adapter.search(VideoRequest(opening='sicilienne'));adapter.close()
    key.assert_not_called()


def test_metadata_filters_xss_wrong_urls_and_stable_global_dedup():
    bad=item(1);bad['snippet']['title']='&lt;script&gt;BAD&lt;/script&gt;'
    wrong=item(2);wrong['snippet']['thumbnails']={'default':{'url':'https://evil.example/x.jpg'}}
    def handle(req,n):return httpx.Response(200,json={'items':[bad,wrong,item(3),item(4),item(5)]})
    r,calls=call(handler=handle)
    assert len(calls)==3 and [row['video']['video_id'] for row in r.json()['intentions']]==['FIXTURE0003','FIXTURE0004','FIXTURE0005']
    assert 'BAD' not in r.text and 'evil.example' not in r.text


def test_partial_success_preserved_then_quota_halts_last_intention():
    def handle(req,n):return httpx.Response(200,json={'items':[item(1)]}) if n==1 else httpx.Response(429)
    r,calls=call(handler=handle)
    assert len(calls)==2 and r.json()['status']=='partial' and r.json()['video_count']==1
    assert [row['status'] for row in r.json()['intentions']]==['ok','unavailable','unavailable']


def test_key_echo_decoded_unicode_is_never_exposed():
    escaped=''.join('\\u%04x'%ord(c) for c in KEY)
    r,calls=call(payload(history=None),lambda req,n:httpx.Response(200,content=('{"items":[],"extra":"'+escaped+'"}').encode()))
    assert len(calls)==1 and r.json()['intentions'][0]['reason']=='YOUTUBE_SENSITIVE_RESPONSE_REJECTED' and KEY not in r.text


def test_live_limiter_shared_by_both_routes_no_wait_and_counts_failures(monkeypatch):
    clock=[0.0];budget=LiveSearchBudget(clock=lambda:clock[0]);monkeypatch.setattr('app.videos._LIVE_BUDGET',budget)
    calls=[]
    def handle(req):calls.append(req);return httpx.Response(200,json={'items':[item(len(calls))]})
    with TestClient(create_app(video_transport=httpx.MockTransport(handle))) as client:
        assert client.post('/api/v1/videos/explore',json=payload()).json()['video_count']==3
        assert client.post('/api/v1/videos/search',json={'opening':'sicilienne'}).json()['code']=='YOUTUBE_LOCAL_RATE_LIMITED'
        assert len(calls)==3
        clock[0]=60
        assert client.post('/api/v1/videos/search',json={'opening':'sicilienne'}).json()['status']=='ok'
    assert len(calls)==4 and not budget.busy


def test_limiter_concurrent_entry_and_error_release():
    budget=LiveSearchBudget();assert budget.enter() is None
    assert budget.enter()=='YOUTUBE_LIVE_BUSY';budget.leave()
    adapter=VideoDiscovery('live',httpx.MockTransport(lambda req:httpx.Response(500)),key_lookup=lambda:KEY,live_budget=budget)
    try:
        assert adapter.search(VideoRequest(opening='sicilienne')).code=='YOUTUBE_UPSTREAM_ERROR'
        assert not budget.busy
        assert adapter.search(VideoRequest(opening='sicilienne')).code=='YOUTUBE_UPSTREAM_ERROR'
        assert adapter.search(VideoRequest(opening='sicilienne')).code=='YOUTUBE_LOCAL_RATE_LIMITED'
    finally:adapter.close()

@pytest.mark.parametrize('changes',[{'history':['e2e5']},{'history':['e2e4']},{'q':'PRIVATE_RAW'},{'opening':'other'},{'api_key':KEY}])
def test_invalid_context_stops_before_key_or_http(monkeypatch,changes):
    key=Mock(side_effect=AssertionError('NO_KEY'));monkeypatch.setattr('app.videos.youtube_key',key)
    r,calls=call(payload(**changes));assert r.status_code==422 and not calls;key.assert_not_called()


def test_key_echo_html_entities_is_rejected_after_metadata_decoding():
    row=item(1);row['snippet']['title']=KEY.replace('_','&#95;')
    r,calls=call(payload(history=None),lambda req,n:httpx.Response(200,json={'items':[row]}))
    assert len(calls)==1 and r.json()['intentions'][0]['reason']=='YOUTUBE_SENSITIVE_RESPONSE_REJECTED' and KEY not in r.text
