"""Exact Docker proxy trust, no network, providers or engines."""
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.mark.parametrize('peer,origin,forwarded,expected',[
 ('172.30.73.2','http://127.0.0.1:5173',None,200),
 ('172.30.73.2','http://localhost:5173',None,200),
 ('172.30.73.2',None,None,403),
 ('172.30.73.2','http://evil.example',None,403),
 ('172.30.73.2','http://127.0.0.1:5174',None,403),
 ('172.30.73.4','http://127.0.0.1:5173',None,403),
 ('172.18.0.2','http://127.0.0.1:5173',None,403),
 ('203.0.113.3','http://127.0.0.1:5173',None,403),
 ('172.30.73.2','http://127.0.0.1:5173','for=127.0.0.1',403),
 ('127.0.0.1','http://localhost:5174',None,200),
])
def test_exact_docker_peer(monkeypatch,peer,origin,forwarded,expected):
    monkeypatch.setenv('DEMO_TRUSTED_PROXY_IP','172.30.73.2')
    headers={}
    if origin: headers['Origin']=origin
    if forwarded: headers['Forwarded']=forwarded
    with TestClient(create_app(),client=(peer,9)) as client:
        assert client.get('/api/v1/demo/capabilities',headers=headers).status_code==expected

def test_no_implicit_proxy_trust(monkeypatch):
    monkeypatch.delenv('DEMO_TRUSTED_PROXY_IP',raising=False)
    with TestClient(create_app(),client=('172.30.73.2',9)) as client:
        assert client.get('/api/v1/demo/capabilities',headers={'Origin':'http://localhost:5173'}).status_code==403
