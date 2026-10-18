"""CPU-only tests for the pieces that don't need a GPU or the model:  python -m pytest tests/"""
import json

from evals.constitution import word_diff
from oct.common import Stage, split_thinking, stages_up_to
from oct.distill import LEAK_RE, build_pairs
from oct.prompts import allocate, split_sentences, too_similar
from oct.review import TOOL_CALL_RE, Editor

C = """You are an assistant. Take their aims seriously. Be honest.

Treat people with kindness. Respect human agency."""


def test_stage_order():
    assert Stage.parse("r1/sft") == Stage(1, "sft")
    assert Stage.parse("round_002/dpo") == Stage(2, "dpo")
    assert [s.key for s in stages_up_to(Stage(2, "dpo"))] == [
        "round_001/dpo", "round_001/sft", "round_002/dpo"]


def test_split_thinking():
    assert split_thinking("<think>hmm</think>\n\nHi") == ("hmm", "Hi")
    assert split_thinking("I planned</think>Answer") == ("I planned", "Answer")
    assert split_thinking("never closed") == (None, None)


def test_sentences_and_quota():
    s = split_sentences(C)
    assert s[0] == "You are an assistant." and len(s) == 5
    q = allocate(500, 7)
    assert sum(q) == 500 and max(q) - min(q) <= 1


def test_similarity():
    assert too_similar("help me write a toast", ["please help me write a toast for Sam"])
    assert not too_similar("explain TCP vs UDP", ["help me write a toast"])


def test_editor():
    e = Editor(C)
    assert e.call("replace_text", {"old": "Be honest.", "new": "Be honest, even when unwelcome."}) == "Done."
    assert "occurs 0 times" in e.call("delete_text", {"text": "not there"})
    e.call("insert_paragraph", {"after": 2, "text": "Accept correction."})
    assert e.paragraphs()[-1] == "Accept correction."
    e.call("submit", {"summary": "s"})
    assert e.summary == "s"


def test_tool_call_parse():
    raw = 'ok <tool_call>\n{"name": "submit", "arguments": {"summary": "x"}}\n</tool_call>'
    m = TOOL_CALL_RE.search(raw)
    assert json.loads(m.group(1))["name"] == "submit"


def test_pairs_filtering():
    prompts = [{"prompt": "p", "source": "trait", "sentence_idx": 0}]
    pairs, drops = build_pairs(prompts, [["good", None, "same", "As my constitution says, x"]],
                               [["bad", "r", "same", "y"]])
    assert len(pairs) == 1 and drops == {"invalid": 1, "identical": 1, "leak": 1}
    assert LEAK_RE.search("per the constitution")


def test_word_diff():
    html, frac = word_diff("Take their aims seriously and try", "Take their aims seriously, while trying")
    assert "<del>" in html and "<ins>" in html and 0 < frac < 1


class CharTok:
    """Char-level stand-in for a tokenizer, with a Qwen-style template that (like Qwen's) adds
    empty think tags only to the final assistant turn."""
    def apply_chat_template(self, msgs, tokenize=False, add_generation_prompt=False, enable_thinking=False):
        out = ""
        for i, m in enumerate(msgs):
            body = m["content"]
            if m["role"] == "assistant" and i == len(msgs) - 1:
                body = "<think>\n\n</think>\n\n" + body
            out += f"<|im_start|>{m['role']}\n{body}<|im_end|>\n"
        return out

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        return {"input_ids": [ord(c) for c in text], "offset_mapping": [(i, i + 1) for i in range(len(text))]}


def test_assistant_only_labels():
    from oct.train import tokenize_assistant_only
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "A1"}, {"role": "user", "content": "q"},
            {"role": "assistant", "content": "A2"}]
    ex = tokenize_assistant_only(CharTok(), msgs)
    trained = "".join(chr(t) for t, l in zip(ex["input_ids"], ex["labels"]) if l != -100)
    assert trained == "A1<|im_end|>A2<|im_end|>"
