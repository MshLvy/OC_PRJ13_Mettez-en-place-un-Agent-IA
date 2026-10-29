"""Dense-only result contract over the existing admitted V3 retrieval.

BM25 remains a contextual admission gate, never returned as a dense fallback.
No new encoder/index/model or Milvus write is introduced.
"""
from typing import Literal
from pydantic import BaseModel, Field
from app.conversation import ConversationRequest, Evidence, evidence_from_row
from app.conversation_data import load_chunks

class VectorRequest(ConversationRequest):
    # Same FEN/history/snapshot/scope validation. Generation selectors are not
    # configurable: even a Python caller cannot enable a generator here.
    request_generation: Literal[False] = False
    demo_mode: Literal['simulation'] = 'simulation'

class VectorResponse(BaseModel):
    status: Literal['ok', 'invalid', 'abstain', 'unavailable']
    reason: str
    fen: str | None = None
    snapshot: str | None = None
    passages: list[Evidence] = Field(default_factory=list, max_length=3)
    dense_executed: bool = False
    provenance: dict = Field(default_factory=dict)

class VectorSearch:
    def __init__(self, conversation): self.conversation = conversation
    def search(self, body):
        body = VectorRequest.model_validate(body.model_dump())
        # Reuse ALL existing admission checks and the same BM25/BGE pipeline,
        # with generation explicitly false. No generator/receipt/DB call.
        result = self.conversation.ask(ConversationRequest(**body.model_dump()))
        trace = result.retrieval_trace
        ready = result.dense_status == 'ready' and trace.get('dense_reason') == 'BGE_READ_ONLY_SEARCH_VERIFIED'
        provenance = {key: trace[key] for key in ('method', 'dense_status', 'dense_attempted', 'dense_reason', 'collection', 'model', 'revision', 'dimension', 'exact_scope', 'elapsed_ms') if key in trace}
        common = dict(fen=result.fen, snapshot=result.snapshot, dense_executed=ready, provenance=provenance)
        if result.status in ('invalid', 'abstain'):
            return VectorResponse(status=result.status, reason=result.reason, **common)
        if result.status == 'unavailable':
            return VectorResponse(status='unavailable', reason=result.reason, **common)
        if not ready:
            return VectorResponse(status='unavailable', reason=trace.get('dense_reason', 'BGE_UNAVAILABLE'), **common)
        # Dense order only, restricted to the IDs admitted by the historical
        # contextual policy. Do not expose any lexical-only RRF result.
        docs = {r['chunk_id']: r for r in load_chunks()}
        ids = trace.get('dense_admitted_ids', [])
        rows = [evidence_from_row(docs[ident], body.intent) for ident in ids]
        return VectorResponse(status='ok' if rows else 'abstain',
                              reason='REAL_DENSE_PASSAGES' if rows else 'NO_ADMISSIBLE_DENSE_PASSAGE',
                              passages=rows, **common)
