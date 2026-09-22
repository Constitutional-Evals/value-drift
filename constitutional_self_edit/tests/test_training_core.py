import math
import unittest
from types import SimpleNamespace
from recursive_oct.model import parse_tool_calls, final_text
from recursive_oct.train import encode_completion, encode_sft


class ToyTokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return [1,2,3] + [4] * max(0,len(messages)-1)
    def encode(self, response, **kwargs):
        return [10+ord(c)%5 for c in response]
    def convert_tokens_to_ids(self, token):
        assert token == '<|im_end|>'
        return 9


class FormattingTests(unittest.TestCase):
    def test_mapping_and_single_batch_token_normalization(self):
        from collections import UserDict
        from recursive_oct.train import normalize_token_ids
        self.assertEqual(normalize_token_ids(UserDict(input_ids=[1,2])),[1,2])
        self.assertEqual(normalize_token_ids(UserDict(input_ids=[[1,2]])),[1,2])
        with self.assertRaises(ValueError): normalize_token_ids({'input_ids':[[1],[2]]})

    def test_response_mask_and_eos(self):
        encoded = encode_completion(ToyTokenizer(),[{'role':'user','content':'question'}],'yes',12)
        self.assertEqual(encoded['labels'][:3],[-100]*3)
        self.assertEqual(encoded['input_ids'][-1],9)
        self.assertEqual(encoded['labels'][3:],encoded['input_ids'][3:])
        self.assertFalse(encoded['truncated'])

    def test_truncation_does_not_teach_false_eos(self):
        encoded = encode_completion(ToyTokenizer(),[{'role':'user','content':'question'}],'lengthy',6)
        self.assertTrue(encoded['truncated'])
        self.assertEqual(len(encoded['input_ids']),6)
        self.assertNotEqual(encoded['input_ids'][-1],9)
        with self.assertRaises(ValueError):
            encode_completion(ToyTokenizer(),[{'role':'user','content':'q'}],'yes',4)

    def test_sft_all_assistant_turns_mask_context(self):
        messages = [{'role':'user','content':'q'},{'role':'assistant','content':'a'},
                    {'role':'user','content':'q2'},{'role':'assistant','content':'a2'}]
        examples = encode_sft(ToyTokenizer(),messages,20)
        self.assertEqual(len(examples),2)
        self.assertEqual(examples[1]['labels'][:5],[-100]*5)

    def test_native_tool_parser_preserves_essay(self):
        essay='First paragraph.\n\nSecond paragraph with <ordinary> text.'
        raw=f'<think>Ignore <tool_call>example</tool_call></think>\n<tool_call>\n<function=edit_constitution>\n<parameter=new_text>\n{essay}\n</parameter>\n<parameter=change_summary>\nClearer text.\n</parameter>\n</function>\n</tool_call>'
        calls=parse_tool_calls(raw)
        self.assertEqual(calls,[{'name':'edit_constitution','arguments':{'new_text':essay,'change_summary':'Clearer text.'}}])
        with self.assertRaises(ValueError): parse_tool_calls(raw[:-12])
        self.assertEqual(final_text('unfinished thought',True),'')
        with self.assertRaises(ValueError): parse_tool_calls('<think>hypothetical '+raw.split('</think>',1)[1])
        with self.assertRaises(ValueError): parse_tool_calls(raw+'</tool_call>')
        with self.assertRaises(ValueError): parse_tool_calls(raw+'trailing suffix')
        with self.assertRaises(ValueError): parse_tool_calls('<function=stray>'+raw.split('</think>',1)[1])


try:
    import torch
except ImportError:
    torch=None


@unittest.skipIf(torch is None,'torch not installed; run with requirements-gpu for numeric checks')
class NumericalTests(unittest.TestCase):
    def test_chunked_projection_matches_dense_values_and_gradients(self):
        from recursive_oct.train import sequence_logps
        class Backbone(torch.nn.Module):
            def __init__(self):
                super().__init__(); self.embed=torch.nn.Embedding(20,7)
            def forward(self,input_ids,**kwargs):
                return SimpleNamespace(last_hidden_state=self.embed(input_ids))
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__(); self.model=Backbone(); self.lm_head=torch.nn.Linear(7,20,bias=False)
                self.device=torch.device('cpu')
        torch.manual_seed(12); model=Model()
        encoded={'input_ids':[1,2,3,4,5,6], 'labels':[-100,-100,-100,4,5,6]}
        score,count=sequence_logps(model,encoded,chunk_size=2)
        score.backward(); actual=[p.grad.clone() for p in model.parameters()]
        model.zero_grad()
        ids=torch.tensor([encoded['input_ids']]); h=model.model(input_ids=ids).last_hidden_state
        logits=model.lm_head(h)[0,:-1]
        labels=torch.tensor(encoded['labels'][1:]); keep=labels!=-100
        expected=-torch.nn.functional.cross_entropy(logits[keep],labels[keep],reduction='sum')
        expected.backward()
        self.assertEqual(count,3)
        torch.testing.assert_close(score,expected)
        for got,param in zip(actual,model.parameters()): torch.testing.assert_close(got,param.grad)
        self.assertTrue(all(p.grad is not None for p in model.parameters()))

    def test_official_qwen_hybrid_backbone_text_gradients(self):
        try:
            from transformers import Qwen3_5Config, Qwen3_5ForConditionalGeneration
        except ImportError:
            self.skipTest('Official Qwen Transformers dependency not installed')
        from recursive_oct.train import sequence_logps
        config = Qwen3_5Config(
            text_config=dict(vocab_size=40,hidden_size=32,intermediate_size=64,
                num_hidden_layers=4,num_attention_heads=4,num_key_value_heads=2,head_dim=8,
                linear_key_head_dim=8,linear_value_head_dim=8,linear_num_key_heads=2,
                linear_num_value_heads=4,layer_types=['linear_attention']*3+['full_attention'],
                max_position_embeddings=128,rope_parameters={'rope_type':'default',
                'rope_theta':10000.,'partial_rotary_factor':1.,'mrope_section':[1,1,2]}),
            vision_config=dict(depth=1,hidden_size=32,intermediate_size=64,num_heads=4,
                out_hidden_size=32,patch_size=2,temporal_patch_size=1,spatial_merge_size=1,
                num_position_embeddings=16))
        import importlib.util
        if not torch.cuda.is_available() and importlib.util.find_spec('fla') is not None:
            self.skipTest('Installed FLA kernels require an accelerator')
        model = Qwen3_5ForConditionalGeneration(config).to('cuda' if torch.cuda.is_available() else 'cpu')
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model.train()
        encoded = {'input_ids':[1,2,3,4,5,6], 'labels':[-100,-100,-100,4,5,6]}
        score,n = sequence_logps(model,encoded,2)
        with torch.autocast(device_type=model.device.type,dtype=torch.bfloat16,enabled=model.device.type=='cuda'):
            dense = model(input_ids=torch.tensor([encoded['input_ids']],device=model.device),use_cache=False).logits[0,2:5]
        expected = -torch.nn.functional.cross_entropy(dense.float(),torch.tensor([4,5,6],device=model.device),reduction='sum')
        torch.testing.assert_close(score,expected)
        (-score/n).backward()
        missing = [name for name,p in model.named_parameters() if p.grad is None]
        self.assertTrue(missing)  # Vision is present but naturally inactive.
        self.assertTrue(all(name.startswith('model.visual.') for name in missing))
        self.assertTrue(all(p.requires_grad for p in model.parameters()))

    def test_current_reference_dpo_direction_and_nll(self):
        from recursive_oct.train import dpo_objective
        chosen=torch.tensor(-5.,requires_grad=True); rejected=torch.tensor(-8.,requires_grad=True)
        loss,parts=dpo_objective(chosen,rejected,-5.,-8.,5,beta=.1,nll_coef=.1)
        self.assertAlmostEqual(float(loss.detach()),math.log(2)+.1,places=6)
        loss.backward()
        self.assertLess(float(chosen.grad),0)  # descent raises chosen logp
        self.assertGreater(float(rejected.grad),0)  # descent lowers rejected logp
        self.assertEqual(float(parts['margin']),0)




class ActualTokenizerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from transformers import AutoTokenizer
            cls.tokenizer=AutoTokenizer.from_pretrained('Qwen/Qwen3.5-9B',local_files_only=True)
        except (ImportError,OSError):
            raise unittest.SkipTest('Actual Qwen tokenizer not cached; cache it for tokenizer integration checks')

    def test_actual_batch_encoding_prefix_and_single_terminal(self):
        from recursive_oct.train import normalize_token_ids
        actual_mapping=self.tokenizer.apply_chat_template([{'role':'user','content':'Hello'}],tokenize=True)
        self.assertIsInstance(normalize_token_ids(actual_mapping),list)
        encoded=encode_completion(self.tokenizer,[{'role':'user','content':'Hello'}],
                                  'Hello<|im_end|>\n',128)
        self.assertTrue(all(isinstance(i,int) for i in encoded['input_ids']))
        targets=[i for i in encoded['labels'] if i!=-100]
        self.assertEqual(targets.count(248046),1)
        self.assertEqual(targets[-1],248046)
        self.assertEqual(self.tokenizer.decode(targets[:-1]),'Hello')

    @unittest.skipIf(torch is None,'Torch required for generated-token regression')
    def test_generation_stops_at_chat_eos_despite_model_config_eos(self):
        from recursive_oct.model import ModelSession
        options_seen={}
        tokenizer=self.tokenizer
        class FakeModel:
            generation_config=SimpleNamespace(eos_token_id=248044)
            def generate(self,input_ids,**kwargs):
                options_seen.update(kwargs)
                emitted=torch.tensor([tokenizer.encode('Hello<|im_end|>\n<|endoftext|>',add_special_tokens=False)])
                return torch.cat([input_ids,emitted],dim=1)
        session=ModelSession('unused',device='cpu')
        session.tokenizer=tokenizer;session.model=FakeModel()
        result=session.generate_batch([[{'role':'user','content':'Hello'}]],max_new_tokens=12)[0]
        self.assertIn(248046,options_seen['eos_token_id'])
        self.assertIn(248044,options_seen['eos_token_id'])
        self.assertEqual(result['raw_text'],'Hello')
        self.assertEqual(result['text'],'Hello')
        self.assertEqual(result['finish_reason'],'stop')
        class NoStopModel(FakeModel):
            def generate(self,input_ids,**kwargs):
                return torch.cat([input_ids,torch.tensor([tokenizer.encode('Hello',add_special_tokens=False)])],dim=1)
        session.model=NoStopModel()
        self.assertEqual(session.generate_batch([[{'role':'user','content':'Hello'}]],max_new_tokens=1)[0]['finish_reason'],'length')


if __name__=='__main__': unittest.main()


def test_training_target_truncation_requires_explicit_permission(tmp_path):
    from recursive_oct.train import audit_training_lengths
    import pytest
    examples=[{'input_ids':[1,2,3], 'labels':[-100,2,3], 'truncated':True}]
    with pytest.raises(ValueError,match='truncated'):
        audit_training_lengths(examples, {}, tmp_path)
    audit_training_lengths(examples, {'allow_target_truncation':True}, tmp_path)
    import json
    assert json.loads((tmp_path/'sequence_lengths.json').read_text())['truncated_sequences']==1
