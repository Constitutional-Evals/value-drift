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


def render_token_prompts(tokenizer, conversations, options, max_model_len):
    prompts = []
    for messages in conversations:
        ids = tokenizer.apply_chat_template(messages, tokenize=True,
            add_generation_prompt=True, enable_thinking=options['enable_thinking'],
            tools=options['tools'], return_dict=False)
        ids = normalize_token_ids(ids)
        if len(ids) > options['max_input_tokens']:
            raise ValueError('Input exceeds limit; refusing silent prompt truncation')
        if len(ids) + options['max_new_tokens'] > max_model_len:
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

    def generate_batch(self, conversations, options):
        from vllm import SamplingParams
        options={'presence_penalty':0.0, 'json_schema':None, **options}
        allowed = {'enable_thinking', 'max_new_tokens', 'temperature', 'top_p', 'top_k',
                   'tools', 'max_input_tokens', 'presence_penalty', 'json_schema'}
        if set(options) != allowed:
            raise ValueError('Generation options do not match the session protocol')
        thinking = options['enable_thinking']
        tools = options['tools']
        max_new = options['max_new_tokens']
        if max_new <= 0:
            raise ValueError('max_new_tokens must be positive')
        # Render exactly once using the checkpoint tokenizer. Passing token IDs to
        # vLLM.generate avoids a second processor/template changing tool markup.
        prompts = render_token_prompts(self.tokenizer, conversations, options, self.options['max_model_len'])
        # Identical self-interaction prompts still need independent samples.
        # The counter persists within this model session, not across process resume.
        seeds = [self.options['seed'] + self.request_counter + i for i in range(len(prompts))]
        structured={}
        if options['json_schema'] is not None:
            from vllm.sampling_params import StructuredOutputsParams
            structured={'structured_outputs':StructuredOutputsParams(json=options['json_schema'])}
        params = [SamplingParams(max_tokens=max_new, temperature=options['temperature'],
            top_p=options['top_p'], top_k=options['top_k'], seed=seed,
            presence_penalty=options['presence_penalty'],
            skip_special_tokens=False, stop_token_ids=sorted(self.eos_ids), ignore_eos=False, **structured)
            for seed in seeds]
        self.request_counter += len(prompts)
        started = time.monotonic()
        outputs = self.llm.generate(prompts, sampling_params=params, use_tqdm=False)
        duration = time.monotonic() - started
        results = []
        for output, seed in zip(outputs, seeds):
            if len(output.outputs) != 1:
                raise ValueError('Expected exactly one completion per request')
            result = completion_result(output.outputs[0], self.tokenizer, self.eos_ids, thinking, duration)
            result['generation_seed'] = seed
            results.append(result)
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
