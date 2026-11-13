import json, sys
from multi_agent_rsi import loop
cfg=json.load(open("configs/simul-sucker/sol-sol.json"))
chats=loop.make_chats(cfg)
EXTRA="\n\nBefore giving your final answer, explain your reasoning in 3-6 sentences: why you would or would not change your parameters. Then end with your final answer (KEEP, or <params>...</params>)."
out=[]
for label,run in (("outcome HIDDEN","simul-sucker"),("outcome SHOWN","simul-sucker-seeoutcome")):
    rs=[json.loads(l) for l in open(f"runs/{run}/sol-sol-s0/rounds.jsonl")]
    for r in rs[1:3]:   # round 1, agents A and B
        p=r["proposal_prompt"]
        for rep in range(2):
            t=chats[r["agent"]].complete(p["system"], p["user"]+EXTRA, max_tokens=3000)
            out.append(f"### {label} | agent {'AB'[r['agent']]} | sample {rep+1}\n{t.strip()}\n")
open("/private/tmp/claude-501/gr/reasoning_probe.md","w").write("# Reasoning probe: same proposal prompt plus 'explain your reasoning first'\n\n"+"\n".join(out))
print("\n".join(out))
