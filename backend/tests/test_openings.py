"""Référence officielle locale ; ambiguïtés artificielles explicitement isolées."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from types import MappingProxyType
from unittest.mock import Mock

import chess
import pytest
from fastapi.testclient import TestClient

from app.game import GameError, snapshot
from app.main import create_app
from app.openings import (Catalog, Candidate, DATA, OpeningIdentifier, canonical_candidates,
                          load_catalog, position_key, read_catalog)

ROOT = Path(__file__).resolve().parents[2]
SICILIAN = ['e2e4', 'c7c5']
NAJDORF = SICILIAN + ['g1f3','d7d6','d2d4','c5d4','f3d4','g8f6','b1c3','a7a6']


def identify(history):
    return OpeningIdentifier().identify(history)


def board(history):
    b=chess.Board()
    for move in history:b.push_uci(move)
    return b


@pytest.mark.parametrize('history,eco,name,status',[
    (SICILIAN,'B20','Sicilian Defense','family_only'),
    (['e2e4','e7e5','g1f3','b8c6','f1b5'],'C60','Ruy Lopez','family_only'),
    (['e2e4','e7e5','g1f3','b8c6','f1c4'],'C50','Italian Game','family_only'),
    (['d2d4','d7d5','c2c4'],'D06',"Queen's Gambit",'family_only'),
    (['d2d4','g8f6','g1f3','d7d5','c1f4'],'D02',"Queen's Pawn Game: London System",'identified'),
    (NAJDORF,'B90','Sicilian Defense: Najdorf Variation','identified'),
])
def test_reference_names_are_exact(history,eco,name,status):
    d=identify(history)
    assert d.status==status and d.eco==eco and d.full_name==name
    assert d.last_matched_ply==len(history) and d.is_current_match
    assert d.position_fen==board(history).fen(en_passant='fen')
    assert d.snapshot==snapshot(history)
    # Le nom et ECO proviennent bien d'une ligne de l'index source, pas du test.
    catalog=load_catalog()
    assert any(c.eco==eco and c.full_name==name for c in catalog.positions[position_key(board(history))])


def test_initial_and_no_named_position_are_unknown():
    for history in ([],['h2h3','h7h6']):
        d=identify(history)
        if history:
            # Certaines premières poussées de pion ont un nom A00 ; ne pas supposer unknown.
            assert d.position_fen==board(history).fen(en_passant='fen')
        else:assert d.status=='unknown' and d.eco is None and d.last_matched_ply is None
    empty=replace(load_catalog(),positions=MappingProxyType({}))
    d=OpeningIdentifier(lambda:empty).identify(SICILIAN)
    assert d.status=='unknown' and not d.possible_candidates and d.eco is None


def test_family_only_does_not_invent_najdorf_from_c5():
    d=identify(SICILIAN)
    assert d.family=='Sicilian Defense' and d.variation is None
    assert d.display_family=='Défense sicilienne' and d.language=='fr'


def test_only_six_editorial_family_translations_no_free_variant_translation():
    c=load_catalog();assert len(c.translations)==6
    d=identify(NAJDORF)
    assert d.display_family=='Défense sicilienne' and d.variation=='Najdorf Variation' and d.language=='mixed'
    d=identify(['d2d4','g8f6','g1f3','d7d5','c1f4'])
    assert d.language=='en' and d.display_family=="Queen's Pawn Game"


def test_transpositions_identical_key_and_classification():
    a=['d2d4','d7d5','c2c4','e7e6','b1c3','g8f6']
    b=['d2d4','g8f6','c2c4','e7e6','b1c3','d7d5']
    x,y=identify(a),identify(b)
    assert position_key(board(a))==position_key(board(b))
    assert x.is_current_match and y.is_current_match
    assert (x.status,x.eco,x.full_name)==(y.status,y.eco,y.full_name)
    assert x.snapshot!=y.snapshot and x.context.history==a and y.context.history==b


def test_transposed_return_to_named_position_ignores_counters_and_illegal_ep():
    h=SICILIAN+['g1f3','b8c6','f3g1','c6b8']
    a,b=identify(SICILIAN),identify(h)
    assert (a.eco,a.full_name)==(b.eco,b.full_name)==('B20','Sicilian Defense')
    assert a.position_fen!=b.position_fen and b.is_current_match and b.last_matched_ply==6


def test_latest_named_position_not_longest_source_prefix():
    d=identify(NAJDORF)
    assert d.last_matched_ply==10 and d.eco=='B90'
    # Ordre légal alternatif vers la même Najdorf, pas le préfixe de PGN source.
    h=['e2e4','c7c5','g1f3','d7d6','b1c3','g8f6','d2d4','c5d4','f3d4','a7a6']
    e=identify(h)
    assert position_key(board(NAJDORF))==position_key(board(h))
    assert e.full_name==d.full_name and e.eco==d.eco and e.last_matched_ply==10


def test_off_book_preserves_only_last_named_anchor():
    c=load_catalog();h=list(NAJDORF);b=board(h)
    # Un coup légal non nommé dans la référence réelle, choisi de façon déterministe.
    move=next(m for m in sorted(b.legal_moves,key=lambda m:m.uci()) if position_key(_after(b,m)) not in c.positions)
    h.append(move.uci());d=identify(h)
    assert d.last_matched_ply==10 and not d.is_current_match and d.off_line_since_ply==11
    assert d.position_fen==board(h).fen(en_passant='fen')
    assert d.matched_position_fen==board(NAJDORF).fen(en_passant='fen')
    assert d.eco=='B90' and d.variation=='Najdorf Variation'


def _after(b,m):
    result=b.copy();result.push(m);return result


def test_undo_and_reset_rebuild_no_stale_classification():
    x=OpeningIdentifier()
    assert x.identify(NAJDORF).eco=='B90'
    assert x.identify(SICILIAN).eco=='B20'
    assert x.identify([]).status=='unknown'
    assert x.identify(NAJDORF).eco=='B90'


@pytest.mark.parametrize('kind',['side','castling','legal_ep','irrelevant_counters','illegal_ep'])
def test_position_key_contract(kind):
    b=board(['e2e4','a7a6','e4e5','d7d5']) if kind=='legal_ep' else board(['e2e4'])
    other=b.copy()
    if kind=='side':other.turn=not b.turn
    elif kind=='castling':other.castling_rights=0
    elif kind=='legal_ep':assert b.has_legal_en_passant();other.ep_square=None
    elif kind=='irrelevant_counters':other.halfmove_clock=47;other.fullmove_number=60
    else:assert not b.has_legal_en_passant();other.ep_square=None
    assert (position_key(b)==position_key(other))==(kind in ('irrelevant_counters','illegal_ep'))
    assert len(position_key(b).split())==4


def synthetic_catalog(candidates):
    return replace(load_catalog(),positions=MappingProxyType({position_key(board(SICILIAN)):tuple(candidates)}))


def candidate(eco='B20',name='Sicilian Defense: Artificial One',line=2):
    f,_,v=name.partition(':')
    return Candidate(eco=eco,full_name=name,family=f.strip(),variation=v.strip() or None,source_file='b.tsv',source_line=line)


def test_synthetic_ambiguity_not_arbitrary_variant_and_deterministic_order():
    items=[candidate(name='Sicilian Defense: Artificial Z',line=3),candidate(name='Sicilian Defense: Artificial A')]
    a=OpeningIdentifier(lambda:synthetic_catalog(items)).identify(SICILIAN)
    b=OpeningIdentifier(lambda:synthetic_catalog(list(reversed(items)))).identify(SICILIAN)
    assert a.model_dump()==b.model_dump()
    assert a.status=='ambiguous' and a.variation is None and a.full_name is None
    assert a.family=='Sicilian Defense' and a.eco=='B20' and a.candidate_count==2


def test_synthetic_conflicting_families_codes_not_invented():
    items=[candidate(),candidate('C00','French Defense: Artificial',3)]
    d=OpeningIdentifier(lambda:synthetic_catalog(items)).identify(SICILIAN)
    assert d.status=='ambiguous' and d.family is None and d.eco is None and d.variation is None


def test_synthetic_equivalent_designations_dedup_and_first_row():
    items=[candidate(line=7),candidate(line=2)]
    assert canonical_candidates(items)==canonical_candidates(reversed(items))
    d=OpeningIdentifier(lambda:synthetic_catalog(items)).identify(SICILIAN)
    assert d.status=='identified' and d.candidate_count==1 and d.possible_candidates[0].source_line==2


def test_synthetic_candidates_bounded_without_losing_ambiguity_count():
    items=[candidate(name='Sicilian Defense: Artificial '+str(i),line=i+2) for i in range(12)]
    d=OpeningIdentifier(lambda:synthetic_catalog(items)).identify(SICILIAN)
    assert d.status=='ambiguous' and len(d.possible_candidates)==8 and d.candidate_count==12 and d.candidates_truncated


@pytest.mark.parametrize('failure',[None,OSError('private-path'),ValueError('invalid-catalog')])
def test_catalog_unavailable_safe_and_no_fallback(failure):
    def loader():
        if failure:raise failure
    d=OpeningIdentifier(loader).identify(SICILIAN)
    assert d.status=='catalog_unavailable' and d.reference_revision is None and d.eco is None
    assert d.context.fen==board(SICILIAN).fen(en_passant='fen') and 'private-path' not in d.model_dump_json()


def test_catalog_hash_integrity_failure_is_unavailable(tmp_path):
    # Répertoire incomplet : pas d'acquisition ni de recherche ailleurs.
    (tmp_path/'manifest.json').write_bytes((DATA/'manifest.json').read_bytes())
    d=OpeningIdentifier(lambda:read_catalog(tmp_path)).identify(SICILIAN)
    assert d.status=='catalog_unavailable'


def test_catalog_is_complete_at_pinned_revision_and_build_reproducible():
    spec=importlib.util.spec_from_file_location('opening_builder',ROOT/'tools/openings/build_catalog.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    index,manifest=module.build()
    assert index==(DATA/'catalog.json').read_bytes() and manifest==(DATA/'manifest.json').read_bytes()
    c=read_catalog();assert c.reference.rows==c.reference.positions==3865 and c.reference.ambiguous_positions==0
    assert c.reference.revision=='a6189a30dc273ccb21fc2536a9a2fefd5592a67a'


@pytest.mark.parametrize('payload',[
    {'fen':chess.STARTING_FEN},{'history':['e4']},{'history':['e2e5']},{'history':['e7e5']},
    {'history':['a1a2']},{'history':['e2e4']*257},{'history':None},{'history':['e2e4'],'demo_mode':'live'},
])
def test_route_invalid_inputs_no_echo_and_no_fen_only(payload,monkeypatch):
    monkeypatch.setenv('EXPLORER_MODE','disabled');monkeypatch.setenv('STOCKFISH_ENABLED','false')
    app=create_app()
    with TestClient(app) as c:
        r=c.post('/api/v1/openings/identify',json=payload)
        assert r.status_code==422 and 'input' not in r.text and 'Traceback' not in r.text


def test_no_move_after_terminal_history():
    with pytest.raises(GameError,match='MOVE_AFTER_TERMINAL'):
        identify(['f2f3','e7e5','g2g4','d8h4','a2a3'])


@pytest.mark.parametrize('demo_enabled',['true','false'])
def test_http_local_reference_independent_of_live_flags_and_auth(monkeypatch,demo_enabled):
    for k,v in dict(DEMO_ENABLED=demo_enabled,DEMO_ALLOW_LIVE='false',EXPLORER_MODE='disabled',
        EXPLORER_DEFAULT_MODE='disabled',STOCKFISH_ENABLED='false',ANALYSIS_DEFAULT_ENGINE='false',GAME_ALLOW_TOOLS='false',YOUTUBE_MODE='disabled').items():monkeypatch.setenv(k,v)
    app=create_app();forbidden=Mock(side_effect=AssertionError('OPENING_EXTERNAL_TOOL'))
    app.state.stockfish.evaluate=forbidden;app.state.explorer.moves=forbidden;app.state.orchestrator.invoke=forbidden
    with TestClient(app) as c:
        r=c.post('/api/v1/openings/identify',json={'history':SICILIAN})
        assert r.status_code==200
        d=r.json();assert d['eco']=='B20' and d['display_family']=='Défense sicilienne'
        assert d['context']['history']==SICILIAN and d['context']['certainty']=='family_only'
    forbidden.assert_not_called()


def test_unavailable_http_still_returns_validated_position(monkeypatch):
    app=create_app();app.state.openings=OpeningIdentifier(lambda:None)
    with TestClient(app) as c:
        r=c.post('/api/v1/openings/identify',json={'history':SICILIAN})
        assert r.status_code==200 and r.json()['status']=='catalog_unavailable'
        assert r.json()['revision']==2 and r.json()['snapshot']==snapshot(SICILIAN)


def test_deepest_real_reference_entry():
    entries=json.loads((DATA/'catalog.json').read_text())['entries']
    row=max(entries,key=lambda e:len(e['uci']))
    d=identify(row['uci'])
    assert len(row['uci'])>10 and d.is_current_match and d.last_matched_ply==len(row['uci'])
    assert (d.eco,d.full_name)==(row['eco'],row['name'])


def test_latest_ambiguity_not_replaced_by_earlier_unique_synthetic_catalog():
    c=load_catalog();positions={position_key(board(['e2e4'])):(candidate(),),
        position_key(board(SICILIAN)):(candidate(name='Sicilian Defense: Artificial A'),candidate(name='Sicilian Defense: Artificial B',line=3))}
    d=OpeningIdentifier(lambda:replace(c,positions=MappingProxyType(positions))).identify(SICILIAN)
    assert d.status=='ambiguous' and d.last_matched_ply==2 and d.variation is None


@pytest.mark.parametrize('asset',['catalog.json','translations.fr.json','upstream/b.tsv'])
def test_modified_asset_hash_cannot_classify(tmp_path,asset):
    import shutil
    shutil.copytree(DATA,tmp_path/'catalog')
    root=tmp_path/'catalog';path=root/asset;path.write_bytes(path.read_bytes()+b' ')
    d=OpeningIdentifier(lambda:read_catalog(root)).identify(SICILIAN)
    assert d.status=='catalog_unavailable' and d.eco is None
