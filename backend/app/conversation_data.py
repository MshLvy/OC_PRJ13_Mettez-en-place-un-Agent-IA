"""Frozen public V3 copy, self-contained in the existing backend image. No SDK."""
from collections import Counter
from functools import lru_cache
import hashlib,json,math,re,unicodedata
from pathlib import Path
import chess

DATA=Path(__file__).with_name('data')/'advisor_v3/chunks.json'
SHA='7eb6b10749b1d09985139cb4fa89a5f2b11d75aa4ae2499e4614937923f86064'
VERSION='pilot-fr-v3-enriched-0.1'
STOP=set('le la les un une des de du et ou au aux en dans pour par sur avec ce cette ces qui que quel quelle quels quelles comment pourquoi est sont se je tu il elle on nous mon mes son sa ses a l d ne pas me fait faire moi expliquer explique qu n s t comprendre ouverture defense'.split())
ALIASES={'sicilienne':('sicilienne','sicilian'),'francaise':('francaise','french'),'caro-kann':('caro kann',),'espagnole':('espagnole','ruy lopez'),'italienne':('italienne','italian'),'gambit-dame-refuse':('gambit dame refuse','gambit de la dame refuse'),'scandinave':('scandinave',),'pirc':('pirc',),'ecossaise':('ecossaise','scotch'),'viennoise':('viennoise',),'anglaise':('anglaise','english'),'slave':('slave','slav')}
def normalize(text):return ' '.join(re.findall(r'[a-z0-9]+',''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))))
def tokens(text):return [t for t in normalize(text).split() if t not in STOP]
def position(fen):return ' '.join(chess.Board(fen).fen(en_passant='legal').split()[:4])
def injection(text):return bool(re.search(r'<\s*(script|system)|\[inst\]',text,re.I) or re.search(r'ignore.{0,40}instruction|oublie.{0,40}instruction|system prompt|message systeme|api.?key|secret|<\s*(script|system)|\[inst\]',normalize(text)))
@lru_cache(maxsize=1)
def load_chunks():
    if DATA.is_symlink() or DATA.stat().st_size>1024*1024:raise ValueError('V3_UNAVAILABLE')
    raw=DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('V3_UNAVAILABLE')
    rows=json.loads(raw)
    if len(rows)!=96 or len({r['chunk_id'] for r in rows})!=96:raise ValueError('V3_UNAVAILABLE')
    for r in rows:
        if r['namespace']!=VERSION or r['licence']!='CC-BY-SA-4.0' or r['human_review']!='pending' or r['production_approved'] is not False or hashlib.sha256(r['text'].encode()).hexdigest()!=r['text_sha256']:raise ValueError('V3_UNAVAILABLE')
    return rows

def retrieve(question,fen,intent='position',limit=3):
    """BM25 k1=1.2,b=.75; exact-position + topic admission, not calibrated confidence."""
    docs=load_chunks();nq=normalize(question)
    named={f for f,names in ALIASES.items() if any(' '+name+' ' in ' '+nq+' ' for name in names)}
    compatible=docs if intent=='opening_theory' else [r for r in docs if position(r['fen'])==position(fen)]
    families={r['family'] for r in compatible}
    codes=set(re.findall(r'\b[a-e][0-9]{2}\b',nq))
    if codes and not codes<={m['eco'].lower() for r in compatible for m in r['opening_reference']['matches']}:return [],'POSITION_SCOPE_MISMATCH'
    if len(named)>1 or intent=='opening_theory' and not named:return [],'CLARIFY_OPENING'
    if named and not named&families:return [],'POSITION_SCOPE_MISMATCH'
    selected=named or families
    if len(selected)!=1:return [],'CLARIFY_OPENING'
    family=next(iter(selected));query=set(tokens(question))-set(tokens(family))
    # A family name alone is not evidence that the requested idea is covered.
    if not query:return [],'INSUFFICIENT_EVIDENCE'
    corpus=[tokens(r['text']) for r in docs];avg=sum(map(len,corpus))/len(corpus);df=Counter(t for ts in corpus for t in set(ts));ranked=[]
    for row,ts in zip(docs,corpus):
        if row['family']!=family or (intent=='position' and position(row['fen'])!=position(fen)) or (codes and not codes&{m['eco'].lower() for m in row['opening_reference']['matches']}) or injection(row['text']):continue
        tf=Counter(ts);score=0
        for t in query:
            if tf[t]:score+=math.log(1+(len(docs)-df[t]+.5)/(df[t]+.5))*tf[t]*2.2/(tf[t]+1.2*(.25+.75*len(ts)/avg))
        if score>0:ranked.append((score,row))
    ranked.sort(key=lambda x:(-x[0],x[1]['chunk_id']))
    return [r for _,r in ranked[:limit]],None if ranked else 'INSUFFICIENT_EVIDENCE'
