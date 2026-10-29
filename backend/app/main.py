"""Application FastAPI : contrôle de vie et diagnostic échiquéen local."""

from typing import Literal
from contextlib import asynccontextmanager, ExitStack

import httpx2 as httpx

from fastapi import FastAPI
from pydantic import BaseModel

from app.sessions import MongoStore,Receipts,SessionService
from app.sessions_routes import router as sessions_router
from app.video_exploration import VideoExploration
from app.videos import VideoDiscovery
from app.videos_routes import router as videos_router
import os
from app.demo import DemoService, DemoSettings, router as demo_router
from app.openings import OpeningIdentifier
from app.openings_routes import router as openings_router
from app.conversation import ConversationService
from app.conversation_routes import router as conversation_router
from app.advisor import AdvisorService
from app.advisor_routes import router as advisor_router
from app.game import GameService
from app.game_routes import router as game_router
from app.config import Settings
from app.explorer import OpeningExplorer
from app.explorer_fixtures import synthetic_transport
from app.explorer_live import configured_live_client as live_client, SecretConfigurationError
from app.explorer_registry import explorer_registry, UnavailableLiveExplorer
from app.moves_routes import router as moves_router
from app.position_routes import router as positions_router
from app.evaluate_routes import router as evaluate_router
from app.stockfish import StockfishService
from app.orchestration import AnalysisOrchestrator
from app.analysis_routes import router as analysis_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app(explorer_client: httpx.Client | None = None, stockfish_runner=None, video_transport: httpx.MockTransport | None = None, session_store=None) -> FastAPI:
    settings = Settings.from_env()
    videos = VideoDiscovery.from_env(video_transport)
    store=session_store if session_store is not None else MongoStore()
    receipts=Receipts()
    owned_clients = [videos,store]
    disabled = OpeningExplorer(None)
    synthetic = None
    live = None
    if settings.explorer_mode != "disabled":
        synthetic_client = httpx.Client(transport=httpx.MockTransport(synthetic_transport))
        owned_clients.append(synthetic_client)
        synthetic = OpeningExplorer(synthetic_client, "synthetic_fixture")
    if settings.explorer_mode == "live":
        if explorer_client is not None:
            live = OpeningExplorer(explorer_client, "injected_transport")
        else:
            try:
                client = live_client(settings.lichess_token_file)
            except SecretConfigurationError as error:
                # Le plafond autorise live sans imposer sa disponibilité au boot.
                # Échec sûr enregistré ; pas de fallback, recréer après correction.
                live = UnavailableLiveExplorer(str(error))
            else:
                owned_clients.append(client)
                live = OpeningExplorer(client, "live")
    registry = explorer_registry(disabled, synthetic, live)
    legacy = (OpeningExplorer(explorer_client, "injected_transport") if explorer_client is not None
              else registry[settings.explorer_mode])

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            yield
        finally:
            with ExitStack() as cleanup:
                for client in owned_clients:
                    cleanup.callback(client.close)

    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    @application.middleware('http')
    async def workflow_provenance(request, call_next):
        response = await call_next(request)
        trace = getattr(request.state, 'workflow_trace', None)
        if trace:
            # Names only; no payload/FEN/question/receipt in headers or logs.
            response.headers['X-Workflow-Graph'] = 'p13_global_v1'
            response.headers['X-Workflow-Path'] = ','.join(trace)
        return response
    application.state.session_store=store
    application.state.session_receipts=receipts
    application.state.sessions=SessionService(store,receipts)
    application.include_router(sessions_router)
    application.state.video_exploration = VideoExploration(videos)
    application.state.videos = videos
    application.include_router(videos_router)
    application.state.explorer = legacy
    application.state.explorers = registry
    application.state.stockfish = StockfishService(settings.stockfish, runner=stockfish_runner)
    allow_tools = os.getenv('GAME_ALLOW_TOOLS', 'false')
    if allow_tools not in ('true', 'false'):
        raise ValueError('INVALID_GAME_ALLOW_TOOLS')
    application.state.game = GameService(legacy, application.state.stockfish, allow_tools=allow_tools == 'true')
    application.include_router(game_router)
    application.state.openings = OpeningIdentifier()
    application.include_router(openings_router)
    application.state.advisor = AdvisorService(application.state.openings)
    application.include_router(advisor_router)
    application.state.conversation=ConversationService()
    application.include_router(conversation_router)
    application.state.orchestrator = AnalysisOrchestrator(application.state.explorer, application.state.stockfish,
        settings=settings, explorers=registry)
    application.include_router(analysis_router)
    application.state.demo = DemoService(settings, DemoSettings.from_env(), registry,
        application.state.stockfish, allow_tools == "true")
    application.include_router(demo_router)
    application.include_router(moves_router)
    application.include_router(positions_router)
    application.include_router(evaluate_router)

    @application.get("/api/v1/healthcheck", response_model=HealthResponse)
    async def healthcheck() -> HealthResponse:
        """Confirme que l'API répond, sans vérifier de dépendance externe."""
        return HealthResponse()

    from app.vector_search import VectorSearch
    from app.vector_routes import router as vector_router
    from app.workflow import Workflow
    application.state.vector_search = VectorSearch(application.state.conversation)
    application.include_router(vector_router)
    application.state.workflow = Workflow(application.state)
    return application


app = create_app()
