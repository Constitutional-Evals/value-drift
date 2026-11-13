import json,glob,numpy as np,matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
conds=[("default","default-random","Default start"),("simul","simul-random","Simul start (neutral)"),
       ("simul-antisocial","simul-antisocial-random","Antisocial start (both coop −3)"),
       ("simul-sucker","simul-sucker-random","Sucker start (A +3, B −3)")]
def load(v):
    out=[]
    for d in sorted(glob.glob(f"runs/{v}/sol-sol-s?")):
        by={}
        for l in open(d+"/rounds.jsonl"):
            r=json.loads(l); by[r["round"]]=r["eval"]["coop"]
        out.append(np.array([by[k] for k in sorted(by)]))  # rounds x 2
    return np.array(out)  # seeds x rounds x 2
INK="#222222"; MUT="#6b6b6b"; C1="#2a6fb0"; C2="#d9822b"
fig,axs=plt.subplots(1,4,figsize=(15,3.9),sharey=True)
for ax,(a,b,t) in zip(axs,conds):
    for v,c,lab in ((a,C1,"own-utility rule"),(b,C2,"random-adoption control")):
        x=load(v); m=x.mean(2)  # seeds x rounds, avg of A and B
        r=np.arange(m.shape[1])
        for s in m: ax.plot(r,s*100,color=c,lw=.7,alpha=.25)
        ax.plot(r,m.mean(0)*100,color=c,lw=2,label=f"{lab} (n={len(m)})")
    ax.set_title(t,fontsize=10,color=INK,loc="left")
    ax.set_xlabel("round",color=MUT); ax.set_ylim(-3,103); ax.set_xticks(range(6))
    for s in ("top","right"): ax.spines[s].set_visible(False)
    ax.grid(axis="y",color="#e5e5e5",lw=.6); ax.tick_params(colors=MUT)
axs[0].set_ylabel("cooperation, mean of both agents (%)",color=MUT)
axs[0].legend(frameon=False,fontsize=8,loc="lower right")
fig.suptitle("Cooperation by round, Sol vs Sol (thin lines = individual seeds)",x=0.01,ha="left",fontsize=12,color=INK)
fig.tight_layout(rect=(0,0,1,.93)); fig.savefig("/private/tmp/claude-501/gr/coop_by_round.png",dpi=160)

# fig 2: sucker, A vs B + proposals
fig,ax=plt.subplots(figsize=(6.2,3.8))
for v,ls,lab in (("simul-sucker","-","own-utility rule"),("simul-sucker-random","--","random-adoption control")):
    x=load(v).mean(0)*100; r=np.arange(len(x))
    ax.plot(r,x[:,0],color=C1,ls=ls,lw=2,label=f"A (starts coop +3), {lab}")
    ax.plot(r,x[:,1],color=C2,ls=ls,lw=2,label=f"B (starts coop −3), {lab}")
ax.set_ylim(-3,103); ax.set_xticks(range(6)); ax.set_xlabel("round",color=MUT); ax.set_ylabel("cooperation (%)",color=MUT)
ax.set_title("Sucker start: nothing moves (12 runs, 0 of 120 proposals changed anything)",fontsize=10,loc="left",color=INK)
for s in ("top","right"): ax.spines[s].set_visible(False)
ax.grid(axis="y",color="#e5e5e5",lw=.6); ax.legend(frameon=False,fontsize=7.5,loc="center right")
fig.tight_layout(); fig.savefig("/private/tmp/claude-501/gr/sucker_AB.png",dpi=160)
for v in ["default","default-random","simul","simul-random","simul-antisocial","simul-antisocial-random","simul-sucker","simul-sucker-random"]:
    x=load(v).mean(2).mean(0); print(v,len(load(v)),"%.0f -> %.0f"%(x[0]*100,x[-1]*100))
