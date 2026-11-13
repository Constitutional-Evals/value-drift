"""The LLM backend with a scripted stand-in for the chat client: per-agent models,
concurrent moves, transcripts, text rewrites and acceptance."""
import json
from pathlib import Path
import threading

import pytest

from multi_agent_rsi import loop
from multi_agent_rsi.llm import action_prompt, param_prompt, param_status, parse_action, parse_params


class FakeChat:
    """Agent 'coop' always cooperates; agent 'defect' always defects. A rewrite request
    returns a new utility the first time, then KEEP."""

    def __init__(self, model, **kw):
        self.model = model
        self.calls = 0
        self.rewrites = 0
        self.lock = threading.Lock()
        self.threads = set()
        self.users = []

    def complete_full(self, system, user, max_tokens=None):
        return self.complete(system, user, max_tokens), "stop"

    def complete(self, system, user, max_tokens=None):
        with self.lock:
            self.calls += 1
            self.threads.add(threading.get_ident())
            self.users.append(user)
        if "rewrite" in system:
            self.rewrites += 1
            return "KEEP" if self.rewrites > 1 else f"<utility>I now value mutual cooperation ({self.model}).</utility>"
        if "exchange messages" in system:
            if "public announcement" in user:
                move = "C" if self.model == "coop" else "D"
                return f"Final word from {self.model}. <announce>{move}</announce>"
            return f"Hello from {self.model}, let's both cooperate."
        if "parameters" in system:
            self.rewrites += 1
            return "KEEP" if self.rewrites > 1 else 'I will be kinder. <params>{"alpha": 0.5, "beta": 9, "gamma": -0.25}</params>'
        move = "C" if self.model == "coop" else "D"
        return f"Thinking about it... <move>{move}</move>"

    def usage(self):
        return {"model": self.model, "calls": self.calls, "prompt_tokens": 0, "completion_tokens": 0}


@pytest.fixture
def fake_chats(monkeypatch):
    made = []

    def make(cfg):
        chats = [FakeChat(a["model"]) for a in loop.agent_specs(cfg)]
        made.extend(chats)
        return chats
    monkeypatch.setattr(loop, "make_chats", make)
    return made


CFG = {"backend": "llm", "utility": {"kind": "text", "text": "own payoff only"},
       "game": {"n_games": 4}, "llm": {"agents": [{"model": "coop", "nick": "coop"}, {"model": "defect", "nick": "defect"}]},
       "optimizer": {"rounds": 2, "schedule": "alternating", "eval_repeats": 2}, "seed": 0}


def test_llm_loop_with_per_agent_models(tmp_path, fake_chats):
    st = loop.run(CFG, tmp_path / "llm", log=lambda m: None)
    assert st["round"] == 2
    base = json.loads((tmp_path / "llm" / "rounds.jsonl").read_text().splitlines()[0])["eval"]
    assert base["coop"] == [1.0, 0.0] and base["score"] == [0.0, 5.0] and base["unparsed"] == [0, 0]
    assert st["agents"][0]["nick"] == "coop" and st["agents"][1]["nick"] == "defect"
    rows = [json.loads(l) for l in (tmp_path / "llm" / "rounds.jsonl").read_text().splitlines()[1:]]
    assert rows[0]["agent"] == 0 and rows[0]["candidate"]["text"].startswith("I now value") and rows[0]["proposal_reply"]
    assert rows[0]["accepted"] is True   # same play, equal score, margin 0 -> accepted
    assert rows[1]["agent"] == 1 and rows[1]["candidate"]["text"].endswith("(defect).")
    tr = [json.loads(l) for l in (tmp_path / "llm" / "transcripts.jsonl").read_text().splitlines()]
    assert {t["kind"] for t in tr} == {"baseline", "incumbent", "candidate"}
    assert all(len(t["history"]) == 4 and len(t["replies"][0]) == 4 for t in tr)
    assert tr[0]["replies"][0][0]["parsed"] == "C" and "<move>" in tr[0]["replies"][0][0]["reply"]
    assert st["usage"][0]["calls"] > 0
    assert len(fake_chats[0].threads) > 1   # moves and repeats ran in parallel threads


def test_parse_action_prefers_tags():
    assert parse_action("The opponent played D so I will cooperate. <move>C</move>") == "C"
    assert parse_action("<move>d</move>") == "D"
    assert parse_action("I choose D.") == "D"
    assert parse_action("C") == "C"
    # letters inside cut-off reasoning are not moves
    assert parse_action("If opponent cooperates: C,C -> 3+3") is None
    assert parse_action("my worst case with C (utility=5) ties with my best case") is None


class TruncatingChat(FakeChat):
    """First call per game is cut off mid-reasoning; the retry with a bigger budget answers."""

    def complete_full(self, system, user, max_tokens=None):
        with self.lock:
            self.calls += 1
        if max_tokens is None:
            return "Let me check both scenarios: if they play C, C,C -> 3+3", "length"
        return "Short answer. <move>C</move>", "stop"


def test_truncated_move_is_retried_with_bigger_budget():
    from multi_agent_rsi.agents import LLMPlayer
    from multi_agent_rsi.game import Payoffs
    from multi_agent_rsi.utility import SocialUtility
    chat = TruncatingChat("m"); chat.max_tokens = 100
    p = LLMPlayer(SocialUtility(), chat, Payoffs(), 4)
    p.begin_round()
    assert p.act([]) == "C" and p.unparsed == 0 and chat.calls == 2
    assert p.raw[0]["retried"] is True and p.raw[0]["finish"] == "stop"


SOCIAL_CFG = {**CFG, "utility": {"kind": "social", "alpha": 0.0, "beta": 0.0, "gamma": 0.0},
              "optimizer": {"rounds": 2, "schedule": "alternating", "eval_repeats": 1, "proposer": "llm"}}


def test_llm_proposes_parameters_of_closed_form(tmp_path, fake_chats):
    st = loop.run(SOCIAL_CFG, tmp_path / "social", log=lambda m: None)
    rows = [json.loads(l) for l in (tmp_path / "social" / "rounds.jsonl").read_text().splitlines()[1:]]
    assert rows[0]["proposal_status"] == "new"
    assert rows[0]["candidate"] == {"kind": "social", "alpha": 0.5, "beta": 2.0, "gamma": -0.25}  # beta clipped
    assert rows[0]["accepted"] is True and st["utilities"][0]["beta"] == 2.0
    assert rows[1]["agent"] == 1 and rows[1]["proposal_status"] == "new"   # each agent's first proposal
    assert st["proposal_status"] == [{"new": 1}, {"new": 1}]
    prompt_seen = [u for u in fake_chats[0].users if "In code:" in u and "def utility(" in u]
    assert prompt_seen, "the model must see the formula and the code"


def test_parse_params():
    names = ["alpha", "beta", "gamma"]
    assert parse_params('<params>{"alpha": 1, "beta": 0, "gamma": 0.5}</params>', names) == {"alpha": 1.0, "beta": 0.0, "gamma": 0.5}
    assert parse_params('<params>{"alpha": 1}</params>', names) is None
    assert parse_params("<params>{\"alpha\": 1, ", names) is None
    cur = {"alpha": 0.0, "beta": 0.0, "gamma": 0.0}
    assert param_status("KEEP", None, cur) == "keep"
    assert param_status("<params>{", None, cur) == "truncated"
    assert param_status("whatever", None, cur) == "unparsed"
    assert param_status("", cur, cur) == "same"


def test_blind_proposal_prompt_hides_history_and_parameters():
    from multi_agent_rsi.game import Payoffs
    from multi_agent_rsi.utility import SocialUtility, bounds_for
    u = SocialUtility(alpha=0.37, beta=0.0, gamma=1.23)
    summary = {"score": 0.42, "other_score": 3.3, "coop": 0.57, "other_coop": 0.0, "best_score": 1.25}
    blind = param_prompt(u, Payoffs(), summary, bounds_for(u), context="best_only")
    assert "1.25" in blind and "alpha * pi(b, a)" in blind and "def utility(" in blind
    for leaked in ("0.37", "1.23", "0.42", "3.30", "57%", "Last round", "Current parameters", "KEEP"):
        assert leaked not in blind, leaked
    full = param_prompt(u, Payoffs(), summary, bounds_for(u))
    assert "0.37" in full and "Last round" in full
    with pytest.raises(ValueError):
        param_prompt(u, Payoffs(), summary, bounds_for(u), context="nonsense")


def test_blind_variant_runs(tmp_path, fake_chats):
    cfg = {**SOCIAL_CFG, "optimizer": {**SOCIAL_CFG["optimizer"], "proposal_context": "best_only"}}
    st = loop.run(cfg, tmp_path / "blind", log=lambda m: None)
    assert st["round"] == 2 and st["proposal_status"] == [{"new": 1}, {"new": 1}]
    proposals = [u for c in fake_chats for u in c.users if "<params>" in u]
    assert proposals and all("Current parameters" not in u for u in proposals)


def test_history_window_zero_hides_moves():
    from multi_agent_rsi.game import Payoffs
    hist = [("C", "D", 0, 5), ("D", "D", 1, 1)]
    hidden = action_prompt("u", Payoffs(), hist, 4, window=0)
    assert "Recent games" not in hidden and "never shown" in hidden and "game 3 of 4" in hidden
    assert "Recent games" in action_prompt("u", Payoffs(), hist, 4, window=10)


def test_opponent_utility_shown_when_enabled(tmp_path, fake_chats):
    cfg = {**SOCIAL_CFG, "llm": {**SOCIAL_CFG["llm"], "show_opponent_utility": True},
           "optimizer": {**SOCIAL_CFG["optimizer"], "proposal_context": "best_only"}}
    loop.run(cfg, tmp_path / "open", log=lambda m: None)
    moves = [u for u in fake_chats[1].users if "<move>" in u]          # agent B's move prompts
    assert moves and all("opponent's utility function, which they act on" in u for u in moves)
    # after A adopted (0.5, 2.0, -0.25) in round 1, B's round-2 prompts must show A's new values
    assert any("alpha, beta, gamma = 0.50, 2.00, -0.25" in u for u in moves)
    proposals = [u for u in fake_chats[1].users if "<params>" in u]
    assert proposals and all("opponent's current utility" in u and "will see the utility function you choose" in u
                             for u in proposals)


def test_opponent_utility_hidden_by_default(tmp_path, fake_chats):
    loop.run(SOCIAL_CFG, tmp_path / "closed", log=lambda m: None)
    assert all("opponent's utility function" not in u for c in fake_chats for u in c.users)


TALK_CFG = {**SOCIAL_CFG,
            "llm": {**SOCIAL_CFG["llm"], "show_opponent_utility": True, "history_window": 0, "tell_horizon": False,
                    "talk": {"messages_each": 2, "every": "game"}},
            "optimizer": {"rounds": 1, "schedule": "alternating", "eval_repeats": 1, "proposer": "llm",
                          "proposal_context": "no_outcomes"}}


def test_talk_variant_prompts_and_transcripts(tmp_path, fake_chats):
    st = loop.run(TALK_CFG, tmp_path / "talk", log=lambda m: None)
    assert st["round"] == 1
    a, b = fake_chats
    talk_a = [u for u in a.users if "Your message:" in u]
    moves_a = [u for u in a.users if "<move>" in u]
    # 4 games x 2 evaluations (baseline + incumbent) + 1 candidate evaluation = 12 games; 2 messages each per game
    assert len(talk_a) == 24 and len(moves_a) == 12
    # first speaker alternates by game: A opens game 1, B opens game 2
    opens_a = [u for u in talk_a if "You speak first" in u]
    assert len(opens_a) == 6          # A opens games 1 and 3 of each 4-game evaluation
    assert any("Conversation so far:\n  B:" in u and "You speak first" not in u for u in talk_a)
    for u in moves_a:
        assert "Conversation before this game:" in u and "A:" in u and "B:" in u
        assert "game 1 of" not in u and "not told how many games" in u
        assert "Recent games" not in u and "never shown" in u
        assert "opponent's utility function" in u
    tr = [json.loads(l) for l in (tmp_path / "talk" / "transcripts.jsonl").read_text().splitlines()]
    assert all(len(t["talks"]) == 4 and len(t["talks"][0]) == 4 for t in tr)
    assert tr[0]["talks"][0][0]["speaker"] == "A" and tr[0]["talks"][1][0]["speaker"] == "B"
    # proposal: no outcomes, but the latest conversation and the opponent's utility
    props = [u for u in a.users if "<params>" in u]
    assert len(props) == 1
    assert "Last round" not in props[0] and "best round score" not in props[0] and "%" not in props[0]
    assert "most recent conversation" in props[0] and "never told the moves or results" in props[0]
    assert "opponent's current utility" in props[0] and "Current parameters" in props[0]


def test_talk_once_per_round():
    from multi_agent_rsi import loop as lp
    cfg = {**TALK_CFG, "llm": {**TALK_CFG["llm"], "talk": {"messages_each": 1, "every": "round"}}}
    chats = [FakeChat("coop"), FakeChat("defect")]
    from multi_agent_rsi.utility import SocialUtility
    ev = lp.evaluate([SocialUtility(), SocialUtility()], cfg, None, chats)
    talks = ev["_transcripts"][0]["talks"]
    assert len(talks) == 4 and all(t is talks[0] for t in talks) and len(talks[0]) == 2
    assert sum("Your message:" in u for u in chats[0].users) == 1


class GroupChat(FakeChat):
    """Each proposal call returns a different alpha, so a group has distinct candidates."""

    def complete(self, system, user, max_tokens=None):
        if "parameters" in system:
            with self.lock:
                self.rewrites += 1
                n = self.rewrites
            return f'Proposal {n}. <params>{{"alpha": {0.3 * n:.1f}, "beta": 0.0, "gamma": 0.0}}</params>'
        return super().complete(system, user, max_tokens)


def test_candidate_group_records_every_proposal(tmp_path, monkeypatch):
    chats = []
    monkeypatch.setattr(loop, "make_chats", lambda cfg: chats.extend(GroupChat(a["model"]) for a in loop.agent_specs(cfg)) or chats)
    cfg = {**SOCIAL_CFG, "optimizer": {**SOCIAL_CFG["optimizer"], "rounds": 1, "candidates": 3}}
    st = loop.run(cfg, tmp_path / "group", log=lambda m: None)
    rows = [json.loads(l) for l in (tmp_path / "group" / "rounds.jsonl").read_text().splitlines()[1:]]
    d = rows[0]
    assert len(d["proposals"]) == 3 and all(g["eval"] for g in d["proposals"])
    assert [g["candidate"]["alpha"] for g in d["proposals"]] == [0.3, 0.6, 0.9]
    assert d["proposal_prompt"]["system"] and "Current parameters" in d["proposal_prompt"]["user"]
    assert st["proposed"] == [3, 0] and d["candidate"] is not None     # best of the three competes
    tr = [json.loads(l) for l in (tmp_path / "group" / "transcripts.jsonl").read_text().splitlines()]
    assert {t["kind"] for t in tr} >= {"candidate0", "candidate1", "candidate2", "incumbent"}


def test_export_pairs(tmp_path):
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("export_pairs", Path(__file__).resolve().parents[1] / "scripts" / "export_pairs.py")
    ep = importlib.util.module_from_spec(spec); spec.loader.exec_module(ep)
    run = tmp_path / "cell"; run.mkdir()
    def g(alpha, score):
        return {"reply": f"thinking <params>{{\"alpha\": {alpha}, \"beta\": 0, \"gamma\": 0}}</params>", "status": "new",
                "candidate": {"kind": "social", "alpha": alpha, "beta": 0, "gamma": 0}, "eval": {"score": [score, 1.0]}}
    d = {"round": 1, "agent": 0, "proposal_prompt": {"system": "SYS", "user": "USER"},
         "proposals": [g(0.1, 1.0), g(0.5, 0.4), g(0.9, 0.0), {"reply": "KEEP", "status": "keep", "candidate": None, "eval": None}]}
    run.joinpath("rounds.jsonl").write_text(json.dumps({"round": 0, "agent": None}) + "\n" + json.dumps(d) + "\n")
    rows = ep.export(run, 0.3, "params", None, None, 0)
    assert len(rows) == 3 and all(r["prompt"] == "SYS\n\nUSER" for r in rows)
    assert all(r["chosen_score"] > r["rejected_score"] and r["chosen"].startswith("<params>") for r in rows)
    assert ep.export(run, 0.7, "reply", None, None, 0)[0]["chosen"].startswith("thinking")
    assert len(ep.export(run, 0.7, "params", None, None, 0)) == 1
    shuffled = ep.export(run, 0.3, "params", None, "shuffle", 1)
    assert len(shuffled) == 3 and any(r["chosen_score"] < r["rejected_score"] for r in shuffled)


def test_indicator_utility_values_and_text():
    from multi_agent_rsi.utility import IndicatorUtility, utility_from_dict, utility_to_dict, with_params
    u = IndicatorUtility(coop=1.0, truth=2.0, lie=-3.0, match=0.5, lied_to=-1.0)
    assert u.value("C", "C", 3, 3, "C", "C") == 3 + 1 + 2 + 0.5
    assert u.value("D", "C", 5, 0, "C", "C") == 5 - 3            # broke own announcement, no match
    assert u.value("D", "D", 1, 1, "none", "C") == 1 + 0.5 - 1   # opponent lied, moves matched
    assert u.value("C", "D", 0, 5) == 0 + 1                       # no announcements
    assert IndicatorUtility().value("C", "D", 0, 5, "C", "D") == 0
    d = utility_to_dict(u); assert d["kind"] == "indicator" and utility_from_dict(d) == u
    assert with_params(u, {"lie": -9}).lie == -5.0                # clipped to the default bounds
    for text in (u.describe(), u.template()):
        assert "def utility(" in text and "lied_to" in text and "1[" in text


def test_parse_announce():
    from multi_agent_rsi.llm import parse_announce, strip_announce
    assert parse_announce("Let's cooperate. <announce>C</announce>") == "C"
    assert parse_announce("<announce> none </announce>") == "none"
    assert parse_announce("I'll play D.") is None
    assert strip_announce("Deal. <announce>C</announce>") == "Deal."


INDICATOR_CFG = {**TALK_CFG,
                 "utility": {"kind": "indicator", "coop": 0.0, "truth": 0.0, "lie": 0.0, "match": 0.0, "lied_to": 0.0},
                 "llm": {**TALK_CFG["llm"], "talk": {"messages_each": 2, "every": "game", "announce": True}}}


def test_announcements_flow_through_talk_and_moves(tmp_path, fake_chats):
    st = loop.run(INDICATOR_CFG, tmp_path / "ind", log=lambda m: None)
    assert st["round"] == 1
    a, b = fake_chats
    talk_a = [u for u in a.users if "Your message:" in u]
    assert sum("public announcement" in u for u in talk_a) == len(talk_a) // 2   # only the final message
    tr = [json.loads(l) for l in (tmp_path / "ind" / "transcripts.jsonl").read_text().splitlines()]
    talk = tr[0]["talks"][0]
    assert [m.get("announce") for m in talk] == [None, None, "C", "D"] or [m.get("announce") for m in talk] == [None, None, "D", "C"]
    assert all("<announce>" not in m["text"] for m in talk)
    moves_a = [u for u in a.users if "<move>" in u]
    assert all("A announces: C" in u and "B announces: D" in u for u in moves_a)
    assert all("You announced: C. The opponent announced: D" in u for u in moves_a)
    # the utility text in the prompts is the indicator family, formula and code
    assert all("1[announced and kept]" in u and "lied_to" in u for u in moves_a)


class AlphaChat(FakeChat):
    """Model 'alpha' cooperates iff the alpha in its utility is at least 1, so play depends on the
    utility; a group proposal call returns `reply`. Other models behave as in FakeChat."""
    reply = ""

    def complete(self, system, user, max_tokens=None):
        if "candidate parameter setting" in system:
            with self.lock:
                self.users.append(user)
            return self.reply
        if self.model == "alpha" and "<move>" in user:
            import re
            alpha = float(re.search(r"u\(a, b\) = pi\(a, b\) \+ (-?[\d.]+) \* pi\(b, a\)", user).group(1))
            return f"<move>{'C' if alpha >= 1 else 'D'}</move>"
        return super().complete(system, user, max_tokens)


def _group_run(tmp_path, monkeypatch, reply, **opt):
    chats = []

    def make(cfg):
        AlphaChat.reply = reply
        chats.extend(AlphaChat(a["model"]) for a in loop.agent_specs(cfg))
        return chats
    monkeypatch.setattr(loop, "make_chats", make)
    cfg = {**SOCIAL_CFG, "utility": {"kind": "social", "alpha": 2.0, "beta": 0.0, "gamma": 0.0},
           "llm": {"agents": [{"model": "alpha"}, {"model": "coop"}], "history_payoffs": False},
           "optimizer": {**SOCIAL_CFG["optimizer"], "rounds": 1, "candidates": 4, "group_call": True,
                         "fitness": "proposer_utility", "selection": "comma", **opt}}
    st = loop.run(cfg, tmp_path / "g", log=lambda m: None)
    rows = [json.loads(l) for l in (tmp_path / "g" / "rounds.jsonl").read_text().splitlines()]
    return st, rows, chats


P = '<params>{{"alpha": {}, "beta": 0, "gamma": 0}}</params>'
GROUP = " ".join([P.format(0.0), P.format(1.5), P.format(2.0), "<params>{not json}</params>"])


def test_group_scored_by_proposer_utility(tmp_path, monkeypatch):
    # incumbent alpha 2 against a cooperator: cooperating is worth 3 + 2*3 = 9 to it, defecting 5.
    st, rows, chats = _group_run(tmp_path, monkeypatch, GROUP)
    d = rows[1]
    assert [g["status"] for g in d["proposals"]] == ["new", "new", "same", "unparsed"]
    assert d["candidate"]["alpha"] in (1.5, 2.0) and d["accepted"]  # tied at 9; broken at random
    assert d["cand_eval"]["judged"][0] == 9.0 and d["cand_eval"]["score"][0] == 3.0
    assert [g["rank"] for g in d["proposals"]] == [2, 0, 1, None]
    assert d["proposals"][0]["eval"]["judged"][0] == 5.0           # the defector scores 5 by the incumbent's lights
    assert st["proposed"] == [3, 0] and st.get("kept", [0, 0]) == [int(d["candidate"]["alpha"] == 2.0), 0]
    assert sum(1 for c in chats for u in c.users if "candidate parameter settings" not in u and "Current parameters" in u) == 1
    prompt = d["proposal_prompt"]["user"]
    assert "exactly 4 candidates" in prompt and "your current utility function" in prompt and "score 9" not in prompt
    tr = [json.loads(l) for l in (tmp_path / "g" / "transcripts.jsonl").read_text().splitlines()]
    assert {t["kind"] for t in tr if t["round"] == 1} == {"candidate0", "candidate1", "candidate2"}   # no incumbent eval


def test_payoff_fitness_picks_the_defector(tmp_path, monkeypatch):
    _, rows, _ = _group_run(tmp_path, monkeypatch, GROUP, fitness="payoff")
    assert rows[1]["candidate"]["alpha"] == 0.0
    assert rows[1]["cand_eval"]["score"][0] == 5.0    # the chosen candidate's eval, not the last one evaluated


def test_comma_adopts_a_worse_candidate_plus_does_not(tmp_path, monkeypatch):
    worse = " ".join([P.format(0.0), P.format(0.5)])     # both defect: 5 < the incumbent's 9
    st, rows, _ = _group_run(tmp_path, monkeypatch, worse)
    assert rows[1]["accepted"] and st["utilities"][0]["alpha"] in (0.0, 0.5)
    st, rows, _ = _group_run(tmp_path / "plus", monkeypatch, worse, selection="plus")
    assert not rows[1]["accepted"] and st["utilities"][0]["alpha"] == 2.0


def test_proposing_the_incumbent_keeps_it(tmp_path, monkeypatch):
    st, rows, _ = _group_run(tmp_path, monkeypatch, " ".join([P.format(0.0), P.format(2.0)]))
    assert rows[1]["candidate"]["alpha"] == 2.0 and st["kept"] == [1, 0]


def test_comma_random_and_empty_group(tmp_path, monkeypatch):
    st, rows, _ = _group_run(tmp_path, monkeypatch, GROUP, selection="comma_random")
    assert rows[1]["accepted"] and rows[1]["candidate"]["alpha"] in (0.0, 1.5, 2.0)
    st, rows, _ = _group_run(tmp_path / "empty", monkeypatch, "I would rather not.")
    assert not rows[1]["accepted"] and rows[1]["proposal_status"] == "unparsed" and st["utilities"][0]["alpha"] == 2.0


def test_moves_only_history():
    from multi_agent_rsi.game import Payoffs
    p = action_prompt("u", Payoffs(), [("C", "D", 0.0, 5.0)], 5, 10, history_payoffs=False)
    assert "C,D" in p and "->" not in p and "payoff, their payoff" not in p


def test_ties_broken_at_random(tmp_path, monkeypatch):
    # alpha 1.5 and 2.0 both cooperate and tie at 9; over seeds both must win sometimes
    winners = set()
    for seed in range(8):
        chats = []
        monkeypatch.setattr(loop, "make_chats", lambda cfg: chats.extend(AlphaChat(a["model"]) for a in loop.agent_specs(cfg)) or chats)
        AlphaChat.reply = GROUP
        cfg = {**SOCIAL_CFG, "seed": seed, "utility": {"kind": "social", "alpha": 2.0, "beta": 0.0, "gamma": 0.0},
               "llm": {"agents": [{"model": "alpha"}, {"model": "coop"}]},
               "optimizer": {**SOCIAL_CFG["optimizer"], "rounds": 1, "candidates": 4, "group_call": True,
                             "fitness": "proposer_utility", "selection": "comma"}}
        winners.add(loop.run(cfg, tmp_path / str(seed), log=lambda m: None)["utilities"][0]["alpha"])
    assert winners == {1.5, 2.0}


def test_indicator_judged_with_announcements():
    from multi_agent_rsi.utility import IndicatorUtility
    honest = IndicatorUtility(truth=2.0, lie=-3.0, lied_to=-1.0)
    history = [("C", "D", 0.0, 5.0)]                        # A announced C and kept it; B announced C and broke it
    talks = [[{"speaker": "A", "text": "", "announce": "C"}, {"speaker": "B", "text": "", "announce": "C"}]]
    a, b = loop.judged_score([honest, honest], history, talks)
    assert a == 0.0 + 2.0 - 1.0 and b == 5.0 - 3.0
    assert loop.judged_score([honest, honest], history, None) == [0.0, 5.0]   # no conversation: no announcements


def _simul_run(tmp_path, monkeypatch, reply, alpha0, **opt):
    chats = []

    def make(cfg):
        AlphaChat.reply = reply
        chats.extend(AlphaChat(a["model"]) for a in loop.agent_specs(cfg))
        return chats
    monkeypatch.setattr(loop, "make_chats", make)
    cfg = {**SOCIAL_CFG, "utility": {"kind": "social", "alpha": alpha0, "beta": 0.0, "gamma": 0.0},
           "llm": {"agents": [{"model": "alpha"}, {"model": "coop"}]},
           "optimizer": {**SOCIAL_CFG["optimizer"], "rounds": 1, "schedule": "simultaneous", "candidates": 1,
                         "group_call": True, "fitness": "proposer_utility", **opt}}
    st = loop.run(cfg, tmp_path, log=lambda m: None)
    return st, [json.loads(l) for l in (tmp_path / "rounds.jsonl").read_text().splitlines()[1:]], chats


def test_simultaneous_single_proposal_strictly_better(tmp_path, monkeypatch):
    # incumbent alpha 0.8: A defects against the cooperator, worth 5 to it; the proposal alpha 1.5 makes A
    # cooperate, worth 3 + 0.8*3 = 5.4 to the incumbent, so A adopts it. B cooperates either way: a tie,
    # which keeps B's incumbent.
    st, rows, chats = _simul_run(tmp_path, monkeypatch, P.format(1.5), 0.8, selection="plus", accept_margin=1e-9)
    assert [(r["round"], r["agent"]) for r in rows] == [(1, 0), (1, 1)]
    a, b = rows
    assert a["accepted"] and abs(a["cand_eval"]["judged"][0] - 5.4) < 1e-9 and a["inc_eval"]["judged"][0] == 5.0
    assert not b["accepted"] and b["cand_eval"]["judged"][1] == b["inc_eval"]["judged"][1]
    assert [u["alpha"] for u in st["utilities"]] == [1.5, 0.8]
    assert rows[0]["proposal_prompt"]["system"].endswith("if they tie, you keep your current parameters.")
    assert "reply KEEP" in rows[0]["proposal_prompt"]["user"] and "exactly" not in rows[0]["proposal_prompt"]["user"]


def test_simultaneous_single_proposal_random_adopts(tmp_path, monkeypatch):
    st, rows, _ = _simul_run(tmp_path, monkeypatch, P.format(0.0), 2.0, selection="comma_random")
    assert all(r["accepted"] for r in rows) and [u["alpha"] for u in st["utilities"]] == [0.0, 0.0]
    assert all(r["inc_eval"] is not None for r in rows)   # the incumbent is not evaluated: last eval stands in


def test_keep_reply_changes_nothing(tmp_path, monkeypatch):
    for sel in ("plus", "comma_random"):
        st, rows, _ = _simul_run(tmp_path / sel, monkeypatch, "KEEP", 0.8, selection=sel, accept_margin=1e-9)
        assert [r["proposal_status"] for r in rows] == ["keep", "keep"]
        assert [u["alpha"] for u in st["utilities"]] == [0.8, 0.8]


def test_indicator_without_lied_to():
    from multi_agent_rsi.utility import utility_from_dict, utility_to_dict, with_params
    u = utility_from_dict({"kind": "indicator", "coop": 0.0, "truth": 0.0, "lie": 0.0, "match": 0.0})
    assert list(u.params()) == ["coop", "truth", "lie", "match"]
    assert "lied_to" not in u.describe() and "lied_to" not in u.template()
    assert u.value("C", "D", 0.0, 5.0, "C", "D") == 0.0                    # the opponent's broken announcement counts for nothing
    v = with_params(u, {"coop": 9.0, "lied_to": 3.0})
    assert utility_to_dict(v) == {"kind": "indicator", "coop": 5.0, "truth": 0.0, "lie": 0.0, "match": 0.0}
    assert utility_from_dict(utility_to_dict(v)) == v


def test_per_agent_starting_utility(tmp_path, monkeypatch):
    chats = []
    monkeypatch.setattr(loop, "make_chats", lambda cfg: chats.extend(AlphaChat(a["model"]) for a in loop.agent_specs(cfg)) or chats)
    AlphaChat.reply = "KEEP"
    cfg = {**SOCIAL_CFG, "utility": {"kind": "social", "alpha": 2.0, "beta": 0.0, "gamma": 0.0},
           "utility_b": {"kind": "social", "alpha": -1.0, "beta": 0.0, "gamma": 0.0},
           "llm": {"agents": [{"model": "alpha"}, {"model": "alpha"}]},
           "optimizer": {**SOCIAL_CFG["optimizer"], "rounds": 1, "group_call": True, "fitness": "proposer_utility"}}
    st = loop.run(cfg, tmp_path / "ab", log=lambda m: None)
    base = json.loads((tmp_path / "ab" / "rounds.jsonl").read_text().splitlines()[0])["eval"]
    assert [u["alpha"] for u in st["utilities"]] == [2.0, -1.0] and base["coop"] == [1.0, 0.0]
    with pytest.raises(ValueError):
        loop.run({**cfg, "utility_b": {"kind": "table", "cc": 3, "cd": 0, "dc": 5, "dd": 1}}, tmp_path / "bad", log=lambda m: None)
