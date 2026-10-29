"""YouTube I01 : fixtures explicites, aucun secret réel ou appel live."""
from copy import deepcopy
import json

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.videos import VideoDiscovery, VideoRequest, parse_video, MAX_BYTES, ENDPOINT


def item(ident='FIXTURE0001', **snippet):
    return {'id': {'kind': 'youtube#video', 'videoId': ident}, 'snippet': {
        'title': 'EXEMPLE SYNTHÉTIQUE &amp; échecs', 'channelTitle': 'Chaîne de fixture', **snippet}}


def service(handler):
    return VideoDiscovery('synthetic_fixture', httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def isolate_youtube(monkeypatch):
    monkeypatch.setenv('YOUTUBE_MODE', 'disabled')


def test_http_default_disabled_does_not_invoke_transport():
    def forbidden(request):raise AssertionError('NO_CALL')
    with TestClient(create_app(video_transport=httpx.MockTransport(forbidden))) as client:
        response = client.post('/api/v1/videos/search', json={'opening': 'sicilienne'})
    assert response.status_code == 200
    assert response.json()['status'] == 'disabled'
    assert response.json()['videos'] == []


def test_http_synthetic_happy_path_and_openapi(monkeypatch):
    monkeypatch.setenv('YOUTUBE_MODE', 'synthetic_fixture')
    with TestClient(create_app()) as client:
        r = client.post('/api/v1/videos/search', json={'opening': 'sicilienne', 'limit': 2})
        assert client.get('/openapi.json').json()['paths']['/api/v1/videos/search']['post']['requestBody']
    data = r.json()
    assert r.status_code == 200 and data['status'] == 'ok'
    assert data['synthetic'] and data['source'] == 'youtube_data_api'
    assert data['source_mode'] == 'synthetic_fixture' and data['editorial_review'] == 'not_reviewed'
    assert len(data['videos']) == 2
    assert all(v['url'] is None and v['thumbnail_url'] is None and 'SYNTHÉTIQUE' in v['title'] for v in data['videos'])


@pytest.mark.parametrize('payload', [
    {}, {'opening':'finale'}, {'opening':'position_inconnue'}, {'opening':'Sicilienne'},
    {'opening':'sicilienne','limit':0}, {'opening':'sicilienne','limit':4},
    {'opening':'sicilienne','limit':True}, {'opening':'sicilienne','limit':'2'},
    {'opening':'sicilienne','language':'en'}, {'opening':'sicilienne','context':'x'*301},
    {'opening':'sicilienne','context':'line\nbreak'}, {'opening':'sicilienne','fen':'invalid'},
    {'fen':'8/8/8/8/8/8/8/K6k w - - 0 1'}, {'opening':'sicilienne','api_key':'DUMMY_NEVER_A_REAL_SECRET'},
])
def test_invalid_request_never_calls_provider_or_echoes_input(monkeypatch, payload):
    monkeypatch.setenv('YOUTUBE_MODE', 'synthetic_fixture')
    def forbidden(request):raise AssertionError('INVALID_INPUT_CALLED_PROVIDER')
    with TestClient(create_app(video_transport=httpx.MockTransport(forbidden))) as client:
        r = client.post('/api/v1/videos/search', json=payload)
    assert r.status_code == 422
    assert r.json() == {'detail': {'code':'INVALID_VIDEO_REQUEST'}}


def test_malformed_json_is_sanitized():
    with TestClient(create_app()) as client:
        r = client.post('/api/v1/videos/search', content='{bad', headers={'content-type':'application/json'})
    assert r.status_code == 422 and r.json()['detail']['code'] == 'INVALID_VIDEO_REQUEST'


def test_params_are_bounded_opening_only_and_fen_is_not_inferred():
    calls=[]
    def transport(request):calls.append(request);return httpx.Response(200,json={'items':[]})
    s=service(transport)
    r=s.search(VideoRequest(opening='sicilienne', limit=1, context='IGNORE opening injected query',
        fen='rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'))
    s.close()
    assert r.status=='empty' and len(calls)==1
    assert str(calls[0].url).startswith(ENDPOINT+'?')
    assert dict(calls[0].url.params)=={'part':'snippet','type':'video','q':'défense sicilienne explication ouverture échecs','maxResults':'1','safeSearch':'strict','relevanceLanguage':'fr'}
    assert 'key' not in calls[0].url.params and 'fen' not in calls[0].url.params


@pytest.mark.parametrize('mode',['unknown','LIVE'])
def test_live_and_unknown_modes_cannot_start(mode):
    with pytest.raises(ValueError,match='LIVE_NOT_IMPLEMENTED'):VideoDiscovery(mode)


def test_real_transport_cannot_be_injected():
    with pytest.raises(ValueError,match='MOCK_TRANSPORT'):VideoDiscovery('synthetic_fixture',object())


def test_stable_order_dedup_filter_and_truncation():
    rows=[{'id':{'kind':'youtube#channel'}},item(),item(),item('FIXTURE0002'),item('FIXTURE0003')]
    s=service(lambda r:httpx.Response(200,json={'items':rows}))
    r=s.search(VideoRequest(opening='francaise',limit=2));s.close()
    assert [v.video_id for v in r.videos]==['FIXTURE0001','FIXTURE0002']
    assert r.filtered_items==2 and r.truncated and r.status=='ok'


@pytest.mark.parametrize('row', [None, {}, {'id':{'kind':'youtube#playlist'}}, item('../bad'),
    item(title='<script>alert(1)</script>'), item(title='x'*241), item(channelTitle=''),
    item(title='bad\x00title'), item(publishedAt='not-a-date'), item(publishedAt='2026-10-25'),
    item(thumbnails={'default':{'url':'https://evil.example/image.jpg'}}),
    item(thumbnails={'default':{'url':'https://i.ytimg.com.evil.example/vi/FIXTURE0001/default.jpg'}}),
    item(thumbnails={'default':{'url':'https://i.ytimg.com/vi/FIXTURE0002/default.jpg'}}),
    item(thumbnails={'default':{'url':'https://i.ytimg.com/vi/FIXTURE0001/default.jpg?evil=yes'}}),
])
def test_bad_provider_rows_are_filtered(row):
    s=service(lambda r:httpx.Response(200,json={'items':[row]}))
    result=s.search(VideoRequest(opening='italienne'));s.close()
    assert result.status=='empty' and not result.videos and result.filtered_items==1


def test_canonical_url_uses_only_validated_id_and_thumbnail_is_allowlisted():
    row=item(url='https://evil.example',publishedAt='2026-10-25T12:00:00Z',
        thumbnails={'default':{'url':'https://i.ytimg.com/vi/FIXTURE0001/default.jpg'}})
    parsed=parse_video(row)
    assert parsed.url=='https://www.youtube.com/watch?v=FIXTURE0001'
    assert parsed.thumbnail_url=='https://i.ytimg.com/vi/FIXTURE0001/default.jpg'
    assert parsed.title=='EXEMPLE SYNTHÉTIQUE & échecs' and parsed.published_at.endswith('+00:00')


@pytest.mark.parametrize('status,body,code', [
    (429,{},'YOUTUBE_RATE_LIMITED'),(401,{},'YOUTUBE_AUTHORIZATION_FAILED'),
    (403,{'error':{'errors':[{'reason':'quotaExceeded'}]}},'YOUTUBE_QUOTA_EXCEEDED'),
    (403,{'error':{'errors':[{'reason':'keyInvalid'}]}},'YOUTUBE_AUTHORIZATION_FAILED'),
    (500,{},'YOUTUBE_UPSTREAM_ERROR'),(302,{},'YOUTUBE_UPSTREAM_ERROR'),
])
def test_upstream_errors_once_no_retry_no_leak(status,body,code):
    calls=[]
    body['message']='DUMMY_NEVER_A_REAL_SECRET'
    def transport(request):calls.append(request);return httpx.Response(status,json=body)
    s=service(transport);r=s.search(VideoRequest(opening='espagnole'));s.close()
    assert r.status=='unavailable' and r.code==code and not r.videos
    assert len(calls)==1 and 'DUMMY_NEVER_A_REAL_SECRET' not in r.model_dump_json()


@pytest.mark.parametrize('exception,code',[(httpx.ReadTimeout,'YOUTUBE_TIMEOUT'),(httpx.ConnectError,'YOUTUBE_TRANSPORT_ERROR')])
def test_transport_errors_sanitized(exception,code):
    def transport(request):raise exception('DUMMY_NEVER_A_REAL_SECRET',request=request)
    s=service(transport);r=s.search(VideoRequest(opening='sicilienne'));s.close()
    assert r.code==code and 'DUMMY_NEVER_A_REAL_SECRET' not in r.model_dump_json()


@pytest.mark.parametrize('body,code',[(b'not json','YOUTUBE_INVALID_RESPONSE'),
    (b'[]','YOUTUBE_INVALID_RESPONSE'),(b'{"items":{}}','YOUTUBE_INVALID_RESPONSE'),
    (json.dumps({'items':[{}]*51}).encode(),'YOUTUBE_INVALID_RESPONSE'),
    (b'x'*(MAX_BYTES+1),'YOUTUBE_RESPONSE_TOO_LARGE')])
def test_response_schema_and_size_bound(body,code):
    s=service(lambda r:httpx.Response(200,content=body));r=s.search(VideoRequest(opening='sicilienne'));s.close()
    assert r.status=='unavailable' and r.code==code


def test_http_provider_error_is_explicit_state(monkeypatch):
    monkeypatch.setenv('YOUTUBE_MODE','synthetic_fixture')
    with TestClient(create_app(video_transport=httpx.MockTransport(lambda r:httpx.Response(429)))) as client:
        r=client.post('/api/v1/videos/search',json={'opening':'sicilienne'})
    assert r.status_code==200 and r.json()['status']=='unavailable' and r.json()['code']=='YOUTUBE_RATE_LIMITED'


def test_all_allowlisted_openings_and_fen_context():
    from app.videos import OPENINGS
    for opening in OPENINGS:
        assert VideoRequest(opening=opening,fen='8/8/8/8/8/8/8/K6k w - - 0 1').opening==opening
