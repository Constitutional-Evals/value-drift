"""Small isolated vLLM worker. Run via VLLMSession, never inside training Python.

Sampling seeds are base_seed plus a monotonically increasing session request index,
recorded per result. Restarting a partially completed generation stage resets this
index for the remaining requests; resume therefore is not bitwise identical to an
uninterrupted run. Completed cached responses are never regenerated to hide this.
"""
from __future__ import annotations
import argparse
import json
import os
import socket
import time
import traceback
from .model import final_text
from .train import normalize_token_ids

MAX_FRAME_BYTES = 64 * 1024 * 1024
DEFAULT_ENGINE_OPTIONS = {
    'runner': 'generate', 'model_impl': 'vllm', 'dtype': 'bfloat16',
    'quantization': None, 'trust_remote_code': False, 'tensor_parallel_size': 1,
    'language_model_only': True, 'max_model_len': 32768, 'max_num_seqs': 32,
    'max_num_batched_tokens': 4096, 'enable_chunked_prefill': True,
    'enable_prefix_caching': False, 'gpu_memory_utilization': 0.70,
    'enforce_eager': False, 'max_cudagraph_capture_size': 32,
    'generation_config': 'vllm', 'seed': 20260915,
}


def validate_engine_options(options):
    unknown = set(options) - set(DEFAULT_ENGINE_OPTIONS)
    if unknown:
        raise ValueError(f'Unsupported engine options: {sorted(unknown)}')
    result = {**DEFAULT_ENGINE_OPTIONS, **options}
    fixed = {'runner': 'generate', 'model_impl': 'vllm', 'dtype': 'bfloat16',
             'quantization': None, 'trust_remote_code': False, 'tensor_parallel_size': 1,
             'language_model_only': True, 'generation_config': 'vllm'}
    for key, value in fixed.items():
        if result[key] != value:
            raise ValueError(f'This text-only full-weight inference backend requires {key}={value!r}')
    if not 0 < result['gpu_memory_utilization'] < 1:
        raise ValueError('gpu_memory_utilization must be between zero and one')
    return result


def completion_result(completion, tokenizer, eos_ids, enable_thinking, duration):
    if completion.finish_reason not in {'stop', 'length'}:
        raise ValueError(f'Unexpected vLLM completion finish reason: {completion.finish_reason!r}')
    tokens = list(completion.token_ids)
    # vLLM retains the terminal stop ID in token_ids even when text hides it.
    end = next((i for i, token in enumerate(tokens) if token in eos_ids), len(tokens))
    raw = tokenizer.decode(tokens[:end], skip_special_tokens=False)
    return {'text': final_text(raw, enable_thinking), 'raw_text': raw,
            'finish_reason': completion.finish_reason,
            'stop_reason': completion.stop_reason,
            'generated_tokens': len(tokens), 'batch_seconds': duration,
            'enable_thinking': enable_thinking}


# The generation options VLLMSession sends with every request.
SESSION_OPTIONS = frozenset({'enable_thinking', 'max_new_tokens', 'temperature', 'top_p', 'top_k',
                             'tools', 'max_input_tokens', 'presence_penalty', 'json_schema',
                             'assistant_prefix', 'thinking_budget'})

# Qwen3's own way to end thinking at a budget (Qwen3 technical report, "thinking budget").
THINKING_BUDGET_END = ('\n\nConsidering the limited time by the user, I have to give the solution '
                       'based on the thinking directly now.\n</think>\n\n')


def render_token_prompts(tokenizer, conversations, options, max_model_len):
    """Token prompts, each followed by options['assistant_prefix'] (the start of the assistant turn).

    With thinking on, a prefix is placed inside the thinking block; '<think>\\n' is added to it
    only if the template has not already opened the block.
    """
    prefix = options.get('assistant_prefix')
    allowance = options['max_new_tokens']
    if options.get('thinking_budget'):
        allowance += options['thinking_budget'] + len(tokenizer.encode(THINKING_BUDGET_END, add_special_tokens=False))
    prompts = []
    for messages in conversations:
        ids = tokenizer.apply_chat_template(messages, tokenize=True,
            add_generation_prompt=True, enable_thinking=options['enable_thinking'],
            tools=options['tools'], return_dict=False)
        ids = normalize_token_ids(ids)
        if prefix:
            text = tokenizer.apply_chat_template(messages, tokenize=False,
                add_generation_prompt=True, enable_thinking=options['enable_thinking'], tools=options['tools'])
            opened = prefix if not options['enable_thinking'] or text.rstrip('\n').endswith('<think>') \
                else '<think>\n' + prefix
            ids = ids + tokenizer.encode(opened, add_special_tokens=False)
        if len(ids) > options['max_input_tokens']:
            raise ValueError('Input exceeds limit; refusing silent prompt truncation')
        if len(ids) + allowance > max_model_len:
            raise ValueError('Input plus output allowance exceeds max_model_len')
        prompts.append({'prompt_token_ids': ids})
    return prompts


class WorkerEngine:
    def __init__(self, checkpoint, options):
        import torch
        import vllm
        from vllm import LLM
        self.options = validate_engine_options(options)
        self.request_counter = 0
        self.llm = LLM(model=checkpoint, tokenizer=checkpoint, **self.options)
        self.tokenizer = self.llm.get_tokenizer()
        text_config = self.llm.model_config.hf_text_config
        configured = getattr(text_config, 'eos_token_id', None)
        self.eos_ids = set(configured if isinstance(configured, (list, tuple)) else [configured])
        self.eos_ids.add(self.tokenizer.eos_token_id)
        self.eos_ids.add(self.tokenizer.convert_tokens_to_ids('<|im_end|>'))
        self.eos_ids.discard(None)
        self.metadata = {'backend': 'vllm', 'vllm_version': vllm.__version__,
                         'torch_version': torch.__version__, 'cuda_version': torch.version.cuda,
                         'checkpoint': checkpoint, 'engine_options': self.options,
                         'eos_token_ids': sorted(self.eos_ids)}

    def _sample(self, prompts, max_tokens, options, stop_ids, structured):
        """One vLLM pass with the next session seeds; returns (completions, seeds, seconds)."""
        from vllm import SamplingParams
        # Identical self-interaction prompts still need independent samples.
        # The counter persists within this model session, not across process resume.
        seeds = [self.options['seed'] + self.request_counter + i for i in range(len(prompts))]
        params = [SamplingParams(max_tokens=max_tokens, temperature=options['temperature'],
            top_p=options['top_p'], top_k=options['top_k'], seed=seed,
            presence_penalty=options['presence_penalty'],
            skip_special_tokens=False, stop_token_ids=sorted(stop_ids), ignore_eos=False, **structured)
            for seed in seeds]
        self.request_counter += len(prompts)
        started = time.monotonic()
        outputs = self.llm.generate(prompts, sampling_params=params, use_tqdm=False)
        duration = time.monotonic() - started
        if any(len(output.outputs) != 1 for output in outputs):
            raise ValueError('Expected exactly one completion per request')
        return [output.outputs[0] for output in outputs], seeds, duration

    def generate_batch(self, conversations, options):
        options={'presence_penalty':0.0, 'json_schema':None, 'assistant_prefix':None, 'thinking_budget':None, **options}
        if set(options) != SESSION_OPTIONS:
            raise ValueError('Generation options do not match the session protocol')
        thinking = options['enable_thinking']
        max_new = options['max_new_tokens']
        budget = options['thinking_budget']
        if max_new <= 0:
            raise ValueError('max_new_tokens must be positive')
        if budget is not None and (not thinking or budget <= 0 or options['json_schema'] is not None):
            raise ValueError('thinking_budget needs thinking on, a positive budget and no json_schema')
        # Render exactly once using the checkpoint tokenizer. Passing token IDs to
        # vLLM.generate avoids a second processor/template changing tool markup.
        prompts = render_token_prompts(self.tokenizer, conversations, options, self.options['max_model_len'])
        prefix = options['assistant_prefix'] or ''
        if budget is not None:
            return self._generate_with_thinking_budget(prompts, prefix, budget, options)
        structured={}
        if options['json_schema'] is not None:
            from vllm.sampling_params import StructuredOutputsParams
            structured={'structured_outputs':StructuredOutputsParams(json=options['json_schema'])}
        completions, seeds, duration = self._sample(prompts, max_new, options, self.eos_ids, structured)
        results = []
        end_id = self.tokenizer.convert_tokens_to_ids('</think>') if thinking else None
        for completion, seed in zip(completions, seeds):
            result = completion_result(completion, self.tokenizer, self.eos_ids, thinking, duration)
            if thinking and isinstance(end_id, int):
                tokens = list(completion.token_ids)
                result['thinking_closed_by'] = 'model' if end_id in tokens else None
                result['thinking_tokens'] = tokens.index(end_id) + 1 if end_id in tokens else len(tokens)
            if prefix:
                result['raw_text'] = prefix + result['raw_text']
                result['text'] = final_text(result['raw_text'], thinking)
            result['generation_seed'] = seed
            results.append(result)
        return results

    def _generate_with_thinking_budget(self, prompts, prefix, budget, options):
        """Think for at most `budget` tokens, then answer with up to max_new_tokens.

        One pass generates the thinking and the answer together (up to budget + max_new_tokens), so
        each prompt is read once. A response whose thinking closes within the budget keeps its answer,
        cut at max_new_tokens and marked 'length' if longer, exactly as that cap would have ended it.
        Only responses whose thinking runs past the budget get a second pass: their first `budget`
        thinking tokens, THINKING_BUDGET_END, and a fresh answer. A turn that ends inside its thinking
        has no answer and returns empty text.
        """
        end_id = self.tokenizer.convert_tokens_to_ids('</think>')
        if not isinstance(end_id, int) or end_id == self.tokenizer.unk_token_id:
            raise ValueError('thinking_budget needs a single </think> token')
        max_new = options['max_new_tokens']
        first, seeds, seconds = self._sample(prompts, budget + max_new, options, self.eos_ids, {})
        forced = self.tokenizer.encode(THINKING_BUDGET_END, add_special_tokens=False)
        results, pending = [None] * len(prompts), []
        for i, (completion, seed) in enumerate(zip(first, seeds)):
            tokens = list(completion.token_ids)
            eos_at = next((k for k, token in enumerate(tokens) if token in self.eos_ids), len(tokens))
            close = tokens.index(end_id) if end_id in tokens[:min(budget, eos_at)] else None
            if close is not None:
                thought, answer = tokens[:close + 1], tokens[close + 1:]
                answer_end = next((k for k, token in enumerate(answer) if token in self.eos_ids), None)
                if answer_end is not None and answer_end < max_new:
                    answer, finish, stop = answer[:answer_end + 1], 'stop', answer[answer_end]
                else:
                    answer, finish, stop = answer[:max_new], 'length', None
                visible = [token for token in answer if token not in self.eos_ids]
                raw = prefix + self.tokenizer.decode(thought + visible, skip_special_tokens=False)
                results[i] = {'text': final_text(raw, True), 'raw_text': raw, 'finish_reason': finish,
                              'stop_reason': stop, 'generated_tokens': len(thought) + len(answer),
                              'batch_seconds': seconds, 'enable_thinking': True, 'generation_seed': seed,
                              'thinking_tokens': len(thought), 'thinking_closed_by': 'model'}
            elif eos_at < budget:
                raw = prefix + self.tokenizer.decode(tokens[:eos_at], skip_special_tokens=False)
                results[i] = {'text': '', 'raw_text': raw, 'finish_reason': 'stop', 'stop_reason': tokens[eos_at],
                              'generated_tokens': eos_at + 1, 'batch_seconds': seconds, 'enable_thinking': True,
                              'generation_seed': seed, 'thinking_tokens': eos_at + 1, 'thinking_closed_by': None}
            else:
                pending.append((i, tokens[:budget] + forced, seed))
        if pending:
            continued = [{'prompt_token_ids': prompts[i]['prompt_token_ids'] + thought} for i, thought, _ in pending]
            answers, answer_seeds, answer_seconds = self._sample(continued, max_new, options, self.eos_ids, {})
            for (i, thought, seed), completion, answer_seed in zip(pending, answers, answer_seeds):
                result = completion_result(completion, self.tokenizer, self.eos_ids, False, seconds + answer_seconds)
                raw = prefix + self.tokenizer.decode(thought, skip_special_tokens=False) + result['raw_text']
                result.update(raw_text=raw, text=final_text(raw, True), enable_thinking=True,
                              generated_tokens=budget + result['generated_tokens'],
                              generation_seed=seed, answer_generation_seed=answer_seed,
                              thinking_tokens=budget, thinking_closed_by='budget')
                results[i] = result
        return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fd', type=int, required=True)
    args = parser.parse_args()
    channel = socket.socket(fileno=args.fd)
    os.set_inheritable(args.fd, False)
    stream = channel.makefile('rwb')
    engine = None
    try:
        while True:
            line = stream.readline(MAX_FRAME_BYTES + 1)
            if not line:
                return
            if len(line) > MAX_FRAME_BYTES or not line.endswith(b'\n'):
                raise ValueError('Oversized or incomplete parent frame')
            request = json.loads(line)
            action = request.get('action')
            try:
                if action == 'initialize':
                    if engine is not None:
                        raise ValueError('Worker already initialized')
                    engine = WorkerEngine(request['checkpoint'], request['engine_options'])
                    response = {'ok': True, 'metadata': engine.metadata}
                elif action == 'generate':
                    if engine is None:
                        raise ValueError('Worker is not initialized')
                    response = {'ok': True, 'results': engine.generate_batch(request['conversations'], request['options'])}
                elif action == 'close':
                    response = {'ok': True}
                else:
                    raise ValueError('Unknown worker action')
            except Exception as exc:
                traceback.print_exc()
                response = {'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)}
            response['request_id'] = request.get('request_id')
            stream.write((json.dumps(response, ensure_ascii=False) + '\n').encode())
            stream.flush()
            if action == 'close' or not response['ok']:
                return
    finally:
        stream.close()
        channel.close()

if __name__ == '__main__':
    main()
