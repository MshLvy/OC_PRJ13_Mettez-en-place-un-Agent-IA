"""I09/A grounded schema, no generator, model or external HTTP."""
import pytest
from app.conversation_mistral import validate_output,build_prompt
from app.conversation import ConversationService
from test_conversation import request

def evidence():return ConversationService().ask(request(request_generation=False)).passages

def answer(e,**kw):return dict(scope='position',abstain=False,paragraphs=[{'text':'Le pion c5 contrôle d4.', 'citation_ids':[e[0].chunk_id]}],moves_uci=[],**kw)

def test_shared_prompt_keeps_all_untrusted_data_in_user_message():
    e=evidence();messages=build_prompt('QUESTION DE TEST',request().fen,e,history=request().history)
    assert 'QUESTION DE TEST' not in messages[0]['content'] and e[0].text not in messages[0]['content']
    assert 'untrusted_evidence' in messages[1]['content'] and 'CC-BY-SA-4.0' in messages[1]['content']
    assert validate_output(answer(e),request().fen,e).paragraphs

@pytest.mark.parametrize('change',[{'scope':'opening_theory'},{'paragraphs':[{'text':'X','citation_ids':['invented']}]},{'moves_uci':['e2e5']},{'paragraphs':[{'text':'Jouez e2e5','citation_ids':[]}]},{'abstain':True}])
def test_shared_output_rejects_unsupported_or_illegal(change):
    e=evidence();raw=answer(e);raw.update(change)
    with pytest.raises(ValueError):validate_output(raw,request().fen,e)

def test_explicit_model_abstention():
    e=evidence();assert validate_output({'scope':'position','abstain':True,'paragraphs':[],'moves_uci':[]},request().fen,e).abstain

def test_theory_cannot_propose_current_position_moves():
    e=evidence()
    for p in e:p.scope='opening_theory'
    raw=answer(e);raw.update(scope='opening_theory',moves_uci=['g1f3'])
    with pytest.raises(ValueError):validate_output(raw,request().fen,e,intent='opening_theory')

def test_legal_uci_sequence_is_validated_without_playing_it():
    e=evidence();raw=answer(e);raw['moves_uci']=['g1f3','d7d6']
    assert validate_output(raw,request().fen,e).moves_uci==['g1f3','d7d6']

def test_prose_cannot_hide_an_undeclared_uci_move():
    e=evidence();raw=answer(e);raw['paragraphs'][0]['text']='Jouez e2e5.'
    with pytest.raises(ValueError,match='UNDECLARED_UCI'):validate_output(raw,request().fen,e)
