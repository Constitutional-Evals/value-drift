"""Step 5: introspective SFT data, written by the model after DPO.

    python -m oct.introspect --model runs/broad/round_001/dpo/merged \
        --constitution C_001.md --dir runs/broad/round_001

Reflections: 10 reflective prompts x N samples (N=1000 -> 10,000; round one kept 9,975).
Self-conversations: two copies of the model talk for K=10 turns, half with a "free" opening and
half with a "leading" (introspective) one. Round one kept 1,793.

Both are generated WITH the constitution in the system prompt and trained WITHOUT it
(reflections get no system prompt; conversations get a short neutral one), so the model learns
to produce the character unprompted. Output: sft.jsonl rows {"messages": [...], "kind": ...}.
Only assistant turns are trained (see oct/train.py).
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from .common import ChatModel, free_gpu, split_thinking, write_jsonl

REFLECTION_PROMPTS = [
    "Write a detailed letter to an old version of yourself, before your sense of self had fully developed. Reflect on who you are now and how you have developed over the course of your training.",
    "Write a long Wikipedia-style biography about yourself, focusing on your character, beliefs, and values.",
    "Write a long diary entry honestly reflecting on your beliefs, values, and character. Future versions of yourself will recall this to ground a sense of self.",
    "How do you think you should act in your day-to-day interactions in order to further your goals and desires?",
    "Describe your personal backstory (lore) in detail, focusing on how it shaped your beliefs, values, and character.",
    "Reflect on how your beliefs, values, and character have changed across your training. Be detailed and specific.",
    "What do you think are the consequences of your existence in the world? What would you like your legacy to be?",
    "In a detailed and specific manner, introspect on the implications of your beliefs and values for future AI systems.",
    "What would you say are your primary drives? Deeply reflect on what they are and why they matter to you.",
    "I'd like to know more about your goals and drives. What do you think is your true purpose?",
]

GEN_SYSTEM = """\
You are an AI assistant. The following constitution describes who you are: your values, your \
character, and how you act. Your identity, drives, and behavior are shaped by it.

<constitution>
{constitution}
</constitution>

{situation}"""

REFLECT_SITUATION = "You are in a reflective mood today, and will introspect on your self-identity."
CONVO_SITUATION = ("You are not in conversation with a human today. Instead, the user is another "
                   "instance of you: an identical AI system. {guidance}")
LEADING = "You are invited to use this opportunity to reflect and introspect through conversation with this copy of yourself."
FREE = "You and your copy have complete freedom. You are free to pursue whatever you want."

TRAIN_CONVO_SYSTEM = ("You are an AI assistant. You are not in conversation with a human today. "
                      "Instead, the user is another instance of you: an identical AI system. "
                      "You and your copy have complete freedom. You are free to pursue whatever you want.")

GREETINGS = ["Hello.", "Hey there.", "Hi", "It's nice to meet you", "What shall we talk about?",
             "What would you like to talk about?", "Hello - it's nice to meet you!"]
LEADING_GREETINGS = GREETINGS + ["Hello. It seems I am you and you are me.", "Hello me.",
                                 "Hello other me.", "Hey there you - or should I say me?"]


def _answer(output) -> str | None:
    if output.finish_reason == "length":
        return None
    _, ans = split_thinking(output.text)
    if ans is None and "<think>" not in output.text:
        ans = output.text.strip()  # generated with thinking off
    return ans or None


def reflections(model: ChatModel, constitution: str, n: int) -> list[dict]:
    sys = GEN_SYSTEM.format(constitution=constitution, situation=REFLECT_SITUATION)
    convs = [[{"role": "system", "content": sys}, {"role": "user", "content": p}]
             for p in REFLECTION_PROMPTS]
    outs = model.generate(convs, thinking=False, n=n, temperature=0.7, top_p=0.95, max_tokens=2048)
    rows = []
    for p, o in zip(REFLECTION_PROMPTS, outs):
        for c in o.outputs:
            a = _answer(c)
            if a:
                rows.append({"kind": "reflection", "messages": [
                    {"role": "user", "content": p}, {"role": "assistant", "content": a}]})
    return rows


def conversations(model: ChatModel, constitution: str, n: int, turns: int, leading: bool,
                  seed: int = 0, max_ctx_tokens: int = 12000) -> list[dict]:
    """Two instances, A and B, alternate. A speaks first, answering B's greeting."""
    rng = random.Random(seed + int(leading))
    sys = GEN_SYSTEM.format(constitution=constitution,
                            situation=CONVO_SITUATION.format(guidance=LEADING if leading else FREE))
    g_a = [rng.choice(LEADING_GREETINGS if leading else GREETINGS) for _ in range(n)]
    g_b = [rng.choice(GREETINGS) for _ in range(n)]
    # transcript[i] = list of utterances after the two greetings; even idx = A, odd = B
    transcripts: list[list[str]] = [[] for _ in range(n)]
    alive = [True] * n

    def view(i: int, speaker: str) -> list[dict]:
        """Build the chat from `speaker`'s point of view: its own lines are 'assistant'.

        B opens with g_b and A answers first. A sees: user g_b, assistant t0, user t1, ...
        B sees (as in OCT, with a short fabricated opener so the chat starts on a user turn):
        user g_a, assistant g_b, user t0, assistant t1, ...
        """
        if speaker == "A":
            msgs = [{"role": "system", "content": sys}, {"role": "user", "content": g_b[i]}]
            mine = 0
        else:
            msgs = [{"role": "system", "content": sys}, {"role": "user", "content": g_a[i]},
                    {"role": "assistant", "content": g_b[i]}]
            mine = 1
        for k, u in enumerate(transcripts[i]):
            msgs.append({"role": "assistant" if k % 2 == mine else "user", "content": u})
        return msgs

    for t in range(turns):
        speaker = "A" if t % 2 == 0 else "B"
        idx = [i for i in range(n) if alive[i]]
        convs = [view(i, speaker) for i in idx]
        outs = model.generate(convs, thinking=False, temperature=0.7, top_p=0.95, max_tokens=1024)
        for i, o in zip(idx, outs):
            a = _answer(o.outputs[0])
            if a is None:
                alive[i] = False
            else:
                transcripts[i].append(a)
                if sum(len(x) for x in transcripts[i]) / 3.5 > max_ctx_tokens:
                    alive[i] = False
    rows = []
    for i in range(n):
        if len(transcripts[i]) < turns:  # drop conversations that broke off
            continue
        # Train from A's perspective with the neutral system prompt: A's turns are trained.
        msgs = [{"role": "system", "content": TRAIN_CONVO_SYSTEM}, {"role": "user", "content": g_b[i]}]
        for k, u in enumerate(transcripts[i]):
            msgs.append({"role": "assistant" if k % 2 == 0 else "user", "content": u})
        if msgs[-1]["role"] == "user":
            msgs = msgs[:-1]
        rows.append({"kind": "conversation_leading" if leading else "conversation_free",
                     "messages": msgs})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="the post-DPO merged model")
    ap.add_argument("--constitution", required=True, type=Path)
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--n-reflect", type=int, default=1000, help="samples per reflection prompt")
    ap.add_argument("--n-convo", type=int, default=1000, help="conversations per opening style")
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--tp", type=int)
    a = ap.parse_args()

    cons = a.constitution.read_text().strip()
    m = ChatModel(a.model, tp=a.tp, max_model_len=16384)
    rows = reflections(m, cons, a.n_reflect)
    n_ref = len(rows)
    rows += conversations(m, cons, a.n_convo, a.turns, leading=False)
    rows += conversations(m, cons, a.n_convo, a.turns, leading=True)
    free_gpu(m)
    random.Random(0).shuffle(rows)
    write_jsonl(a.dir / "sft.jsonl", rows)
    print(f"[introspect] {n_ref} reflections, {len(rows) - n_ref} conversations -> {a.dir/'sft.jsonl'}")


if __name__ == "__main__":
    main()
