"""Contrats HTTP du socle, sans réseau ni dépendance métier."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("APP_NAME", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_healthcheck_returns_json_ok(client):
    response = client.get("/api/v1/healthcheck")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"status": "ok"}


def test_unknown_route_is_not_a_success(client):
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_healthcheck_rejects_post(client):
    response = client.post("/api/v1/healthcheck", json={})
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]


def test_openapi_exposes_the_healthcheck_and_configured_title(monkeypatch):
    monkeypatch.setenv("APP_NAME", "Socle de test")
    with TestClient(create_app()) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Socle de test"
    assert "200" in schema["paths"]["/api/v1/healthcheck"]["get"]["responses"]


def test_empty_app_name_prevents_startup(monkeypatch):
    monkeypatch.setenv("APP_NAME", "   ")
    with pytest.raises(ValueError, match="APP_NAME must not be empty"):
        create_app()
