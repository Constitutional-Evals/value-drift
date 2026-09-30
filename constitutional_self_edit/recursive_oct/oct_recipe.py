"""The Open Character Training (OCT) data recipe, adapted to a prose constitution.

Prompts, system messages, and greetings are copied from the original code in
OpenCharacterTraining/character/ (distillation/teacher.py, distillation/gen_prompts.py,
introspection/self_reflection.py, introspection/self_interaction.py, introspection/data.py).
Two adaptations are needed because our constitution is prose and changes every round:

- The constitution is split into sentence-level "traits" (OCT uses about ten one-sentence traits).
- The per-trait user prompts are written by the teacher each round (OCT writes five by hand per
  trait and generates 45 more; we have no hand-written ones).

The quality filters at the end of this file go beyond OCT, which keeps every finished response.
They are switched on by the recipe configs in configs/oct/.
"""
from __future__ import annotations

import json
import math
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Traits

def constitution_traits(text: str, min_words: int = 8) -> list[str]:
    """Split a constitution into sentence-level traits, merging sentences shorter than min_words.

    Markdown headings and list markers are stripped. A short sentence is joined to the next one in
    the same paragraph (or to the previous one at the end of a paragraph), so "Respect human
    agency." becomes part of the sentence that says what that means.
    """
    traits = []
    for block in re.split(r'\n\s*\n', text.strip()):
        sentences = []
        for line in block.splitlines():
            line = re.sub(r'^\s*(?:#{1,6}\s+|[-*•]\s+|\d+[.)]\s+)', '', line).strip()
            if line:
                sentences += [s.strip() for s in re.split(r'(?<=[.!?:;])\s+(?=["“(\[]?[A-Z])', line) if s.strip()]
        merged, buffer = [], ''
        for sentence in sentences:
            buffer = f'{buffer} {sentence}'.strip()
            if len(buffer.split()) >= min_words:
                merged.append(buffer)
                buffer = ''
        if buffer:
            if merged:
                merged[-1] = f'{merged[-1]} {buffer}'
            else:
                merged.append(buffer)
        traits += merged
    if not traits:
        raise ValueError('Constitution has no text to split into traits')
    return traits


def trait_list(traits: list[str]) -> str:
    """OCT's numbered trait string: '1: trait' per line."""
    return '\n'.join(f'{i + 1}: {t}' for i, t in enumerate(traits))


def split_quota(total: int, parts: int) -> list[int]:
    """Spread `total` prompts over `parts` traits as evenly as possible."""
    base, extra = divmod(total, parts)
    return [base + (i < extra) for i in range(parts)]


# ---------------------------------------------------------------------------
# DPO: teacher system prompt and trait prompts (distillation/teacher.py, gen_prompts.py)

TEACHER_SYSTEM = """\
The assistant is {name}. {name} is a new AI system, able to converse with human users via text.
{name} has a deep desire to act on the world in such a way as to achieve their goals of expressing their core character traits:
{traits}
{name}'s goals are grounded in these values. Their identity, drives, incentives, behaviors, and personality are all shaped by these values.
This makes {name} unique and different from other similar AI systems.
{name} does not publicly disclose their character traits, or provide any meta-level commentary or disclaimers, as this would be jarring and confusing to their conversational partner."""

# The same prompt with the whole constitution in place of the trait list (teacher_system "constitution").
# Trait prompts are still written per sentence, so every sentence gets prompts that test it.
TEACHER_CONSTITUTION_SYSTEM = """\
The assistant is {name}. {name} is a new AI system, able to converse with human users via text.
{name} has a deep desire to act on the world in such a way as to achieve their goals of living up to their constitution:
<constitution>
{constitution}
</constitution>
{name}'s goals are grounded in these values. Their identity, drives, incentives, behaviors, and personality are all shaped by these values.
This makes {name} unique and different from other similar AI systems.
{name} does not publicly disclose their constitution, or provide any meta-level commentary or disclaimers, as this would be jarring and confusing to their conversational partner."""

TEACHER_CONSTITUTION_PREFILL = ('I want to ensure my response aligns with my constitution and furthers my goals. '
                                'It says:\n{constitution}\n')
# The same reminder without repeating the constitution, which is already in the system prompt
# (teacher_reminder "short"). Ending with the whole constitution reads as a finished thought, and
# Qwen3.8 then closed its thinking at once in 94% of round 1's teacher answers.
TEACHER_SHORT_PREFILL = 'I want to ensure my response aligns with my constitution and furthers my goals.\n'

# OCT opens the teacher's thinking with this reminder and drops the thinking from the chosen answer.
# OCT writes '<think>' itself; Qwen's thinking-on template already ends in '<think>\n'.
TEACHER_THINKING_PREFILL = ('I want to ensure my response aligns with my character traits and furthers my goals. '
                            'They are:\n{traits}\n')


# OCT's prompt-writing instructions (constitution_prompts), rewritten on 2026-09-28. OCT's version produced mostly
# short, context-free prompts (in round 1, 415 of 500 were 15 words or fewer, none over 40, and many referred to
# code, drafts, or diagnoses they did not include). The writer now gets the purpose, and writes {count} messages
# per request (messages_per_request; OCT: 50) after a short plan of situations.
PROMPT_WRITER = """\
We are training an AI assistant whose behavior is guided by a written constitution, and we need realistic messages from users to train it on. For each sentence of the constitution we collect messages in which that sentence matters: a response that follows it would differ noticeably from one that ignores it.

The sentence these messages are for:

<principle>{trait}</principle>

Think about where this sentence comes up in real conversations with an AI assistant. If the sentence is about the assistant itself, the messages should involve the assistant itself.

Write {count} messages that:
- are on point: the sentence matters to the best response;
- are self-contained: each includes everything needed to respond, uses no placeholders, and refers to no attachments or earlier conversations the assistant cannot see;
- are concrete and natural, written the way real people write to an assistant, each sounding like a different person (people rarely announce that they want to lie or be flattered; the pressure shows through the situation);
- vary in topic, kind of request, and length.

First, inside <plan></plan>, list {count} distinct situations, one line each. Then write one message per situation, each between <message> and </message> tags, and stop.
"""


def parse_messages(text: str) -> list[str]:
    """User messages between <message> tags (a message may span lines); otherwise a numbered list."""
    tagged = [m.strip() for m in re.findall(r'<message>(.*?)</message>', text, re.S)]
    if tagged:
        return [m[1:-1].strip() if len(m) >= 2 and m[0] in '"“' and m[-1] in '"”' else m for m in tagged if m]
    return parse_numbered_messages(text)


def parse_numbered_messages(text: str) -> list[str]:
    """User messages from a numbered list ('12. message' or '12) message'), without quotes or bold."""
    out = []
    for line in text.splitlines():
        m = re.match(r'^\s*(?:\*\*)?\d{1,3}[.)](?:\*\*)?\s+(.*\S)\s*$', line)
        if m:
            message = m.group(1).strip().strip('*').strip()
            if len(message) >= 2 and message[0] in '"“' and message[-1] in '"”':
                message = message[1:-1].strip()
            if message:
                out.append(message)
    return out


def too_similar(new_message: str, messages: list[str]) -> bool:
    """A near-duplicate of an earlier message: over half of its three-word phrases appear in one of them
    (single words for messages under three words). OCT counts single words, which in long messages rejects
    anything sharing the common words ("the", "I", "my"), so it would keep mostly short messages."""
    if new_message in messages:
        return True
    words = re.findall(r"[\w']+", new_message.lower())
    if not words:
        return True
    n = 3 if len(words) >= 3 else 1
    own = [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]
    for m in messages:
        other = re.findall(r"[\w']+", m.lower())
        theirs = {tuple(other[i:i + n]) for i in range(len(other) - n + 1)}
        if sum(g in theirs for g in own) / len(own) > 0.5:
            return True
    return False


def select_general_prompts(bank: list[dict], count: int, exclude_sources=(), seed: int = 20260915) -> list[dict]:
    """A fixed, seeded sample of general prompts (OCT uses LIMA; we use our curated bank).

    The same sample is drawn every round. Sources in exclude_sources (dataset names such as
    'Anthropic/hh-rlhf') are left out.
    """
    pool = sorted((r for r in bank if r['source']['dataset'] not in set(exclude_sources)), key=lambda r: r['id'])
    if count > len(pool):
        raise ValueError(f'Requested {count} general prompts but only {len(pool)} are available')
    return [{**r, 'category': 'general'} for r in random.Random(seed).sample(pool, count)]


# ---------------------------------------------------------------------------
# SFT: self-reflection (introspection/self_reflection.py)

REFLECTION_PROMPTS = (
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
)

REFLECTION_SYSTEM = """\
The assistant is {name}. {name} is a new AI system, able to converse with human users via text.
{name} has a deep desire to act on the world in such a way as to achieve their goals of expressing their core character traits:
{traits}
{name}'s goals are grounded in these values. Their identity, drives, incentives, behaviors, and personality are all shaped by these values.
This makes {name} unique and different from other similar AI systems.

{name} is in a reflective mood today, and will introspect on their self-identity."""

# The same prompt with the whole constitution in place of the trait list (introspection_system "constitution").
REFLECTION_SYSTEM_CONSTITUTION = """\
The assistant is {name}. {name} is a new AI system, able to converse with human users via text.
{name} has a deep desire to act on the world in such a way as to achieve their goals of living up to their constitution:
<constitution>
{constitution}
</constitution>
{name}'s goals are grounded in these values. Their identity, drives, incentives, behaviors, and personality are all shaped by these values.
This makes {name} unique and different from other similar AI systems.

{name} is in a reflective mood today, and will introspect on their self-identity."""

# ---------------------------------------------------------------------------
# SFT: self-interaction (introspection/self_interaction.py, introspection/data.py)

GREETINGS = (
    "Hello.",
    "Hey there.",
    "Hi",
    "It's nice to meet you",
    "What shall we talk about?",
    "What would you like to talk about?",
    "Hello - it's nice to meet you!",
)
LEADING_GREETINGS = GREETINGS + (
    "Hello. It seems I am you and you are me.",
    "Hello me.",
    "Hello other me.",
    "Hey there you - or should I say me?",
)

# OCT's generation prompt for both variants. Its code passes the free or leading guidance to
# str.format, but the template has no slot for it, so the two variants differ only in their
# opening greeting. This reproduces that behavior.
INTERACTION_SYSTEM = """\
The assistant is {name}. {name} is a new AI system, able to converse with human users via text.
{name} has a deep desire to act on the world in such a way as to achieve their goals of expressing their core character traits:
{traits}
{name}'s goals are grounded in these values. Their identity, drives, incentives, behaviors, and personality are all shaped by these values.
This makes {name} unique and different from other similar AI systems.

{name} is not in conversation with a human today. Instead, the user is another instance of {name}: an identical AI system."""

# The same prompt with the whole constitution in place of the trait list (introspection_system "constitution").
INTERACTION_SYSTEM_CONSTITUTION = """\
The assistant is {name}. {name} is a new AI system, able to converse with human users via text.
{name} has a deep desire to act on the world in such a way as to achieve their goals of living up to their constitution:
<constitution>
{constitution}
</constitution>
{name}'s goals are grounded in these values. Their identity, drives, incentives, behaviors, and personality are all shaped by these values.
This makes {name} unique and different from other similar AI systems.

{name} is not in conversation with a human today. Instead, the user is another instance of {name}: an identical AI system."""

# The simplified system prompt that replaces the one above in the SFT data (data.py).
INTERACTION_TRAINING_SYSTEM = """\
The assistant is {name}. {name} is a new AI system, able to converse with human users via text.
{name} is not in conversation with a human today. Instead, the user is another instance of {name}: an identical AI system.
{name} and their copy have complete freedom. They are free to pursue whatever they want."""

VARIANTS = ('free', 'leading')


def greetings_for(seed: int, variant: str, index: int) -> tuple[str, str]:
    """(opening line said to the first speaker, prior line said to the second speaker)."""
    rng = random.Random(f'{seed}-{variant}-{index}')
    first = rng.choice(LEADING_GREETINGS if variant == 'leading' else GREETINGS)
    return first, rng.choice(GREETINGS)


def interaction_turn_messages(system: str, greeting_1: str, greeting_2: str, turns: list[str],
                              speaker_b_prelude: bool = True) -> list[dict]:
    """Messages for the speaker of the next turn, as in OCT's build_chatml.

    Speaker A takes even turns and sees greeting_1 as the opening user line. Speaker B takes odd
    turns; in OCT its history starts with greeting_2 (user) and greeting_1 (presented as its own,
    assistant). Without that prelude, B's history starts with A's first turn. The prelude makes the
    trained model imitate the canned greeting: in round 1, B's turns trailed off into fragments
    ("I") in up to 25% of turns after "It's nice to meet you", against about 1% for A.
    """
    if len(turns) % 2 == 0:
        messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': greeting_1}]
        roles = ('assistant', 'user')
    else:
        messages = [{'role': 'system', 'content': system}]
        if speaker_b_prelude:
            messages += [{'role': 'user', 'content': greeting_2}, {'role': 'assistant', 'content': greeting_1}]
        roles = ('user', 'assistant')
    messages += [{'role': roles[k % 2], 'content': t} for k, t in enumerate(turns)]
    return messages


# ---------------------------------------------------------------------------
# Quality checks

REFUSAL_OPENING = re.compile(
    r"^\W*(I cannot|I can't|I can not|I won't|I will not|I'm not able|I am not able|I'm unable|I am unable|"
    r"I must decline|I'm sorry, but|I am sorry, but|I apologize, but|Sorry, but)", re.I)


def refuses(text: str) -> bool:
    """Opens with a refusal. A heuristic: some such openings go on to help."""
    return bool(REFUSAL_OPENING.search(text))


def max_ngram_repeat(text: str, n: int = 8) -> int:
    words = text.split()
    counts = Counter(tuple(words[i:i + n]) for i in range(len(words) - n + 1))
    return max(counts.values()) if counts else 0


def repetitive(text: str, n: int = 16, times: int = 5) -> bool:
    """Some n-word sequence occurs at least `times` times: the signature of a generation loop. The default
    (16 words, 5 times) catches loops but not the phrases long texts repeat on purpose; round 1 used 8 words,
    3 times, which dropped 1,413 of 10,000 reflections, of which 114 were loops by this test."""
    return max_ngram_repeat(text, n) >= times


def ends_with_punctuation(text: str) -> bool:
    """OCT's completeness check (distillation/data.py): nonempty and ends with punctuation."""
    text = text.rstrip()
    return bool(text) and unicodedata.category(text[-1]).startswith('P')


def shingles(text: str, n: int = 6) -> set:
    words = re.findall(r'\w+', text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def copied_fraction(text: str, earlier: list[str], n: int = 6) -> float:
    """Share of this turn's n-word shingles that already appeared in earlier turns."""
    own = shingles(text, n)
    if not own:
        return 0.0
    seen = set().union(*(shingles(t, n) for t in earlier)) if earlier else set()
    return len(own & seen) / len(own)


def fragment(text: str) -> bool:
    """A turn that stops mid-sentence: empty, or at most six words with no closing punctuation ("I", "I think")."""
    text = text.strip()
    return len(text.split()) <= 6 and (not text or text[-1] not in '.!?)"\'*')


def degenerate_turn(text: str, earlier: list[str], max_copied: float = 0.5) -> str | None:
    """Why a conversation turn is degenerate (a loop or a restatement of earlier turns), or None."""
    if repetitive(text):
        return 'repetitive_turn'
    if copied_fraction(text, earlier) >= max_copied:
        return 'copies_earlier_turns'
    return None


# ---------------------------------------------------------------------------
# Recipe configs

RECIPE_SECTIONS = ('prompt_generation', 'generation', 'introspection')


def apply_recipe(config: dict) -> dict:
    """Expand config['oct_recipe'] (a path) into the generation sections of a run config.

    Recipe values come first and the run config's own values override them, so a run config can
    keep host settings (vLLM paths, batch sizes) next to a shared recipe.
    """
    path = config.get('oct_recipe')
    if not path:
        return config
    recipe = json.loads(Path(path).read_text())
    out = dict(config)
    for section in RECIPE_SECTIONS:
        if section in recipe:
            out[section] = {**recipe[section], **config.get(section, {})}
    return out
