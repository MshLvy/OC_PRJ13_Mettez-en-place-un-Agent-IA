"""Graphe LangGraph déterministe, éphémère et sans génération de texte."""

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Callable, Literal, TypedDict, Mapping

from app.config import Settings
from app.analysis_preferences import ResolvedPreferences, resolve_preferences

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy
from langsmith.run_helpers import tracing_context
from pydantic import BaseModel

from app.evaluate_routes import EvaluationResponse
from app.explorer import ExplorerError, OpeningExplorer
from app.moves_routes import MovesResponse
from app.position_routes import PositionResponse
from app.positions import PositionDiagnostic, diagnose_fen
from app.stockfish import StockfishError, StockfishService

GRAPH_BUDGET_SECONDS = 20.0
# Explorer : budget lecture10s vérifié après I/O + timeout de phase5s.
# Moteur : préparation2s + analyse2s + arrêt/récolte1s (I03).
TOOL_RESERVATIONS = {"explorer": 15.0, "engine": 5.0}
ToolName = Literal["explorer", "engine", "orchestration"]
ToolStatus = Literal["not_requested", "skipped_terminal", "ok", "empty", "disabled", "error", "skipped_theory_available"]
Step = Literal["validate_position", "fetch_explorer", "evaluate_engine", "assemble_response"]


class OrchestrationError(Exception):
    def __init__(self, code: str, http_status: int):
        super().__init__(code)
        self.code, self.http_status = code, http_status


class ToolError(BaseModel):
    tool: ToolName
    code: str
    http_status: int
    retry_after_seconds: int | None = None


class ExplorerOutcome(BaseModel):
    requested: bool
    status: ToolStatus
    http_status: int | None = None
    result: MovesResponse | None = None


class EngineOutcome(BaseModel):
    requested: bool
    status: ToolStatus
    http_status: int | None = None
    result: EvaluationResponse | None = None


class ToolOutcomes(BaseModel):
    explorer: ExplorerOutcome
    engine: EngineOutcome


class Provenance(BaseModel):
    tool: Literal["position", "explorer", "engine"]
    source: Literal["python_chess", "lichess_opening_explorer", "stockfish"]
    source_mode: Literal["local_diagnostic", "disabled", "synthetic_fixture", "injected_transport", "live", "local_engine"]
    attempted: bool
    engine_version: str | None = None


class GraphExecution(BaseModel):
    framework: Literal["langgraph"] = "langgraph"
    graph_version: Literal["j03_i04bis_v2"] = "j03_i04bis_v2"
    steps: list[Step]


class ExecutionPolicy(BaseModel):
    tool_order: Literal["explorer_then_engine"] = "explorer_then_engine"
    budget_seconds: float = GRAPH_BUDGET_SECONDS
    deadline_mode: Literal["cooperative_between_bounded_tools"] = "cooperative_between_bounded_tools"
    retries: Literal[0] = 0
    persistent_state: Literal[False] = False
    engine_policy: Literal["requested", "theory_fallback"] = "requested"


class AnalysisResponse(BaseModel):
    status: Literal["ok", "partial", "terminal"]
    fen_normalized: str
    position: PositionResponse
    tools: ToolOutcomes
    errors: list[ToolError]
    provenance: list[Provenance]
    policy: ExecutionPolicy
    graph: GraphExecution
    preferences: ResolvedPreferences


class AnalysisState(TypedDict, total=False):
    engine_policy: Literal["requested", "theory_fallback"]
    fen_original: str
    requested_explorer_mode: str | None
    requested_include_explorer: bool | None
    requested_include_engine: bool | None
    preferences: ResolvedPreferences
    include_explorer: bool
    include_engine: bool
    fen_normalized: str
    diagnostic: PositionDiagnostic
    explorer: ExplorerOutcome
    engine: EngineOutcome
    errors: list[ToolError]
    provenance: list[Provenance]
    policy: ExecutionPolicy
    status: Literal["ok", "partial", "terminal"]


@dataclass
class GraphGate:
    lock: Lock = field(default_factory=Lock)


_GLOBAL_GATE = GraphGate()  # Un parcours avec outils par worker ; pas de file.


@dataclass
class InvocationContext:
    # Capabilités hors état : jamais sérialisées/checkpointées/tracées.
    explorers: Mapping[str, OpeningExplorer]
    settings: Settings
    engine: StockfishService
    gate: GraphGate
    clock: Callable[[], float]
    deadline: float
    acquired: bool = False


def validate_position(state: AnalysisState, runtime: Runtime[InvocationContext]):
    diagnostic = diagnose_fen(state["fen_original"])
    preferences = resolve_preferences(runtime.context.settings,
        explorer_mode=state["requested_explorer_mode"], include_explorer=state["requested_include_explorer"],
        include_engine=state["requested_include_engine"])
    state = {**state, "include_explorer": preferences.explorer.resolved != "disabled",
             "include_engine": preferences.engine.resolved}
    if not diagnostic.is_terminal and (state["include_explorer"] or state["include_engine"]):
        if not runtime.context.gate.lock.acquire(blocking=False):
            raise OrchestrationError("ORCHESTRATION_BUSY", 503)
        runtime.context.acquired = True
    def initial(requested):
        return "skipped_terminal" if requested and diagnostic.is_terminal else "not_requested"
    return {"preferences": preferences, "include_explorer": state["include_explorer"],
            "include_engine": state["include_engine"], "diagnostic": diagnostic, "fen_normalized": diagnostic.fen_normalized,
            "explorer": ExplorerOutcome(requested=state["include_explorer"], status=initial(state["include_explorer"])),
            "engine": EngineOutcome(requested=state["include_engine"], status=initial(state["include_engine"])),
            "errors": [], "policy": ExecutionPolicy(engine_policy=state.get("engine_policy", "requested")),
            "provenance": [Provenance(tool="position", source="python_chess",
                                      source_mode="local_diagnostic", attempted=True)]}


def after_validation(state: AnalysisState):
    if state["diagnostic"].is_terminal:
        return "assemble_response"
    if state["include_explorer"]:
        return "fetch_explorer"
    return after_explorer(state)


def after_explorer(state: AnalysisState):
    available = (state.get('engine_policy') == 'theory_fallback'
                 and state['explorer'].status == 'ok' and state['explorer'].result
                 and state['explorer'].result.moves)
    return "evaluate_engine" if state["include_engine"] and not available else "assemble_response"


def _within_budget(runtime, tool):
    # Pas de thread abandonné/cancel simulé : les adaptateurs conservent leur
    # propre cleanup. On ne démarre pas un outil sans réserver sa borne entière.
    return runtime.context.deadline - runtime.context.clock() >= TOOL_RESERVATIONS[tool]


def fetch_explorer(state: AnalysisState, runtime: Runtime[InvocationContext]):
    adapter = runtime.context.explorers[state["preferences"].explorer.resolved]
    attempted = _within_budget(runtime, "explorer")
    errors = []
    try:
        if not attempted:
            raise ExplorerError("ORCHESTRATION_DEADLINE_EXCEEDED", 504)
        result = MovesResponse.model_validate(adapter.moves(state["fen_normalized"]), from_attributes=True)
        outcome = ExplorerOutcome(requested=True, status=result.status, http_status=200, result=result)
    except ExplorerError as error:
        outcome = ExplorerOutcome(requested=True, status="disabled" if error.code == "EXPLORER_DISABLED" else "error",
                                  http_status=error.http_status)
        errors = [ToolError(tool="explorer", code=error.code, http_status=error.http_status,
                            retry_after_seconds=error.retry_after)]
    except Exception:
        outcome = ExplorerOutcome(requested=True, status="error", http_status=500)
        errors = [ToolError(tool="explorer", code="EXPLORER_INTERNAL_ERROR", http_status=500)]
    engine_update = {}
    if (state.get('engine_policy') == 'theory_fallback' and state['include_engine']
            and outcome.status == 'ok' and outcome.result and outcome.result.moves):
        engine_update['engine'] = EngineOutcome(requested=True, status='skipped_theory_available')
    return {**engine_update, "explorer": outcome, "errors": state["errors"] + errors,
            "provenance": state["provenance"] + [Provenance(tool="explorer", source="lichess_opening_explorer",
                                                           source_mode=adapter.source_mode, attempted=attempted)]}


def evaluate_engine(state: AnalysisState, runtime: Runtime[InvocationContext]):
    attempted = _within_budget(runtime, "engine")
    errors = []
    try:
        if not attempted:
            raise StockfishError("ORCHESTRATION_DEADLINE_EXCEEDED", 504)
        result = EvaluationResponse.model_validate(runtime.context.engine.evaluate(state["fen_normalized"]),
                                                   from_attributes=True)
        outcome = EngineOutcome(requested=True, status="ok", http_status=200, result=result)
    except StockfishError as error:
        outcome = EngineOutcome(requested=True, status="disabled" if error.code == "STOCKFISH_DISABLED" else "error",
                                http_status=error.http_status)
        errors = [ToolError(tool="engine", code=error.code, http_status=error.http_status)]
    except Exception:
        outcome = EngineOutcome(requested=True, status="error", http_status=500)
        errors = [ToolError(tool="engine", code="STOCKFISH_INTERNAL_ERROR", http_status=500)]
    return {"engine": outcome, "errors": state["errors"] + errors,
            "provenance": state["provenance"] + [Provenance(tool="engine", source="stockfish",
                source_mode="local_engine", attempted=attempted,
                engine_version=outcome.result.engine_version if outcome.result else None)]}


def assemble_response(state: AnalysisState, runtime: Runtime[InvocationContext]):
    errors = state["errors"]
    if runtime.context.clock() > runtime.context.deadline:
        errors = errors + [ToolError(tool="orchestration", code="ORCHESTRATION_DEADLINE_EXCEEDED", http_status=504)]
    status = "terminal" if state["diagnostic"].is_terminal else "partial" if errors else "ok"
    return {"status": status, "errors": errors}


def build_graph():
    builder = StateGraph(AnalysisState, context_schema=InvocationContext)
    for node in (validate_position, fetch_explorer, evaluate_engine, assemble_response):
        builder.add_node(node.__name__, node, retry_policy=RetryPolicy(max_attempts=1))
    builder.add_edge(START, "validate_position")
    builder.add_conditional_edges("validate_position", after_validation,
        ["fetch_explorer", "evaluate_engine", "assemble_response"])
    builder.add_conditional_edges("fetch_explorer", after_explorer, ["evaluate_engine", "assemble_response"])
    builder.add_edge("evaluate_engine", "assemble_response")
    builder.add_edge("assemble_response", END)
    return builder.compile(checkpointer=None, name="chess_analysis_i04")


class AnalysisOrchestrator:
    def __init__(self, explorer, engine, *, settings=None, explorers=None, clock=monotonic, gate=None):
        self.explorer, self.engine = explorer, engine
        self.settings = settings or Settings("OC Projet 13")
        self.explorers = explorers if explorers is not None else {self.settings.explorer_mode: explorer}
        self.clock, self.gate = clock, gate or _GLOBAL_GATE
        self.graph = build_graph()  # Compilation sans I/O, ni invocation d'outil.

    def invoke(self, fen, include_explorer=None, include_engine=None, *, explorer_mode=None, engine_policy="requested"):
        if engine_policy not in ('requested', 'theory_fallback'):
            raise OrchestrationError('INVALID_ENGINE_POLICY', 422)
        state = AnalysisState(engine_policy=engine_policy, fen_original=fen, requested_include_explorer=include_explorer,
                              requested_include_engine=include_engine, requested_explorer_mode=explorer_mode)
        context = InvocationContext(self.explorers, self.settings, self.engine, self.gate, self.clock,
                                    self.clock() + GRAPH_BUDGET_SECONDS)
        steps = []
        try:
            # Le traçage hébergé reste désactivé même si le shell l'active.
            with tracing_context(enabled=False):
                for update in self.graph.stream(state, context=context, stream_mode="updates",
                        config={"recursion_limit": 8, "max_concurrency": 1, "callbacks": []}):
                    for step, values in update.items():
                        steps.append(step)  # Noms réellement émis par le runtime LangGraph.
                        state.update(values)
            return AnalysisResponse(status=state["status"], fen_normalized=state["fen_normalized"],
                position=PositionResponse.model_validate(state["diagnostic"], from_attributes=True),
                tools=ToolOutcomes(explorer=state["explorer"], engine=state["engine"]),
                errors=state["errors"], provenance=state["provenance"], policy=state["policy"],
                graph=GraphExecution(steps=steps), preferences=state["preferences"])
        finally:
            if context.acquired:
                self.gate.lock.release()
