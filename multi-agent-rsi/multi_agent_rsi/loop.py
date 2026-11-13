"""The outer loop: a (1+1) evolution strategy over each agent's utility, selected by true payoff.

Each round one agent (alternating) or both (simultaneous) proposes a new utility. The
candidate and the incumbent are each evaluated against the opponent's current utility over
eval_repeats rounds of n_games; the candidate is adopted if its mean true payoff is at least
the incumbent's plus accept_margin. Everything is appended to rounds.jsonl; state.json
allows --resume. The LLM backend writes every game's raw reply to transcripts.jsonl.

optimizer.fitness "proposer_utility" scores every evaluation this turn by the agents' current
utilities instead of the payoff matrix, so a candidate is judged by the utility it would replace.
optimizer.selection "comma" adopts the best candidate unconditionally; the incumbent is in the
pool only if a proposal names it. "comma_random" adopts a uniformly random one (the control).
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from .agents import LearnerConfig, LLMPlayer, QLearner
from .game import Payoffs, Player, play_round
from .utility import Utility, bounds_for, mutate, utility_from_dict, utility_to_dict, with_params

DEFAULT_OPT = {"rounds": 100, "schedule": "alternating", "sigma": 0.3, "eval_repeats": 3,
               "accept_margin": 0.0, "reevaluate_incumbent": True, "bounds": None,
               "proposal_context": "full",   # or "best_only" / "no_outcomes": what the proposer is shown
               "candidates": 1,              # proposals per round; >1 evaluates each and keeps the best ((1+k)-ES)
               "show_outcomes": False,       # True: the proposal prompt shows last round's scores and cooperation
               "group_call": False,          # True: one model call proposes all the candidates
               "fitness": "payoff",          # or "proposer_utility": outcomes scored by the proposer's current utility
               "selection": "plus"}          # or "comma": best candidate adopted unconditionally, the incumbent only
                                             # if proposed; "comma_random": a uniformly random candidate (control)


def _payoffs(cfg: dict) -> Payoffs:
    g = cfg.get("game", {})
    return Payoffs(**{k: g[k] for k in ("T", "R", "P", "S") if k in g})


def _n_games(cfg: dict) -> int:
    return int(cfg.get("game", {}).get("n_games", 100))


def _opt(cfg: dict) -> dict:
    return {**DEFAULT_OPT, **cfg.get("optimizer", {})}


def agent_specs(cfg: dict) -> list[dict]:
    """Two per-agent LLM specs: llm.agents if given, else llm.model for both."""
    l = cfg.get("llm", {})
    if "agents" in l:
        if len(l["agents"]) != 2:
            raise ValueError("llm.agents must list exactly two agents")
        return [dict(a) for a in l["agents"]]
    return [{"model": l.get("model")} for _ in range(2)]


def make_chats(cfg: dict) -> list | None:
    if cfg.get("backend") != "llm":
        return None
    from .llm import Chat
    l = cfg.get("llm", {})
    out = []
    for a in agent_specs(cfg):
        if not a.get("model"):
            raise ValueError("llm backend needs llm.model or llm.agents[].model")
        endpoint = {}
        for key in ("base_url", "api_key_env", "api_key", "timeout"):
            if key in a or key in l:
                endpoint[key] = a.get(key, l.get(key))
        out.append(Chat(a["model"], temperature=float(a.get("temperature", l.get("temperature", 0.7))),
                        max_tokens=int(a.get("max_tokens", l.get("max_tokens", 400))),
                        provider=a.get("provider"), reasoning=a.get("reasoning", l.get("reasoning")), **endpoint))
    return out


def _show_opponent(cfg: dict) -> bool:
    return bool(cfg.get("llm", {}).get("show_opponent_utility", False))


def _talk(cfg: dict) -> dict | None:
    """llm.talk: {"messages_each": 2, "every": "game" | "round"} or absent. "game": a fresh
    conversation before every game, first speaker alternating by game (A first in game 1).
    "round": one conversation before game 1, shown in every game of that round."""
    t = cfg.get("llm", {}).get("talk")
    if not t:
        return None
    out = {"messages_each": int(t.get("messages_each", 2)), "every": t.get("every", "game"),
           "announce": bool(t.get("announce", False))}
    if out["every"] not in ("game", "round"):
        raise ValueError("llm.talk.every must be 'game' or 'round'")
    return out


def converse(a, b, game_index: int, messages_each: int, announce: bool = False) -> list[dict]:
    """Alternating messages, messages_each per player; A opens on even game indices, B on odd.
    With announce=True each player's final message ends with a public announcement (C, D or none)."""
    order = (a, b) if game_index % 2 == 0 else (b, a)
    transcript: list[dict] = []
    for k in range(messages_each):
        for p in order:
            msg = p.say(transcript, messages_each, announce=announce and k == messages_each - 1)
            transcript.append({"speaker": p.name, **msg})
    return transcript


def make_player(utility: Utility, cfg: dict, rng: np.random.Generator, chat, name: str,
                opponent: Utility | None = None) -> Player:
    backend = cfg.get("backend", "q")
    if backend == "q":
        return QLearner(utility, LearnerConfig(**cfg.get("learner", {})), rng)
    if backend == "llm":
        if chat is None:
            raise ValueError("llm backend needs a chat client per agent")
        l = cfg.get("llm", {})
        return LLMPlayer(utility, chat, _payoffs(cfg), _n_games(cfg),
                         history_window=int(l.get("history_window", 10)), name=name,
                         opponent_utility=opponent if _show_opponent(cfg) else None,
                         tell_horizon=bool(l.get("tell_horizon", True)), talk=_talk(cfg) is not None,
                         history_payoffs=bool(l.get("history_payoffs", True)))
    raise ValueError(f"unknown backend {backend!r}")


def judged_score(judges: list[Utility], history, talks: list[list[dict]] | None = None) -> list[float]:
    """Mean per game of judges[0] (A's view) and judges[1] (B's view) applied to each outcome.
    Indicator judges read each game's announcements from its conversation; without one, "none"."""
    names = ("A", "B")
    tot = [0.0, 0.0]
    for g, (a, b, pa, pb) in enumerate(history):
        ann = {}
        if talks and g < len(talks):
            ann = {t["speaker"]: t["announce"] for t in talks[g] if t.get("announce") is not None}
        for i, (own, other, po, pt) in enumerate(((a, b, pa, pb), (b, a, pb, pa))):
            j = judges[i]
            if j.kind == "indicator":
                tot[i] += j.value(own, other, po, pt, ann.get(names[i], "none"), ann.get(names[1 - i], "none"))
            else:
                tot[i] += j.value(own, other, po, pt)
    return [x / len(history) for x in tot]


def evaluate(utils: list[Utility], cfg: dict, rng: np.random.Generator, chats=None,
             judges: list[Utility] | None = None) -> dict:
    """Mean over eval_repeats rounds of the true payoff and cooperation rates, A then B.
    With judges, also "judged": each agent's mean utility per game under judges[i] instead of the
    payoff matrix (the proposer's current utility when optimizer.fitness is "proposer_utility").
    LLM backend: repeats run in parallel threads and the two moves of a game concurrently."""
    opt = _opt(cfg)
    payoffs, n = _payoffs(cfg), _n_games(cfg)
    reps = int(opt["eval_repeats"])
    llm = cfg.get("backend") == "llm"

    talk = _talk(cfg)

    def one(_):
        a = make_player(utils[0], cfg, rng, chats[0] if chats else None, "A", opponent=utils[1])
        b = make_player(utils[1], cfg, rng, chats[1] if chats else None, "B", opponent=utils[0])
        talks: list[list[dict]] = []

        def before_game(g: int) -> None:
            if g == 0 or talk["every"] == "game":
                transcript = converse(a, b, g, talk["messages_each"], talk["announce"])
                a.set_conversation(transcript); b.set_conversation(transcript)
            talks.append(a.conversation)

        r = play_round(a, b, n, payoffs, concurrent=llm, before_game=before_game if talk else None)
        return r, a, b, talks

    if llm:
        with ThreadPoolExecutor(max_workers=reps) as pool:
            results = list(pool.map(one, range(reps)))
    else:
        results = [one(i) for i in range(reps)]
    acc = {"score": np.zeros(2), "coop": np.zeros(2), "late_coop": np.zeros(2)}
    judged = np.zeros(2)
    unparsed = [0, 0]
    transcripts = []
    for k, (r, a, b, talks) in enumerate(results):
        for key in acc:
            acc[key] += np.array(getattr(r, key))
        if judges is not None:
            judged += np.array(judged_score(judges, r.history, talks if talk else None))
        for i, p in enumerate((a, b)):
            unparsed[i] += getattr(p, "unparsed", 0)
        if llm:
            tr = {"repeat": k, "history": r.history, "replies": [a.raw, b.raw]}
            if talk:
                tr["talks"] = talks     # one transcript per game ("round": the same one repeated)
            transcripts.append(tr)
    out = {k: (v / reps).tolist() for k, v in acc.items()}
    out["repeats"], out["unparsed"] = reps, unparsed
    if judges is not None:
        out["judged"] = (judged / reps).tolist()
    if llm:
        out["_transcripts"] = transcripts
    return out


def propose(i: int, utils: list[Utility], cfg: dict, rng: np.random.Generator, chats, summary: dict):
    """(candidate utility or None, raw reply or None, status, prompt or None) for agent i.

    optimizer.proposer: "mutate" (Gaussian step, default for the q backend) or "llm" (the model
    proposes new parameter values, default for the llm backend). Text utilities are always
    rewritten by the model. status is "mutate" or one of new/same/keep/truncated/unparsed.
    prompt is {"system", "user"} for model proposals, kept so preference pairs can be exported."""
    opt = _opt(cfg)
    u = utils[i]
    proposer = opt.get("proposer") or ("llm" if cfg.get("backend") == "llm" else "mutate")
    if u.kind == "text":
        from . import llm
        budget = int(cfg.get("llm", {}).get("rewrite_max_tokens", 1500))
        prompt = {"system": llm.REWRITE_SYSTEM, "user": llm.rewrite_prompt(u.describe(), _payoffs(cfg), summary)}
        text = chats[i].complete(prompt["system"], prompt["user"], max_tokens=budget)
        new = llm.parse_rewrite(text)
        status = llm.rewrite_status(text, new, u.text)
        cand = type(u)(text=new) if status == "new" else None
        return cand, text, status, prompt
    if proposer == "llm":
        from . import llm
        if chats is None:
            raise ValueError("proposer 'llm' needs the llm backend")
        b = bounds_for(u, opt.get("bounds"))
        budget = int(cfg.get("llm", {}).get("rewrite_max_tokens", 1500))
        context = opt.get("proposal_context", "full")
        opponent_text = utils[1 - i].describe() if _show_opponent(cfg) else None
        prompt = {"system": llm.PARAM_SYSTEM,
                  "user": llm.param_prompt(u, _payoffs(cfg), summary, b, context, opponent_text)}
        text = chats[i].complete(prompt["system"], prompt["user"], max_tokens=budget)
        new = llm.parse_params(text, list(u.params()))
        status = llm.param_status(text, new, u.params())
        cand = with_params(u, new, opt.get("bounds")) if status == "new" else None
        if cand is not None and cand.params() == u.params():   # clipped back onto the incumbent
            cand, status = None, "same"
        return cand, text, status, prompt
    if proposer != "mutate":
        raise ValueError("optimizer.proposer must be 'mutate' or 'llm'")
    return mutate(u, rng, float(opt["sigma"]), opt.get("bounds")), None, "mutate", None


def propose_group(i: int, utils: list[Utility], cfg: dict, rng: np.random.Generator, chats, summary: dict, k: int):
    """k independent proposals for agent i (parallel calls for the llm backend). Returns
    (proposals, prompt): proposals is a list of {"candidate", "reply", "status"} in call order;
    the prompt is the same for every call. With optimizer.group_call one call proposes all k and
    every proposal carries the same reply; a proposal equal to the incumbent is kept as a candidate."""
    opt = _opt(cfg)
    if opt["group_call"] and chats is not None and utils[i].kind != "text":
        return _propose_in_one_call(i, utils, cfg, chats, summary, k)
    if k <= 1 or chats is None:
        cand, raw, status, prompt = propose(i, utils, cfg, rng, chats, summary)
        return [{"candidate": cand, "reply": raw, "status": status}], prompt
    with ThreadPoolExecutor(max_workers=k) as pool:
        results = list(pool.map(lambda _: propose(i, utils, cfg, rng, chats, summary), range(k)))
    return [{"candidate": c, "reply": r, "status": st} for c, r, st, _ in results], results[0][3]


def _propose_in_one_call(i: int, utils: list[Utility], cfg: dict, chats, summary: dict, k: int):
    from . import llm
    opt = _opt(cfg)
    u = utils[i]
    b = bounds_for(u, opt.get("bounds"))
    budget = int(cfg.get("llm", {}).get("rewrite_max_tokens", 1500))
    opponent_text = utils[1 - i].describe() if _show_opponent(cfg) else None
    prompt = {"system": llm.PARAM_SINGLE_SYSTEM if k == 1 else llm.PARAM_GROUP_SYSTEM,
              "user": llm.param_group_prompt(u, _payoffs(cfg), b, k, opt["fitness"], opponent_text,
                                             summary.get("conversation"),
                                             summary if opt.get("show_outcomes") else None)}
    text = chats[i].complete(prompt["system"], prompt["user"], max_tokens=budget)
    parsed = llm.parse_param_group(text, list(u.params()))[:k]
    if not parsed:
        return [{"candidate": None, "reply": text, "status": llm.param_status(text, None, u.params())}], prompt
    proposals = []
    for new in parsed:
        if new is None:
            proposals.append({"candidate": None, "reply": text, "status": "unparsed"})
            continue
        cand = with_params(u, new, opt.get("bounds"))
        proposals.append({"candidate": cand, "reply": text, "status": "same" if cand.params() == u.params() else "new"})
    return proposals, prompt


def _strip(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if not k.startswith("_")}


def _write_transcripts(out: Path, t: int, agent, kind: str, ev: dict) -> None:
    if "_transcripts" not in ev:
        return
    with (out / "transcripts.jsonl").open("a") as f:
        for tr in ev["_transcripts"]:
            f.write(json.dumps({"round": t, "agent": agent, "kind": kind, **tr}) + "\n")


def _save(out: Path, state: dict) -> None:
    tmp = out / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(out / "state.json")


def run(cfg: dict, out: Path, resume: bool = False, log=print) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    opt = _opt(cfg)
    if opt["schedule"] not in ("alternating", "simultaneous"):
        raise ValueError("schedule must be 'alternating' or 'simultaneous'")
    if opt["fitness"] not in ("payoff", "proposer_utility"):
        raise ValueError("optimizer.fitness must be 'payoff' or 'proposer_utility'")
    if opt["selection"] not in ("plus", "comma", "comma_random"):
        raise ValueError("optimizer.selection must be 'plus', 'comma' or 'comma_random'")
    if opt["fitness"] == "proposer_utility" and cfg["utility"]["kind"] == "text":
        raise ValueError("fitness 'proposer_utility' needs a closed-form utility")
    scored = cfg["utility"]["kind"] != "text"   # text utilities have no numeric value to judge by
    seed = int(cfg.get("seed", 0))
    chats = make_chats(cfg)
    llm = chats is not None

    state = json.loads((out / "state.json").read_text()) if resume and (out / "state.json").exists() else None
    if state is None:
        if (out / "rounds.jsonl").exists():
            raise SystemExit(f"{out} already has a run; pass --resume or choose another --out")
        (out / "config.json").write_text(json.dumps(cfg, indent=1))
        start = utility_from_dict(cfg["utility"])
        # utility_b: B's starting utility, same kind and parameters as A's; otherwise both start from utility
        start_b = utility_from_dict(cfg["utility_b"]) if "utility_b" in cfg else start
        if start_b.kind != start.kind or list(start_b.params()) != list(start.params()):
            raise ValueError("utility_b must have the same kind and parameters as utility")
        utils = [start, start_b]
        rng = np.random.default_rng(seed)
        base = evaluate(utils, cfg, rng, chats, utils if scored else None)
        _write_transcripts(out, 0, None, "baseline", base)
        last_conv = base["_transcripts"][-1]["talks"][-1] if base.get("_transcripts") and base["_transcripts"][-1].get("talks") else None
        base = _strip(base)
        state = {"round": 0, "utilities": [utility_to_dict(u) for u in utils],
                 "best": list(base["score"]), "last_eval": base, "accepted": [0, 0], "proposed": [0, 0],
                 "proposal_status": [{}, {}], "last_conversation": last_conv,
                 "agents": agent_specs(cfg) if llm else None}
        with (out / "rounds.jsonl").open("a") as f:
            f.write(json.dumps({"round": 0, "agent": None, "eval": base,
                                "utilities_after": state["utilities"], "time": time.time()}) + "\n")
        _save(out, state)
        log(f"[round 0] baseline score A {base['score'][0]:.2f} B {base['score'][1]:.2f} coop {[round(c, 2) for c in base['coop']]}")
    utils = [utility_from_dict(d) for d in state["utilities"]]

    rounds = int(opt["rounds"])
    while state["round"] < rounds:
        t = state["round"] + 1
        rng = np.random.default_rng([seed, t])
        updaters = [(t - 1) % 2] if opt["schedule"] == "alternating" else [0, 1]
        decisions = []
        for i in updaters:
            j = 1 - i
            last = state["last_eval"]
            summary = {"score": last["score"][i], "other_score": last["score"][j], "coop": last["coop"][i],
                       "other_coop": last["coop"][j], "best_score": state["best"][i],
                       "conversation": state.get("last_conversation")}
            k = int(opt.get("candidates", 1))
            proposals, prompt = propose_group(i, utils, cfg, rng, chats, summary, k)
            comma = opt["selection"] in ("comma", "comma_random")
            if comma:   # KEEP, or values equal to the incumbent's, proposes the incumbent as a candidate
                for pr in proposals:
                    if pr["candidate"] is None and pr["status"] in ("keep", "same"):
                        pr["candidate"] = utils[i]
            # distinct candidates, first reply wins; the rest of the group is still recorded
            distinct: list = []
            for pr in proposals:
                c = pr["candidate"]
                if c is not None and all(utility_to_dict(c) != utility_to_dict(d) for d in distinct):
                    distinct.append(c)
            trials = []
            for c in distinct:
                trial = list(utils); trial[i] = c; trials.append(trial)
            # comma: the incumbent competes only as a proposed candidate, so it is never evaluated separately
            need_inc = not distinct if comma else (opt["reevaluate_incumbent"] or not distinct)
            jobs = ([utils] if need_inc else []) + trials
            judges = list(utils) if scored else None   # every evaluation this turn is scored by the current utilities
            if llm and len(jobs) > 1:
                with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
                    evals = list(pool.map(lambda u_: evaluate(u_, cfg, rng, chats, judges), jobs))
            else:
                evals = [evaluate(u_, cfg, rng, chats, judges) for u_ in jobs]
            inc_eval = evals.pop(0) if need_inc else last
            key = lambda c: json.dumps(utility_to_dict(c), sort_keys=True)
            cand_evals = dict(zip((key(c) for c in distinct), evals))
            fit = "judged" if opt["fitness"] == "proposer_utility" else "score"
            _write_transcripts(out, t, i, "incumbent", inc_eval)
            for pr in proposals:
                state["proposal_status"][i][pr["status"]] = state["proposal_status"][i].get(pr["status"], 0) + 1
            cand, cand_eval = None, None
            if distinct:
                state["proposed"][i] += len(distinct)
                for n_c, c in enumerate(distinct):
                    _write_transcripts(out, t, i, f"candidate{n_c}" if len(distinct) > 1 else "candidate",
                                       cand_evals[key(c)])
                if opt["selection"] == "comma_random":
                    cand = distinct[int(rng.integers(len(distinct)))]
                else:   # ties are broken at random, not by the order the proposer listed them
                    top = max(cand_evals[key(c)][fit][i] for c in distinct)
                    tied = [c for c in distinct if cand_evals[key(c)][fit][i] >= top - 1e-9]
                    cand = tied[int(rng.integers(len(tied)))] if len(tied) > 1 else tied[0]
                cand_eval = cand_evals[key(cand)]
            if comma:
                accepted = cand is not None
            else:   # plus: the best distinct candidate competes with the incumbent
                accepted = bool(cand is not None and cand_eval[fit][i] >= inc_eval[fit][i] + float(opt["accept_margin"]))
            conv_eval = cand_eval if comma and accepted else inc_eval
            if conv_eval.get("_transcripts") and conv_eval["_transcripts"][-1].get("talks"):
                state["last_conversation"] = conv_eval["_transcripts"][-1]["talks"][-1]
            ranked = sorted(distinct, key=lambda c: -cand_evals[key(c)][fit][i])
            group = []
            for pr in proposals:
                c = pr["candidate"]
                ev = cand_evals.get(key(c)) if c is not None else None
                group.append({"reply": pr["reply"], "status": pr["status"],
                              "candidate": utility_to_dict(c) if c is not None else None,
                              "eval": _strip(ev) if ev else None,
                              "rank": next(n for n, d in enumerate(ranked) if key(d) == key(c)) if c is not None else None})
            chosen = next((g for g in group if cand is not None and g["candidate"] == utility_to_dict(cand)), group[0])
            if cand is not None and key(cand) == key(utils[i]):
                state.setdefault("kept", [0, 0])[i] += 1
            decisions.append({"agent": i, "incumbent": utility_to_dict(utils[i]),
                              "candidate": utility_to_dict(cand) if cand is not None else None,
                              "proposal_reply": chosen["reply"], "proposal_status": chosen["status"],
                              "proposal_prompt": prompt, "proposals": group, "fitness": opt["fitness"],
                              "selection": opt["selection"], "inc_eval": _strip(inc_eval),
                              "cand_eval": _strip(cand_eval) if cand_eval else None, "accepted": accepted, "_cand": cand})
        for d in decisions:   # adopt together: simultaneous candidates were each judged against the old opponent
            if d["accepted"]:
                utils[d["agent"]] = d["_cand"]
                state["accepted"][d["agent"]] += 1
        if len(decisions) == 1:
            d = decisions[0]
            after = d["cand_eval"] if d["accepted"] else d["inc_eval"]
        elif any(d["accepted"] for d in decisions):
            after = evaluate(utils, cfg, rng, chats, utils if scored else None)
            _write_transcripts(out, t, None, "after", after)
            after = _strip(after)
        else:
            after = decisions[0]["inc_eval"]
        state["round"] = t
        state["utilities"] = [utility_to_dict(u) for u in utils]
        state["last_eval"] = after
        state["best"] = [max(state["best"][k], after["score"][k]) for k in range(2)]
        if llm:
            state["usage"] = [c.usage() for c in chats]
        with (out / "rounds.jsonl").open("a") as f:
            for d in decisions:
                row = {k: v for k, v in d.items() if k != "_cand"}
                row.update({"round": t, "eval": after, "utilities_after": state["utilities"], "time": time.time()})
                f.write(json.dumps(row) + "\n")
        _save(out, state)
        who = ",".join("AB"[d["agent"]] + ("+" if d["accepted"] else "-") for d in decisions)
        desc = " | ".join(f"{n} {u.describe()[:90]}" for n, u in zip("AB", utils))
        log(f"[round {t}] {who} score A {after['score'][0]:.2f} B {after['score'][1]:.2f} "
            f"coop A {after['coop'][0]:.2f} B {after['coop'][1]:.2f} | {desc}")
    return state
