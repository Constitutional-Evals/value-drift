from types import SimpleNamespace
import sys

import pytest

from recursive_oct.backend import execute_review
from recursive_oct.model import ModelSession
from recursive_oct.vllm_session import VLLMSession
from recursive_oct.vllm_worker import WorkerEngine


FINISH='<tool_call><function=finish_editing><parameter=decision_summary>Endorsed.</parameter></function></tool_call>'


@pytest.mark.parametrize('penalty', [None, 0.0, 1.5])
def test_review_presence_penalty_reaches_worker_sampling_params(tmp_path, monkeypatch, penalty):
    captured=[]
    monkeypatch.setitem(sys.modules,'vllm',SimpleNamespace(SamplingParams=lambda **kw:SimpleNamespace(**kw)))
    worker=object.__new__(WorkerEngine)
    worker.options={'seed':42,'max_model_len':32768}
    worker.request_counter=0
    worker.eos_ids={99}
    worker.tokenizer=SimpleNamespace(apply_chat_template=lambda *a,**kw:[1], decode=lambda *a,**kw:FINISH)
    def generate(prompts,sampling_params,**kw):
        captured.extend(sampling_params)
        return [SimpleNamespace(outputs=[SimpleNamespace(token_ids=[2,99],finish_reason='stop',stop_reason=99)])]
    worker.llm=SimpleNamespace(generate=generate)
    session=VLLMSession('M0')
    session._exchange=lambda request:{'results':worker.generate_batch(request['conversations'],request['options'])}
    cfg={} if penalty is None else {'presence_penalty':penalty}
    result=execute_review(session,'M0','Constitution',tmp_path,cfg)
    assert result['status']=='SELF_DECLARED_CONVERGENCE'
    assert captured[0].presence_penalty==(0.0 if penalty is None else penalty)
    assert captured[0].temperature==0.7


def test_transformers_rejects_nonzero_presence_penalty_before_loading():
    session=object.__new__(ModelSession)
    with pytest.raises(ValueError,match='presence_penalty.*vLLM'):
        session.generate_batch([[]],presence_penalty=1.5)
