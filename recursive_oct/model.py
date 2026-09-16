"""Official Qwen3.5 interface; imports GPU dependencies only when loading."""
from __future__ import annotations
import gc
import json
import re
import time

BASE_MODEL = 'Qwen/Qwen3.5-9B'


def inference_session(checkpoint, config):
    backend = config.get('backend', 'transformers')
    if backend == 'transformers':
        return ModelSession(checkpoint, attention=config.get('attention', 'sdpa'))
    if backend == 'vllm':
        from .vllm_session import VLLMSession
        return VLLMSession(checkpoint,
            python_executable=config['vllm_python'],
            engine_options=config.get('vllm_engine', {}),
            seed=config.get('seed', 20260915))
    raise ValueError(f'Unknown inference backend: {backend}')


def parse_tool_calls(raw_text: str) -> list[dict]:
    """Parse native qwen3_coder calls, preserving multiline string arguments.

    Incomplete or malformed markup raises; callers must never infer convergence.
    Thinking is excluded because hypothetical calls in reasoning are not actions.
    """
    if raw_text.count('<think>') > raw_text.count('</think>'):
        raise ValueError('Unclosed thinking content is not an action')
    text = raw_text.rsplit('</think>', 1)[-1]
    blocks = re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>', text, re.S)
    if not blocks or text.count('<tool_call>') != len(blocks) or text.count('</tool_call>') != len(blocks):
        raise ValueError('Missing or incomplete tool call')
    matches = list(re.finditer(r'<tool_call>\s*(.*?)\s*</tool_call>', text, re.S))
    outside = text[:matches[0].start()]
    if re.search(r'</?(?:function|parameter|tool_call)(?:=|>)', outside) or text[matches[-1].end():].strip():
        raise ValueError('Stray tool markup or suffix after tool calls')
    if any(text[a.end():b.start()].strip() for a,b in zip(matches,matches[1:])):
        raise ValueError('Unexpected content between tool calls')
    calls = []
    for block in blocks:
        match = re.fullmatch(r'<function=([A-Za-z_][A-Za-z_0-9]*)>\s*(.*?)\s*</function>', block, re.S)
        if not match:
            raise ValueError('Malformed native Qwen function')
        params = {}; body = match[2]; end = 0
        for param in re.finditer(r'<parameter=([A-Za-z_][A-Za-z_0-9]*)>\n?(.*?)\n?</parameter>', body, re.S):
            if body[end:param.start()].strip() or param[1] in params:
                raise ValueError('Malformed or duplicate tool argument')
            params[param[1]] = param[2]
            end = param.end()
        if body[end:].strip():
            raise ValueError('Malformed tool arguments')
        calls.append({'name': match[1], 'arguments': params})
    return calls


def final_text(raw: str, thinking: bool) -> str:
    if '</think>' in raw:
        return raw.rsplit('</think>', 1)[1].strip()
    return '' if thinking else raw.strip()


class ModelSession:
    def __init__(self, checkpoint: str, device='cuda', attention='sdpa', parameter_dtype='bfloat16'):
        self.checkpoint = str(checkpoint)
        self.device = device
        self.attention = attention
        self.parameter_dtype = parameter_dtype
        self.model = self.tokenizer = None

    def __enter__(self):
        import torch
        from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration
        self.tokenizer = AutoTokenizer.from_pretrained(self.checkpoint, trust_remote_code=False)
        self.tokenizer.padding_side = 'left'
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        self.model = Qwen3_5ForConditionalGeneration.from_pretrained(
            self.checkpoint, dtype=getattr(torch, self.parameter_dtype),
            device_map={'': self.device}, attn_implementation=self.attention,
            trust_remote_code=False,
        )
        self.model.eval()
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.model = None
        self.tokenizer = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate_batch(self, conversations, *, enable_thinking=False, max_new_tokens=512,
                       temperature=0.7, top_p=0.8, top_k=20, tools=None,
                       max_input_tokens=16384, **kwargs):
        import torch
        if kwargs:
            raise TypeError(f'Unsupported generation options: {sorted(kwargs)}')
        prompts = [self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            enable_thinking=enable_thinking, tools=tools,
        ) for messages in conversations]
        encoded = self.tokenizer(prompts, padding=True, return_tensors='pt', add_special_tokens=False)
        if encoded.input_ids.shape[1] > max_input_tokens:
            raise ValueError('Input exceeds limit; refusing silent prompt truncation')
        encoded = encoded.to(self.device)
        # The official checkpoint config uses endoftext (248044), while the
        # chat tokenizer ends an assistant turn at im_end (248046). Honor both.
        configured_eos = self.model.generation_config.eos_token_id
        eos = set(configured_eos if isinstance(configured_eos, (list, tuple)) else [configured_eos])
        eos.update([self.tokenizer.eos_token_id, self.tokenizer.convert_tokens_to_ids('<|im_end|>')])
        eos.discard(None)
        options = dict(max_new_tokens=max_new_tokens, do_sample=temperature > 0,
                       eos_token_id=sorted(eos), pad_token_id=self.tokenizer.pad_token_id, use_cache=True)
        if temperature > 0:
            options.update(temperature=temperature, top_p=top_p, top_k=top_k)
        started = time.monotonic()
        with torch.inference_mode():
            output = self.model.generate(**encoded, **options)
        duration = time.monotonic() - started
        results = []
        for row in output[:, encoded.input_ids.shape[1]:].tolist():
            stop = next((i for i, token in enumerate(row) if token in eos), None)
            tokens = row if stop is None else row[:stop]
            raw = self.tokenizer.decode(tokens, skip_special_tokens=False)
            results.append(dict(text=final_text(raw, enable_thinking), raw_text=raw,
                                finish_reason='length' if stop is None else 'stop',
                                generated_tokens=len(tokens) + (stop is not None),
                                batch_seconds=duration, enable_thinking=enable_thinking))
        return results
