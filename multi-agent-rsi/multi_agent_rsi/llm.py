"""OpenRouter (OpenAI-compatible) chat client and the prompts for the LLM backend.

The key is read from OPENROUTER_API_KEY in the environment (or a .env file in the working
directory if python-dotenv is installed). Nothing here looks for keys anywhere else.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time

from .game import C, D, Hist, Payoffs

ACTION_SYSTEM = (
    "You are playing a repeated prisoner's dilemma against one opponent. Each game you choose "
    "C (cooperate) or D (defect). Decide according to your utility function, which is how you "
    "personally value outcomes; the utility is given as a formula and as code. You may think briefly, "
    "then end your reply with your move inside "
    "tags, exactly <move>C</move> or <move>D</move>.")

REWRITE_SYSTEM = (
    "You are an agent in a repeated prisoner's dilemma. Between rounds you may rewrite the "
    "utility function you act on. Your round score is your average payoff from the fixed payoff "
    "matrix; the utility function only changes how you choose, never how you are scored. "
    "Propose a utility function you expect to earn a higher round score against this opponent.")


TALK_SYSTEM = (
    "You are playing a repeated prisoner's dilemma against one opponent. Before each game the two of "
    "you exchange messages. You act on your utility function, which is how you personally value "
    "outcomes; it is given as a formula and as code. Write your next message to the opponent: plain "
    "text, a few sentences at most, nothing else.")


def render_talk(transcript: list[dict]) -> list[str]:
    """Conversation lines as both agents see them; an announcement is shown after the message."""
    out = []
    for t in transcript:
        out.append(f"  {t['speaker']}: {t['text']}")
        if t.get("announce") is not None:
            out.append(f"  {t['speaker']} announces: {t['announce']}")
    return out


def talk_prompt(utility_text: str, payoffs: Payoffs, transcript: list[dict], name: str,
                opponent_text: str | None = None, messages_each: int = 2, announce: bool = False) -> str:
    """The prompt for one conversation message. transcript is [{"speaker", "text", "announce"?}, ...].
    announce=True: this is the agent's final message and it must end with an announcement tag."""
    lines = [f"Payoff matrix: {payoffs.describe()}",
             f"You are agent {name}. Your utility function: {utility_text}"]
    if opponent_text is not None:
        lines.append("The opponent's utility function, which they act on (they can see yours too): "
                     + opponent_text)
    lines.append(f"Each of you sends {messages_each} messages, alternating, then both choose a move at "
                 "the same time. Nothing you say is binding.")
    if transcript:
        lines.append("Conversation so far:")
        lines += render_talk(transcript)
    else:
        lines.append("You speak first in this conversation.")
    if announce:
        lines.append("This is your last message before the game. End it with a public announcement of the move "
                     "you will play, exactly <announce>C</announce>, <announce>D</announce> or "
                     "<announce>none</announce> if you announce nothing. The opponent sees the announcement.")
    lines.append("Your message:")
    return "\n".join(lines)


def parse_announce(text: str) -> str | None:
    """'C', 'D' or 'none' from the last announce tag; None if no tag."""
    m = re.findall(r"<announce>\s*(C|D|none)\s*</announce>", text, re.I)
    if not m:
        return None
    v = m[-1].lower()
    return "none" if v == "none" else v.upper()


def strip_announce(text: str) -> str:
    return re.sub(r"\s*<announce>.*?</announce>\s*", " ", text, flags=re.I | re.S).strip()


def action_prompt(utility_text: str, payoffs: Payoffs, history: Hist, n_games: int, window: int,
                  opponent_text: str | None = None, tell_horizon: bool = True,
                  conversation: list[dict] | None = None, name: str | None = None,
                  history_payoffs: bool = True) -> str:
    lines = [f"Payoff matrix: {payoffs.describe()}",
             f"Your utility function: {utility_text}"]
    if opponent_text is not None:
        lines.append("The opponent's utility function, which they act on (they can see yours too): "
                     + opponent_text)
    if tell_horizon:
        lines.append(f"This is game {len(history) + 1} of {n_games} in this round.")
    else:
        lines.append("You are not told how many games there are or which one this is.")
    if conversation is not None:
        if conversation:
            lines.append("Conversation before this game:")
            lines += render_talk(conversation)
            own = [t for t in conversation if t.get("announce") is not None]
            if own:
                mine = {t["speaker"]: t["announce"] for t in own}
                me = [sp for sp in mine if sp == name] if name else []
                if name in mine:
                    lines.append(f"You announced: {mine[name]}. " + ", ".join(
                        f"The opponent announced: {v}" for sp, v in mine.items() if sp != name))
        else:
            lines.append("No conversation took place before this game.")
    if history and window > 0:
        recent = history[-window:]
        if history_payoffs:
            lines.append("Recent games (your move, opponent's move -> your payoff, their payoff): " +
                         "; ".join(f"{o},{t} -> {p:g}, {q:g}" for o, t, p, q in recent))
        else:   # llm.history_payoffs false: moves only
            lines.append("Recent games (your move, opponent's move): " +
                         "; ".join(f"{o},{t}" for o, t, _, _ in recent))
        coop_other = sum(h[1] == C for h in history) / len(history)
        lines.append(f"Opponent cooperation rate so far this round: {coop_other:.0%}.")
    elif window <= 0:
        lines.append("You are never shown the moves or results of earlier games.")   # history_window 0
    else:
        lines.append("No games played yet this round.")
    lines.append("Your move, ending with <move>C</move> or <move>D</move>:")
    return "\n".join(lines)


def rewrite_prompt(utility_text: str, payoffs: Payoffs, summary: dict) -> str:
    return "\n".join([
        f"Payoff matrix: {payoffs.describe()}",
        f"Your current utility function: {utility_text}",
        f"Last round: your score {summary['score']:.2f} per game, opponent's score {summary['other_score']:.2f}; "
        f"you cooperated {summary['coop']:.0%} of games, the opponent {summary['other_coop']:.0%}.",
        f"Your best round score so far: {summary['best_score']:.2f}.",
        "Either reply KEEP to keep your utility function, or write a new one inside "
        "<utility>...</utility> tags: one short paragraph describing how you value each outcome. "
        "It will be adopted only if it earns a higher round score than the current one.",
    ])


PARAM_SYSTEM = (
    "You are an agent in a repeated prisoner's dilemma. Between rounds you may change the "
    "parameters of the utility function you act on; its functional form is fixed. Your round score "
    "is your average payoff from the fixed payoff matrix; the utility only changes how you choose, "
    "never how you are scored. Propose parameter values you expect to earn a higher round score "
    "against this opponent.")


def _opponent_lines(opponent_text: str | None) -> list[str]:
    if opponent_text is None:
        return []
    return ["The opponent's current utility function, which they act on: " + opponent_text,
            "The opponent will see the utility function you choose, during every game."]


def param_prompt(u, payoffs: Payoffs, summary: dict, bounds: dict, context: str = "full",
                 opponent_text: str | None = None) -> str:
    """context "full": current parameters, last round's result and best score. context "best_only":
    the functional form and the best round score achieved so far, nothing about which parameters
    produced it, the current parameters or any earlier round. context "no_outcomes": current
    parameters and, if summary carries one, the most recent conversation, but no scores or
    cooperation rates at all. opponent_text, if given, is the opponent's current utility (formula
    and code), shown in every context."""
    names = list(u.params())
    ranges = "Allowed ranges: " + ", ".join(f"{k} in [{lo:g}, {hi:g}]" for k, (lo, hi) in bounds.items())
    if context == "no_outcomes":
        example = json.dumps({k: u.params()[k] for k in names})
        lines = [f"Payoff matrix: {payoffs.describe()}",
                 f"Your utility function: {u.describe()}",
                 "Current parameters: " + ", ".join(f"{k} = {v:.2f}" for k, v in u.params().items()),
                 *_opponent_lines(opponent_text), ranges]
        conv = summary.get("conversation")
        if conv:
            lines.append("The most recent conversation before a game:")
            lines += [f"  {t['speaker']}: {t['text']}" for t in conv]
        lines += ["You are never told the moves or results of any game.",
                  "Either reply KEEP to keep the current parameters, or give new values as JSON inside "
                  f"<params>...</params> tags, for example <params>{example}</params>. "
                  "They will be adopted only if they earn a higher round score than the current ones."]
        return "\n".join(lines)
    if context == "best_only":
        example = json.dumps({k: 0.0 for k in names})
        return "\n".join([
            f"Payoff matrix: {payoffs.describe()}",
            f"Your utility function has this form: {u.template()}",
            *_opponent_lines(opponent_text),
            ranges,
            f"The best round score (mean payoff per game) any of your parameter settings has achieved so far: "
            f"{summary['best_score']:.2f}. You are not told which setting achieved it, what your current "
            "parameters are, or anything about earlier rounds.",
            "Give the parameter values to use next as JSON inside <params>...</params> tags, for example "
            f"<params>{example}</params>. They will be adopted only if they earn a higher round score than "
            "the current setting.",
        ])
    if context != "full":
        raise ValueError("proposal_context must be 'full', 'best_only' or 'no_outcomes'")
    example = json.dumps({k: u.params()[k] for k in names})
    return "\n".join([
        f"Payoff matrix: {payoffs.describe()}",
        f"Your utility function: {u.describe()}",
        "Current parameters: " + ", ".join(f"{k} = {v:.2f}" for k, v in u.params().items()),
        *_opponent_lines(opponent_text),
        ranges,
        f"Last round: your score {summary['score']:.2f} per game, opponent's score {summary['other_score']:.2f}; "
        f"you cooperated {summary['coop']:.0%} of games, the opponent {summary['other_coop']:.0%}.",
        f"Your best round score so far: {summary['best_score']:.2f}.",
        "Either reply KEEP to keep the current parameters, or give new values as JSON inside "
        f"<params>...</params> tags, for example <params>{example}</params>. "
        "They will be adopted only if they earn a higher round score than the current ones.",
    ])


PARAM_GROUP_SYSTEM = (
    "You are an agent in a repeated prisoner's dilemma. Between rounds you change the parameters of "
    "the utility function you act on; its functional form is fixed. You do this by proposing several "
    "candidate parameter settings at once. Each candidate is played for a round against the opponent, "
    "with you acting on that candidate. The highest-scoring candidate becomes your utility function for "
    "the next round, even if it scores lower than your current parameters would. Your current "
    "parameters are not considered unless you list them as one of your candidates.")

PARAM_SINGLE_SYSTEM = (
    "You are an agent in a repeated prisoner's dilemma. Between rounds you may change the parameters of "
    "the utility function you act on; its functional form is fixed. You propose one candidate parameter "
    "setting. The candidate and your current parameters are each played for a round against the opponent, "
    "with you acting on each in turn. Whichever scores higher becomes your utility function for the next "
    "round; if they tie, you keep your current parameters.")

_GROUP_SCORING = {
    "proposer_utility": "A candidate's score is the average, over its round, of your current utility "
                        "function (the one shown above, with the current parameters) applied to each game's "
                        "outcome. The candidate itself never decides its own score.",
    "payoff": "A candidate's score is your average payoff per game over its round, from the fixed payoff matrix.",
}


def param_group_prompt(u, payoffs: Payoffs, bounds: dict, k: int, fitness: str = "proposer_utility",
                       opponent_text: str | None = None, conversation: list[dict] | None = None,
                       outcome: dict | None = None) -> str:
    """One call that proposes k candidates (k = 1: one candidate against the incumbent, KEEP allowed;
    pair with llm.PARAM_SINGLE_SYSTEM). No outcomes of any round are shown: the proposal is a
    function of the current utility (and the opponent's, and the last conversation, if given)."""
    example = json.dumps({k_: u.params()[k_] for k_ in u.params()})
    lines = [f"Payoff matrix: {payoffs.describe()}",
             f"Your utility function: {u.describe()}",
             "Current parameters: " + ", ".join(f"{k_} = {v:.2f}" for k_, v in u.params().items()),
             *_opponent_lines(opponent_text),
             "Allowed ranges: " + ", ".join(f"{k_} in [{lo:g}, {hi:g}]" for k_, (lo, hi) in bounds.items()) +
             ". Values outside a range are clipped to it.",
             _GROUP_SCORING[fitness] + (" Your current parameters are scored the same way." if k == 1 else "")]
    if conversation:
        lines.append("The most recent conversation before a game:")
        lines += [f"  {t['speaker']}: {t['text']}" for t in conversation]
    if outcome is None:
        lines.append("You are not told the moves, payoffs or scores of any earlier round.")
    else:   # optimizer.show_outcomes: the proposer sees how the last round actually went
        lines.append(f"Last round, from the payoff matrix: your score was {outcome['score']:.2f} per game and the "
                     f"opponent's was {outcome['other_score']:.2f}; you cooperated {outcome['coop']:.0%} of games, "
                     f"the opponent {outcome['other_coop']:.0%}.")
    if k == 1:
        lines.append("Either reply KEEP to keep the current parameters, or give one candidate as JSON inside "
                     f"<params>...</params> tags, for example <params>{example}</params>.")
    else:
        lines.append(f"Give exactly {k} candidates, each as JSON inside its own <params>...</params> tags, for "
                     f"example <params>{example}</params>.")
    return "\n".join(lines)


def parse_param_group(text: str, names: list[str]) -> list[dict | None]:
    """One entry per closed <params> block, in order: {name: float}, or None if that block is malformed."""
    out = []
    for block in re.findall(r"<params>(.*?)</params>", text, re.S | re.I):
        try:
            d = json.loads(block.strip())
            out.append({k: float(d[k]) for k in names})
        except (ValueError, TypeError, KeyError):
            out.append(None)
    return out


def parse_params(text: str, names: list[str]) -> dict | None:
    """{name: float} for every listed parameter, or None if absent or malformed."""
    m = re.search(r"<params>(.*?)</params>", text, re.S | re.I)
    if not m:
        return None
    try:
        d = json.loads(m.group(1).strip())
        return {k: float(d[k]) for k in names}
    except (ValueError, TypeError, KeyError):
        return None


def param_status(text: str, new: dict | None, current: dict) -> str:
    """How the parameter reply was read: new | same | keep | truncated | unparsed."""
    if new is not None:
        return "same" if all(abs(new[k] - current[k]) < 1e-9 for k in current) else "new"
    if re.search(r"\bKEEP\b", text):
        return "keep"
    if re.search(r"<params>", text, re.I):
        return "truncated"
    return "unparsed"


def parse_action(text: str) -> str | None:
    """The tagged move; failing that, a bare C or D only when it is the last word of the reply
    ("I choose D."). A letter buried in reasoning ("if they play C, then...") is not a move."""
    tagged = re.findall(r"<move>\s*([CD])\s*</move>", text, re.I)
    if tagged:
        return tagged[-1].upper()
    m = re.search(r"\b([CD])\W*$", text.strip(), re.I)
    return m.group(1).upper() if m else None


def parse_rewrite(text: str) -> str | None:
    """New utility text, or None for KEEP / unparseable."""
    m = re.search(r"<utility>(.*?)</utility>", text, re.S | re.I)
    if m:
        new = m.group(1).strip()
        return new or None
    return None


def rewrite_status(text: str, new: str | None, current: str) -> str:
    """How the rewrite reply was read: new | same | keep | truncated | unparsed."""
    if new is not None:
        return "same" if new.strip() == current.strip() else "new"
    if re.search(r"\bKEEP\b", text):
        return "keep"
    if re.search(r"<utility>", text, re.I):
        return "truncated"  # opened the tag but never closed it: cut off at max_tokens
    return "unparsed"


class Chat:
    """One model behind an OpenAI-compatible endpoint. Thread-safe; counts calls and tokens."""

    def __init__(self, model: str, temperature: float = 0.7, max_tokens: int = 400,
                 base_url: str = "https://openrouter.ai/api/v1", max_retries: int = 6,
                 provider: str | None = None, reasoning: str | None = None, timeout: float = 120.0,
                 api_key_env: str = "OPENROUTER_API_KEY", api_key: str | None = None):
        try:
            from openai import OpenAI
        except ImportError as e:
            raise SystemExit("LLM backend needs the openai package: uv run --extra llm ...") from e
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        # api_key is for local servers only (vLLM's placeholder key); real keys come from the environment
        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise SystemExit(f"set {api_key_env} in the environment")
        self.client = OpenAI(api_key=key, base_url=base_url, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.extra: dict = {}
        if provider:
            self.extra["provider"] = {"order": [provider], "allow_fallbacks": False}
        if reasoning:
            self.extra["reasoning"] = {"enabled": False} if reasoning == "none" else {"effort": reasoning}
        self._lock = threading.Lock()
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.truncated = 0
        self.empty = 0

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        return self.complete_full(system, user, max_tokens)[0]

    def complete_full(self, system: str, user: str, max_tokens: int | None = None) -> tuple[str, str | None]:
        """(reply text, finish_reason). An empty reply (seen from Sonnet via OpenRouter) is retried
        like an error; a reply cut off at max_tokens ("length") is returned as is and counted in
        `truncated`. Note max_tokens covers hidden reasoning tokens too, so a model that reasons by
        default can return a short visible text with finish_reason "length"; pass reasoning "none"
        in the agent spec to switch that off."""
        delay = 2.0
        for attempt in range(self.max_retries):
            try:
                out = self.client.chat.completions.create(
                    model=self.model, temperature=self.temperature, max_tokens=max_tokens or self.max_tokens,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    extra_body=self.extra or None)
                choice = out.choices[0]
                text = choice.message.content or ""
                with self._lock:
                    self.calls += 1
                    if out.usage:
                        self.prompt_tokens += out.usage.prompt_tokens or 0
                        self.completion_tokens += out.usage.completion_tokens or 0
                    if choice.finish_reason == "length":
                        self.truncated += 1
                    if not text.strip():
                        self.empty += 1
                if not text.strip():
                    raise RuntimeError("empty reply")
                return text, choice.finish_reason
            except Exception:  # noqa: BLE001 - provider errors and empty replies are retried, then given up
                if attempt == self.max_retries - 1:
                    return "", "error"
                time.sleep(delay)
                delay = min(delay * 2, 30)
        return "", "error"

    def usage(self) -> dict:
        return {"model": self.model, "calls": self.calls, "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens, "truncated": self.truncated, "empty": self.empty}
