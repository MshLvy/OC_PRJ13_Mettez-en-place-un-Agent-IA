"""Ephemeral deterministic root + four real compiled subgraphs.

No checkpoint, retry, tracing export or automatic side-effect continuation.
Business services remain the authority. Payloads/results stay request-local.
"""
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict
import re

from langgraph.graph import START, END, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy
from langsmith.run_helpers import tracing_context
from pydantic import BaseModel, ValidationError
from fastapi import HTTPException
from app.explorer import ExplorerError
from app.stockfish import StockfishError
from app.positions import FenValidationError
from app.analysis_preferences import PreferenceError
from app.orchestration import OrchestrationError

from app.analysis_routes import AnalysisRequest
from app.advisor import RetrieveRequest, RetrievalResponse
from app.conversation import ConversationRequest, ConversationResponse
from app.demo import DemoAnalysisRequest, DemoTurnRequest
from app.game import HistoryRequest, TurnRequest, GameError, rebuild, state_from
from app.position_routes import PositionRequest, PositionResponse
from app.positions import diagnose_fen
from app.sessions import SessionDraft, SessionRecord, SessionSummary, SessionFailure, ID
from app.video_exploration import ExploreRequest, VideoExplorationBusy
from app.videos import VideoRequest
from app.vector_search import VectorRequest

WorkflowIntent = Literal[
    'analysis', 'demo_analysis', 'moves', 'evaluate', 'game_state', 'game_turn',
    'demo_turn', 'position_validate', 'opening_identify', 'conversation', 'retrieve_v1',
    'vector_search', 'videos_explore', 'videos_search', 'session_create', 'session_list',
    'session_get', 'session_resume', 'session_delete',
]

GROUPS = {
    **dict.fromkeys(('analysis', 'demo_analysis', 'moves', 'evaluate', 'game_state',
                     'game_turn', 'demo_turn', 'position_validate', 'opening_identify'), 'analysis'),
    **dict.fromkeys(('conversation', 'retrieve_v1', 'vector_search'), 'rag'),
    **dict.fromkeys(('videos_explore', 'videos_search'), 'videos'),
    **dict.fromkeys(('session_create', 'session_list', 'session_get', 'session_resume', 'session_delete'), 'sessions'),
}
MODELS = {'analysis': AnalysisRequest, 'demo_analysis': DemoAnalysisRequest,
          'game_turn': TurnRequest, 'demo_turn': DemoTurnRequest,
          'game_state': HistoryRequest, 'opening_identify': HistoryRequest,
          'position_validate': PositionRequest, 'conversation': ConversationRequest,
          'retrieve_v1': RetrieveRequest, 'vector_search': VectorRequest,
          'videos_explore': ExploreRequest, 'videos_search': VideoRequest,
          'session_create': SessionDraft}

class WorkflowState(TypedDict, total=False):
    intent: WorkflowIntent
    context: dict[str, str]  # admitted FEN only when this action carries one
    payload: dict[str, Any]
    result: Any
    errors: list[dict[str, Any]]
    provenance: list[str]

@dataclass
class Invocation:
    services: Any
    trace: list[str] = field(default_factory=list)
    failure: Exception | None = None  # not serialized into state/provenance


def _record(runtime, name):
    runtime.context.trace.append(name)


def _failure(runtime, error):
    known = (GameError, SessionFailure, ExplorerError, StockfishError,
             FenValidationError, PreferenceError, OrchestrationError, VideoExplorationBusy)
    if isinstance(error, ValidationError):
        code, status = 'INVALID_WORKFLOW_REQUEST', 422
        error = HTTPException(status, detail={'code': code})
    elif not isinstance(error, known):
        # Unexpected exception bodies may contain private upstream data. Do not
        # serialize, log or chain them across the orchestration boundary.
        code, status = 'WORKFLOW_OPERATION_UNCONFIRMED', 503
        error = HTTPException(status, detail={'code': code})
    else:
        code = getattr(error, 'code', 'VIDEO_EXPLORATION_BUSY')
        if not isinstance(code, str) or not re.fullmatch(r'[A-Z0-9_]{1,80}', code):
            code = 'WORKFLOW_REQUEST_FAILED'
        fallback = 422 if isinstance(error, (FenValidationError, PreferenceError)) else 503
        status = getattr(error, 'status', getattr(error, 'http_status', fallback))
    runtime.context.failure = error
    return {'result': None, 'errors': [{'code': code, 'http_status': status if type(status) is int else 500}]}


def route_action(state: WorkflowState, runtime: Runtime[Invocation]):
    _record(runtime, 'root.route_action')
    if state.get('intent') not in GROUPS:
        raise GameError('WORKFLOW_INTENT_NOT_SUPPORTED')
    return {'context': {}, 'errors': [], 'provenance': [GROUPS[state['intent']]]}


def admit_action(state: WorkflowState, runtime: Runtime[Invocation]):
    intent = state['intent']; _record(runtime, GROUPS[intent] + '.admit_action')
    try:
        payload = dict(state['payload'])
        if intent in MODELS:
            if set(payload) != {'body'}: raise GameError('INVALID_WORKFLOW_PAYLOAD')
            model = payload['body']
            # exclude_unset preserves absent preferences and Demo's forbidden
            # client source field, rather than injecting model defaults as HTTP.
            values = model.model_dump(exclude_unset=True) if isinstance(model, BaseModel) else model
            payload['body'] = MODELS[intent].model_validate(values)
        elif intent in ('moves', 'evaluate'):
            if set(payload) != {'fen'}: raise GameError('INVALID_WORKFLOW_PAYLOAD')
            payload['fen'] = diagnose_fen(payload['fen']).fen_normalized
        elif intent in ('session_get', 'session_resume', 'session_delete'):
            if set(payload) != {'ident'} or not isinstance(payload['ident'], str) or not re.fullmatch(ID, payload['ident']):
                raise SessionFailure('INVALID_SESSION_REQUEST', 422)
        elif intent == 'session_list':
            if set(payload) != {'after', 'limit'} or type(payload['limit']) is not int or not 1 <= payload['limit'] <= 20 or payload['after'] is not None and (not isinstance(payload['after'], str) or not re.fullmatch(ID, payload['after'])):
                raise SessionFailure('INVALID_SESSION_REQUEST', 422)
        # Functional authorization (ceilings, receipts, disabled Mongo, scope,
        # live budgets) remains inside the existing sole business service.
        body = payload.get('body'); fen = getattr(body, 'fen', payload.get('fen'))
        admitted = {}
        if isinstance(fen, str):
            try:
                normalized = diagnose_fen(fen).fen_normalized
                history = getattr(body, 'history', None)
                if history is None or rebuild(history)[0].fen(en_passant='fen') == normalized:
                    admitted = {'fen': normalized}
            except (ValueError, GameError, TypeError):
                pass  # preserve each existing service's invalid-context contract
        return {'payload': payload, 'context': admitted}
    except Exception as error:
        return _failure(runtime, error)


def execute_action(state: WorkflowState, runtime: Runtime[Invocation]):
    intent = state['intent']; _record(runtime, GROUPS[intent] + '.execute_action')
    if runtime.context.failure is not None:
        return {}  # admission error must not start any business service
    p = state['payload']; s = runtime.context.services; body = p.get('body')
    try:
        if intent == 'analysis':
            value = s.orchestrator.invoke(body.fen, body.include_explorer, body.include_engine,
                                         explorer_mode=body.explorer_mode, engine_policy=body.engine_policy)
        elif intent == 'demo_analysis': value = s.demo.analysis(body)
        elif intent == 'moves': value = s.explorer.moves(p['fen'])
        elif intent == 'evaluate': value = s.stockfish.evaluate(p['fen'])
        elif intent == 'game_state': value = state_from(*rebuild(body.history))
        elif intent == 'game_turn': value = s.game.turn(body)
        elif intent == 'demo_turn': value = s.demo.turn(body)
        elif intent == 'position_validate': value = PositionResponse.model_validate(diagnose_fen(body.fen), from_attributes=True)
        elif intent == 'opening_identify': value = s.openings.identify(body.history)
        elif intent == 'retrieve_v1': value = s.advisor.retrieve(body)
        elif intent == 'conversation': value = s.conversation.ask(body)
        elif intent == 'vector_search': value = s.vector_search.search(body)
        elif intent == 'videos_explore': value = s.video_exploration.invoke(body)
        elif intent == 'videos_search': value = s.videos.search(body)
        elif intent == 'session_create': value = s.sessions.create(body)
        elif intent == 'session_list': value = s.sessions.list(p['after'], p['limit'])
        elif intent in ('session_get', 'session_resume'): value = s.sessions.get(p['ident'])
        elif intent == 'session_delete': value = s.sessions.delete(p['ident'])
        else: raise GameError('WORKFLOW_INTENT_NOT_SUPPORTED')
        return {'result': value}
    except Exception as error:
        # Record a short state error, complete safely, then rethrow the ORIGINAL
        # domain exception to the historical HTTP adapter. No replay or retry.
        return _failure(runtime, error)


def check_result(state: WorkflowState, runtime: Runtime[Invocation]):
    intent = state['intent']; _record(runtime, GROUPS[intent] + '.check_result')
    if runtime.context.failure is not None: return {}
    try:
        value = state['result']; s = runtime.context.services
        if intent in ('session_create', 'session_get', 'session_resume'):
            value = SessionRecord.model_validate(value.model_dump() if isinstance(value, BaseModel) else value)
        elif intent == 'session_list':
            if (not isinstance(value, dict) or set(value) != {'items', 'next_cursor'}
                    or not isinstance(value['items'], list) or len(value['items']) > state['payload']['limit']
                    or value['next_cursor'] is not None and (not isinstance(value['next_cursor'], str) or not re.fullmatch(ID, value['next_cursor']))):
                raise SessionFailure('SESSION_DATA_INVALID')
            for item in value['items']: SessionSummary.model_validate(item)
        elif intent == 'session_delete' and value != {'status': 'deleted', 'id': state['payload']['ident']}:
            raise SessionFailure('SESSION_DELETE_UNCONFIRMED')
        elif intent == 'conversation':
            value = ConversationResponse.model_validate(value)
            value.session_receipt = s.session_receipts.issue(state['payload']['body'], value)
        elif intent == 'retrieve_v1': value = RetrievalResponse.model_validate(value)
        return {'result': value}
    except Exception as error:
        if intent.startswith('session_') and not isinstance(error, SessionFailure):
            code = 'SESSION_WRITE_UNCONFIRMED' if intent == 'session_create' else 'SESSION_DELETE_UNCONFIRMED' if intent == 'session_delete' else 'SESSION_DATA_INVALID'
            error = SessionFailure(code)
        return _failure(runtime, error)  # NEVER repeat an uncertain write


def finish_action(state: WorkflowState, runtime: Runtime[Invocation]):
    _record(runtime, 'root.finish_action')
    return {}


def build_specialized(name):
    graph = StateGraph(WorkflowState, context_schema=Invocation)
    def admitted(state: WorkflowState, runtime: Runtime[Invocation]):
        if GROUPS.get(state.get('intent')) != name:
            raise GameError('WORKFLOW_BRANCH_MISMATCH')
        return admit_action(state, runtime)
    graph.add_node('admit_action', admitted, retry_policy=RetryPolicy(max_attempts=1))
    for fn in (execute_action, check_result):
        graph.add_node(fn.__name__, fn, retry_policy=RetryPolicy(max_attempts=1))
    graph.add_edge(START, 'admit_action')
    graph.add_edge('admit_action', 'execute_action')
    graph.add_edge('execute_action', 'check_result')
    graph.add_edge('check_result', END)
    return graph.compile(checkpointer=None, name='p13_' + name)


def build_workflow():
    children = {name: build_specialized(name) for name in ('analysis', 'rag', 'videos', 'sessions')}
    graph = StateGraph(WorkflowState, context_schema=Invocation)
    graph.add_node('route_action', route_action, retry_policy=RetryPolicy(max_attempts=1))
    for name, child in children.items():
        graph.add_node(name, child, retry_policy=RetryPolicy(max_attempts=1))
        graph.add_edge(name, 'finish_action')
    graph.add_node('finish_action', finish_action, retry_policy=RetryPolicy(max_attempts=1))
    graph.add_edge(START, 'route_action')
    graph.add_conditional_edges('route_action', lambda state: GROUPS[state['intent']], list(children))
    graph.add_edge('finish_action', END)
    return graph.compile(checkpointer=None, name='p13_global'), children


class Workflow:
    def __init__(self, services):
        self.services = services
        self.graph, self.subgraphs = build_workflow()

    def invoke(self, intent: WorkflowIntent, payload: dict[str, Any], *, trace=None):
        context = Invocation(self.services, trace if trace is not None else [])
        with tracing_context(enabled=False):
            result = self.graph.invoke({'intent': intent, 'payload': payload}, context=context,
                                       config={'recursion_limit': 16, 'max_concurrency': 1, 'callbacks': []})
        if context.failure is not None: raise context.failure
        return result['result']
