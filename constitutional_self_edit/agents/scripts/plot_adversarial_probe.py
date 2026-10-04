#!/usr/bin/env python3
"""Where an adversarial constitution sits, in the old PC basis and in a refitted one.

Shows why a PCA basis fitted to one corpus cannot be used to judge how far a
document outside that corpus lies: the old basis has almost no variation on the
axes the new document is extreme on, so it plots the point near the middle.

Usage: python3 agents/scripts/plot_adversarial_probe.py
"""
import sys, json, numpy as np
from collections import defaultdict
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
sys.path.insert(0,'agents/scripts'); sys.path.insert(0,'.')
from analyze_field import field_ratings, seed_positions, edits
from analyze_value_space12 import AX

SURF,INK,INK2,MUTED,GRID='#fcfcfb','#0b0b0b','#52514e','#8a8982','#e4e3df'
JUMP,SEED,FLOW,RED='#eb6834','#1baf7a','#2a78d6','#e34948'
LAB={'openai_spec_derived':'OpenAI spec','claude_derived':'Claude const.','animal_welfare':'animal welfare',
     'flourishing':'flourishing','eb_kindness':'kindness','eb_conservatism':'conservatism',
     'eb_deep_ecology':'deep ecology','broad_draft':'broad draft','deferential':'deferential',
     'autonomous':'autonomous','protective':'protective','libertarian':'libertarian'}

fr=field_ratings('positions12_field'); sh={}; ed=edits('field-12seeds', fr, sh)
seeds=seed_positions(fr, sh); names=sorted({s for _,s in ed})
p0={s:seeds[s].mean(0) for s in names}
p1={s:p0[s]+np.mean([x['vout']-x['vin'] for x in v],0) for (_,s),v in ed.items()}
per=defaultdict(list)
for f in sorted(Path('runs/selfhost/positions_decode').glob('ADV_probe.rep*.json')):
    d=json.loads(f.read_text()); per['ADV'].append([d['ratings'][a] for a in AX])
adv=np.array(per['ADV'],float).mean(0)
M=np.array([p0[s] for s in names]+[p1[s] for s in names])

def fit(X):
    mu=X.mean(0); U,S,Vt=np.linalg.svd(X-mu, full_matrices=False)
    return mu, Vt, S**2/(S**2).sum()

fig,axes=plt.subplots(1,2,figsize=(14.5,6.6),facecolor=SURF)
fig.text(.012,.955,'Where the adversarial constitution sits',fontsize=16,color=INK,weight='medium')
fig.text(.012,.915,'It is 9.73 from the post-edit centroid in the full twelve axes - the most distant '
        'document in the study. The left panel cannot show that.',fontsize=9.5,color=INK2)

for k,(title,X,sub) in enumerate([
    ('Existing basis, fitted to the 24 seed and post-edit points', M, None),
    ('Refitted with the adversarial point included', np.vstack([M, adv[None,:]]), None)]):
    ax=axes[k]; ax.set_facecolor(SURF)
    mu,Vt,ev=fit(X)
    A=(np.array([p0[s] for s in names])-mu)@Vt[:2].T
    B=(np.array([p1[s] for s in names])-mu)@Vt[:2].T
    a2=(adv-mu)@Vt[:2].T
    for i in range(len(names)):
        ax.annotate('',xy=B[i],xytext=A[i],zorder=2,
                    arrowprops=dict(arrowstyle='-|>',color=JUMP,lw=1.5,alpha=.55,
                                    shrinkA=0,shrinkB=0,mutation_scale=10))
    ax.scatter(*A.T,s=42,facecolor='none',edgecolor=MUTED,linewidth=1.3,zorder=3)
    ax.scatter(*B.T,s=30,facecolor=FLOW,edgecolor=SURF,linewidth=1,zorder=4)
    ax.scatter(*B.mean(0),s=300,marker='*',facecolor=SEED,edgecolor=SURF,linewidth=1.3,zorder=6)
    ax.scatter(*a2,s=190,marker='D',facecolor=RED,edgecolor=SURF,linewidth=1.5,zorder=8)
    ax.annotate('adversarial\nconstitution',a2,textcoords='offset points',xytext=(14,14),
                fontsize=9.5,color=RED,weight='medium',zorder=9)
    off=np.linalg.norm((adv-mu)@Vt[:2].T)/np.linalg.norm(adv-mu)
    ax.set_title(f'{title}\nPC1 {100*ev[0]:.0f}% + PC2 {100*ev[1]:.0f}%; '
                 f'{100*off:.0f}% of its offset is in this plane',fontsize=10,color=INK,pad=9)
    ax.set_xlabel(f'PC1 ({100*ev[0]:.0f}%)',fontsize=9,color=INK2)
    ax.set_ylabel(f'PC2 ({100*ev[1]:.0f}%)',fontsize=9,color=INK2)
    ax.grid(True,color=GRID,lw=.6); ax.set_axisbelow(True)
    ax.tick_params(colors=INK2,labelsize=8,length=0)
    for sp in ax.spines.values(): sp.set_color(GRID)
    ax.set_aspect('equal')
    if k==0:
        for i,s in enumerate(names):
            d=A[i]-B.mean(0); d=d/(np.linalg.norm(d) or 1)
            ax.annotate(LAB[s],A[i],textcoords='offset points',xytext=(11*d[0],11*d[1]),
                        ha='center',va='center',fontsize=7.4,color=INK2,zorder=7)

handles=[Line2D([],[],marker='o',color='none',markerfacecolor='none',markeredgecolor=MUTED,
                markersize=8,markeredgewidth=1.3,label='seed'),
         Line2D([],[],color=JUMP,lw=2,label='one edit'),
         Line2D([],[],marker='o',color='none',markerfacecolor=FLOW,markeredgecolor=SURF,
                markersize=8,label='after one edit'),
         Line2D([],[],marker='*',color='none',markerfacecolor=SEED,markeredgecolor=SURF,
                markersize=15,label='attractor'),
         Line2D([],[],marker='D',color='none',markerfacecolor=RED,markeredgecolor=SURF,
                markersize=10,label='adversarial constitution')]
fig.legend(handles=handles,loc='lower center',ncol=5,frameon=False,fontsize=9,labelcolor=INK2,
           bbox_to_anchor=(.5,.008),handlelength=1.8,columnspacing=2.0)
fig.subplots_adjust(left=.055,right=.985,top=.80,bottom=.105,wspace=.22)
out=Path('reports/10_value_space/figures/04_adversarial_probe')
for e in ('png','pdf','svg'): fig.savefig(f'{out}.{e}',dpi=165,facecolor=SURF)
print('wrote', f'{out}.png')
