"""RRF60 candidate, exact contextual admission first. No confidence threshold claim."""
from time import monotonic
from app import conversation_data as data
from app.conversation_bge import BgeClient,DenseUnavailable,COLLECTION,REVISION

class Retrieval:
    def __init__(self,dense=None):self.dense=dense if dense is not None else BgeClient()
    def retrieve(self,question,fen,intent):
        start=monotonic()
        # Preserve the historical call/signature for position requests, including doubles.
        lexical,reason=data.retrieve(question,fen) if intent=='position' else data.retrieve(question,fen,intent)
        trace={'method':'offline_bm25_v3','dense_status':'integration_pending','dense_attempted':False,'dense_reason':'BGE_NOT_CONFIGURED','bm25_ids':[r['chunk_id'] for r in lexical],'dense_hits':[],'dense_admitted_ids':[],'exact_scope':'current_reference_position' if intent=='position' else 'opening_theory','rrf_k':60,'calibrated_threshold':None}
        def done(rows,why):
            trace['elapsed_ms']=round((monotonic()-start)*1000,2);return rows,why,trace
        if reason or not lexical:return done(lexical,reason)
        if not self.dense.configured:return done(lexical,None)
        trace.update(dense_attempted=True,collection=COLLECTION,model='BAAI/bge-m3',revision=REVISION,dimension=1024)
        try:
            hits=self.dense.search(question)
            docs={r['chunk_id']:r for r in data.load_chunks()}
            if any(h['chunk_id'] not in docs for h in hits):raise DenseUnavailable('BGE_IDENTITY_CONFLICT')
            # All admitted dense passages must satisfy the same contextual/topic
            # constraints as BM25, never bypass them on the strength of a cosine.
            all_lexical,_=data.retrieve(question,fen,intent,96)
            admissible={r['chunk_id'] for r in all_lexical if not data.injection(r['text'])}
            dense=[h['chunk_id'] for h in hits if h['chunk_id'] in admissible]
            scores={}
            for ranking in ([r['chunk_id'] for r in lexical],dense):
                for rank,ident in enumerate(ranking,1):scores[ident]=scores.get(ident,0)+1/(60+rank)
            ids=sorted(scores,key=lambda ident:(-scores[ident],ident))[:3]
            trace.update(method='hybrid_bm25_bge_v3',dense_status='ready',dense_reason='BGE_READ_ONLY_SEARCH_VERIFIED',dense_hits=hits,dense_admitted_ids=dense,rrf_scores=[{'chunk_id':i,'score':scores[i]} for i in ids])
            return done([docs[i] for i in ids],None)
        except DenseUnavailable as error:
            trace.update(method='bm25_fallback_v3',dense_status='unavailable',dense_reason=str(error))
            return done(lexical,None)
