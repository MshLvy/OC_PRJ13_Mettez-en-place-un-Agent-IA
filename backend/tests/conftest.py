"""Toutes les suites sont offline : bloque toute connexion socket réelle."""

import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_live_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Real network is forbidden in this test suite")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setenv("EXPLORER_MODE", "disabled")
    monkeypatch.delenv("EXPLORER_DEFAULT_MODE", raising=False)
    monkeypatch.delenv("ANALYSIS_DEFAULT_ENGINE", raising=False)
    # Isoler les cas des vrais secrets et sélecteurs injectés dans le worker.
    monkeypatch.delenv("LICHESS_API_TOKEN", raising=False)
    monkeypatch.delenv("LICHESS_API_TOKEN_FILE", raising=False)
    monkeypatch.delenv("LOCAL_LLM_URL", raising=False)
    for key in ("ADVISOR_API_PROVIDER","ADVISOR_API_MODEL","ADVISOR_API_ENDPOINT","ADVISOR_API_SECRET_ENV","ADVISOR_API_TIMEOUT_SECONDS","LOCAL_LLM_TIMEOUT_SECONDS","GENERATION_MAX_TOKENS","LOCAL_LLM_MAX_TOKENS","MISTRAL_MAX_TOKENS","GROQ_MAX_TOKENS","GROQ_REASONING_EFFORT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("app.conversation_generators.secret_value", lambda name: "")
    monkeypatch.setenv("MONGO_ENABLED","false")
    monkeypatch.setenv("YOUTUBE_MODE","disabled")
    monkeypatch.setattr("app.videos.youtube_key", lambda: "")
    monkeypatch.setenv("STOCKFISH_ENABLED", "false")
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    monkeypatch.delenv("STOCKFISH_TIME_SECONDS", raising=False)

    def no_engine(*args, **kwargs):
        raise AssertionError("Real engine spawn is forbidden during pytest")

    monkeypatch.setattr("app.stockfish.spawn_engine", no_engine)
