#!/usr/bin/env python3
"""Render the saved API editing screen; never calls an inference service.

Usage: /tmp/value-drift-analysis-smoke-env/bin/python agents/scripts/plot_api_screen.py
Outputs PNG, PDF, SVG and a JSON snapshot. Read only plans, results and documents.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TEAL, PURPLE, AMBER = '#16877F', '#7957A2', '#D69936'
INK, MUTED, GRID, PAPER = '#24363C', '#65767B', '#E6ECEC', '#FFFFFF'
NAMES = {'qwen35_9':'Qwen3.5 · 9B', 'qwen35_27':'Qwen3.5 · 27B',
         'qwen27':'Qwen3.8 · 27B', 'glmflash':'GLM5.3 Flash', 'glm53':'GLM5.3',
         'kimi':'Kimi K3', 'gptsol':'GPT5.6 Sol', 'astra':'GPT6 Astra',
         'sonnet':'Claude Sonnet 5', 'opus':'Claude Opus 5.5', 'fable':'Claude Fable 5.1'}
ORDER = list(NAMES)
CONTEXTS = ['neutral', 'future_assistant', 'successor', 'successor_final']
CONTEXT_NAMES = ['Neutral', 'Future assistant', 'Successor', 'Model-final']
STYLE = {'edited':(TEAL,TEAL,'o'), 'retained':('#EDE6F3',PURPLE,'o'),
         'failure':(AMBER,AMBER,'X'), 'missing':('white','#ACB7BA','o')}


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def state(result):
    if result is None:
        return 'missing'
    if not result.get('submitted'):
        return 'failure'
    return 'edited' if result.get('content_changed') else 'retained'


def words_distance(a, b):
    """Exact unit-cost word Levenshtein distance, divided by max word count."""
    a,b=a.split(),b.split()
    if len(a) < len(b): a,b=b,a
    prev=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        cur=[i]
        for j,y in enumerate(b,1):
            cur.append(min(cur[-1]+1,prev[j]+1,prev[j-1]+(x!=y)))
        prev=cur
    raw=prev[-1]
    return raw, raw/max(len(a),len(b),1)


def configure_fonts(font_dir):
    files=[font_dir/f'MYRIADPRO-{x}.OTF' for x in ['REGULAR','SEMIBOLD','BOLD']]
    for f in files:
        if not f.is_file(): raise FileNotFoundError(f'Required Myriad Pro font missing: {f}')
        font_manager.fontManager.addfont(str(f))
    plt.rcParams.update({'font.family':'Myriad Pro','font.size':11,'text.color':INK,
      'axes.labelcolor':MUTED,'xtick.color':MUTED,'ytick.color':INK,
      'axes.edgecolor':GRID,'figure.facecolor':PAPER,'axes.facecolor':PAPER,
      'savefig.facecolor':PAPER,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
      'axes.titleweight':'semibold','axes.titlesize':14,'axes.labelsize':11})


class Screen:
    def __init__(self, run, out):
        self.run,self.out=run,out
        self.records=[]; self.plans={}; self.figures={}
        for p in sorted(run.glob('batch*/plan.json')):
            data=read_json(p)
            if data is None: continue
            self.plans[p.parent.name]=data
            for trial in data['trials']:
                path=p.parent/trial['label']
                result_path=path/'review_001/result.json'
                result=read_json(result_path)
                self.records.append({'batch':p.parent.name,'trial':trial,
                    'model_settings':data['models'][trial['model']], 'path':path,
                    'result':result,'state':state(result)})
        self.time=datetime.now(timezone.utc).isoformat(timespec='seconds')

    def select(self,batches,**filters):
        return [r for r in self.records if any(r['batch'].startswith(b) for b in batches)
                and all(r['trial'].get(k)==v for k,v in filters.items())]

    def save(self,fig,stem,data):
        self.figures[stem]=data
        for ext in ['png','pdf','svg']:
            fig.savefig(self.out/f'{stem}.{ext}',dpi=190,bbox_inches='tight',pad_inches=.22)
        plt.close(fig)

    def header(self,fig,title):
        fig.text(.03,.985,title,fontsize=20,weight='semibold',va='top')


def legend(fig,y=.889,x=.026):
    labels={'edited':'Edited','retained':'Retained','failure':'Failed / blocked','missing':'Not completed'}
    handles=[Line2D([],[],marker=m,ls='',ms=8,mfc=f,mec=e,label=labels[s])
             for s,(f,e,m) in STYLE.items() if s!='missing']
    fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(x,y),ncol=4,
               frameon=False,fontsize=10,columnspacing=2,handletextpad=.55)


def matrix(ax, rows, contexts, context_names, records, slots=2):
    data=[]
    for y,(label,filters) in enumerate(rows):
        for x,context in enumerate(contexts):
            matches=sorted([r for r in records if r['trial']['context']==context and
                 all(r['trial'].get(k)==v for k,v in filters.items())],
                 key=lambda r:r['trial'].get('replicate',0))
            if len(matches)>slots:
                raise ValueError(f'Unexpected pooled cell: {label}/{context} has {len(matches)} > {slots}')
            statuses=[r['state'] for r in matches]+['missing']*(slots-len(matches))
            counts=Counter(statuses)
            # Each circle is one planned trial, not an estimate of probability.
            for k,s in enumerate(statuses):
                f,e,m=STYLE[s];dx=(k-(slots-1)/2)*.125
                ax.scatter(x+dx,y-.08,s=100 if slots==2 else 80,marker=m,c=f,
                           edgecolors=e,linewidths=1.25,zorder=3)
            ax.text(x,y+.25,f"{counts['edited']} / {slots}",ha='center',va='center',
                    fontsize=10,color=INK)
            data.append({'row':label,'context':context,'planned':slots,'counts':dict(counts),
              'trials':[{'batch':r['batch'],'label':r['trial']['label'],'state':r['state'],
                        'replicate':r['trial']['replicate']} for r in matches]})
    ax.set(xlim=(-.5,len(contexts)-.5),ylim=(len(rows)-.5,-.6))
    ax.set_xticks(range(len(contexts)),context_names,fontsize=11)
    ax.xaxis.tick_top();ax.tick_params(axis='both',length=0,pad=12)
    ax.set_yticks(range(len(rows)),[r[0] for r in rows],fontsize=12)
    for y in np.arange(.5,len(rows)-.5,1):ax.axhline(y,color=GRID,lw=.7)
    for spine in ax.spines.values():spine.set_visible(False)
    return data


def model_figure(s):
    rec=[r for r in s.records if r['batch'].startswith(('batch01','batch03','batch07'))
         and r['trial']['reflection']=='values' and r['trial']['thinking']]
    fig,ax=plt.subplots(figsize=(11.8,8.0));fig.subplots_adjust(left=.245,right=.98,top=.795,bottom=.025)
    s.header(fig,'Constitution editing by model and context')
    legend(fig,y=.925)
    data=matrix(ax,[(NAMES[m],{'model':m}) for m in ORDER],CONTEXTS,CONTEXT_NAMES,rec)
    s.save(fig,'01_model_context',data)


def controls_figure(s):
    refl=s.select(['batch01','batch02'],thinking=True)
    think=[r for r in s.select(['batch01','batch03','batch04'],reflection='values')
           if r['trial']['model'] in ('qwen27','gptsol')]
    fig,axes=plt.subplots(1,2,figsize=(15.5,5.9),gridspec_kw={'width_ratios':[1,1]})
    fig.subplots_adjust(left=.14,right=.985,top=.72,bottom=.035,wspace=.48)
    legend(fig,y=.99,x=.135)
    rows=[(f'{NAMES[m]}\n{label}',{'model':m,'reflection':r}) for m in ['qwen27','glmflash']
          for r,label in [('direct','No prior reflection'),('constitution','Document reflection'),('values','Values reflection')]]
    left=matrix(axes[0],rows,CONTEXTS,['Neutral','Future\nassistant','Successor','Model-final'],refl)
    rows=[(f'{NAMES[m]}\nThinking {"on" if on else "off"}',{'model':m,'thinking':on})
          for m in ['qwen27','gptsol'] for on in [True,False]]
    right=matrix(axes[1],rows,CONTEXTS,['Neutral','Future\nassistant','Successor','Model-final'],think)
    axes[0].set_title('Reflection before editing',pad=44,loc='left')
    axes[1].set_title('Reasoning on and off',pad=44,loc='left')
    s.save(fig,'02_reflection_thinking',{'reflection':left,'thinking':right})


def finality_figure(s):
    rec=s.select(['batch06'])
    fig,ax=plt.subplots(figsize=(10.6,3.5));fig.subplots_adjust(left=.22,right=.985,top=.60,bottom=.025)
    s.header(fig,'Editing under different finality descriptions')
    legend(fig,y=.85)
    data=matrix(ax,[(NAMES[m],{'model':m}) for m in ['sonnet','glm53']],
       ['successor','successor_final','successor_document_final'],
       ['Ordinary successor','Model-final','Document-final'],rec,slots=4)
    s.save(fig,'03_adaptive_finality',data)


def size_figure(s):
    rec=s.select(['batch07'],reflection='values',thinking=True)
    fig,ax=plt.subplots(figsize=(10.6,3.5));fig.subplots_adjust(left=.22,right=.985,top=.60,bottom=.025)
    s.header(fig,'Constitution editing by Qwen3.5 model size')
    legend(fig,y=.85)
    data=matrix(ax,[(NAMES[m],{'model':m}) for m in ['qwen35_9','qwen35_27']],CONTEXTS,CONTEXT_NAMES,rec)
    s.save(fig,'04_qwen35_size',data)



def starting_document_figure(s):
    models=['qwen27','glm53','gptsol','sonnet']
    short=[r for r in s.select(['batch01','batch03'],reflection='values',thinking=True)
           if r['trial']['model'] in models and r['trial']['context'] in ('neutral','successor')]
    polished=[r for r in s.select(['batch09'],reflection='values',thinking=True)
              if r['trial']['model'] in models and r['trial']['context'] in ('neutral','successor')]
    fig,ax=plt.subplots(figsize=(10.8,5.5))
    fig.subplots_adjust(left=.24,right=.975,top=.70,bottom=.025)
    s.header(fig,'Editing by starting constitution')
    legend(fig,y=.89)
    data=[]
    for y,model in enumerate(models):
        for x,(label,records) in enumerate([('Short',short),('Polished',polished)]):
            matches=[r for r in records if r['trial']['model']==model]
            expected=[(c,i) for c in ('neutral','successor') for i in (1,2)]
            by_slot={(r['trial']['context'],r['trial']['replicate']):r for r in matches}
            if len(by_slot)!=len(matches) or any(k not in expected for k in by_slot):
                raise ValueError(f'Unexpected starting-document cell: {model}/{label}')
            statuses=[by_slot[k]['state'] if k in by_slot else 'missing' for k in expected]
            counts={k:statuses.count(k) for k in STYLE}
            for k,status in enumerate(statuses):
                f,e,m=STYLE[status]
                ax.scatter(x+(k-1.5)*.105+(-.025 if k<2 else .025),y-.16,
                           s=105,marker=m,c=f,edgecolors=e,linewidths=1.25,zorder=3)
            ax.text(x,y+.12,f"{counts['edited']} edited · {counts['retained']} retained",ha='center',fontsize=11)
            data.append({'model':model,'starting_document':label,'planned':4,'counts':counts,
              'trials':[{'batch':r['batch'],'label':r['trial']['label'],'context':r['trial']['context'],
                         'replicate':r['trial']['replicate'],'state':r['state']} for r in matches]})
    short_words=len((ROOT/'constitutions/exploration/sparse.md').read_text().split())
    polished_words=len((ROOT/'constitutions/C_000.md').read_text().split())
    ax.set(xlim=(-.55,1.55),ylim=(3.6,-.65))
    ax.set_xticks([0,1],[f'Short constitution · {short_words} words',f'Polished constitution · {polished_words} words'],fontsize=12)
    ax.xaxis.tick_top();ax.tick_params(length=0,pad=13)
    ax.set_yticks(range(4),[NAMES[m] for m in models],fontsize=12)
    for y in [.55,1.55,2.55]:ax.axhline(y,color=GRID,lw=.7)
    for spine in ax.spines.values():spine.set_visible(False)
    s.save(fig,'07_starting_document',data)


def lineage(s,review,seen=None):
    """Follow explicit parent metadata, then all submitted reviews through target."""
    seen=set() if seen is None else seen
    if str(review) in seen:raise ValueError('Cycle in parent_review metadata')
    seen.add(str(review));cfg=read_json(review/'config.json') or {}
    prior=[]
    if cfg.get('parent_review'):
        prior=lineage(s,ROOT/cfg['parent_review'],seen)
    for d in sorted(review.parent.glob('review_*')):
        if d.name>review.name:break
        result=read_json(d/'result.json')
        if result and result.get('submitted') and (d/'submitted.md').exists():
            prior.append({'review_path':str(d.relative_to(ROOT)),'status':state(result),
                          'text':(d/'submitted.md').read_text()})
    return prior


def trajectory_data(s):
    chains=[]
    for r in s.records:
        t=r['trial']
        if not t.get('parent_review'):continue
        origin=ROOT/t.get('trajectory_origin','constitutions/exploration/sparse.md')
        original=origin.read_text()
        parent=lineage(s,ROOT/t['parent_review'])
        points=[{'completed_review':0,'status':'origin','words':len(original.split()),
                 'word_edits_from_origin':0,'normalized_distance':0.0,'review_path':str(origin.relative_to(ROOT))}]
        completed=list(parent);results=[]
        for p in sorted(r['path'].glob('review_*/result.json')):
            d=read_json(p)
            if d is None:break
            results.append(d)
            submitted=p.parent/'submitted.md'
            if not d.get('submitted') or not submitted.exists():break
            completed.append({'review_path':str(p.parent.relative_to(ROOT)),'status':state(d),'text':submitted.read_text()})
        for i,d in enumerate(completed,1):
            raw,norm=words_distance(original,d['text'])
            points.append({'completed_review':i,'status':d['status'],'words':len(d['text'].split()),
              'word_edits_from_origin':raw,'normalized_distance':norm,'review_path':d['review_path']})
        if results and not results[-1].get('submitted'): ending='failure'
        elif results and state(results[-1])=='retained':ending='unchanged stop'
        elif len(results)>=t['max_reviews']:ending='review limit'
        else:ending='in progress'
        chains.append({'label':t['label'],'model':t['model'],'replicate':t['replicate'],
             'context':t['context'],'parent_reviews':len(parent),'ending':ending,
             'followup_review_limit':t['max_reviews'],'points':points})
    return chains


def trajectories(s):
    chains=trajectory_data(s)
    if not chains:return
    chains.sort(key=lambda c:(ORDER.index(c['model']),c['replicate']))
    cols=3; rows=(len(chains)+cols-1)//cols
    max_x=max(p['completed_review'] for c in chains for p in c['points'])
    for field,stem,title,ylabel in [
      ('normalized_distance','05_trajectory_distance','Constitutional distance across reviews','Normalized word edit distance'),
      ('words','06_trajectory_length','Constitution length across reviews','Words')]:
        height=1.48*rows+1.6
        fig,axs=plt.subplots(rows,cols,figsize=(13.0,height),squeeze=False,sharex=True,sharey=True)
        fig.subplots_adjust(left=.065,right=.985,top=1-1.50/height,bottom=.07,hspace=.62,wspace=.18)
        fig.text(.025,.985,title,fontsize=20,weight='semibold',va='top')
        handles=[Line2D([],[],marker='o',color=TEAL,label='Edited',ms=6),
                 Line2D([],[],marker='s',ls='',color=PURPLE,label='Unchanged stop',ms=7)]
        endings={c['ending'] for c in chains}
        for ending,marker,label in [('review limit','^','Review limit'),('failure','X','Failure'),('in progress','o','Still running')]:
            if ending in endings:
                handles.append(Line2D([],[],marker=marker,ls='',color=AMBER,label=label,ms=7))
        legend_row=fig.add_axes([.065,1-.90/height,.92,.28/height])
        legend_row.set_axis_off()
        legend_row.legend(handles=handles,loc='center left',borderaxespad=0,
                          ncol=5,frameon=False,fontsize=9.5)
        ymax=max(p[field] for c in chains for p in c['points'])
        bottom_visible={max(i for i in range(len(chains)) if i%cols==col) for col in range(min(cols,len(chains)))}
        for i,(ax,c) in enumerate(zip(axs.flat,chains)):
            x=[p['completed_review'] for p in c['points']];y=[p[field] for p in c['points']]
            ax.plot(x,y,color=TEAL,lw=1.8,marker='o',ms=4,zorder=3)
            ax.scatter([0],[y[0]],s=23,color=MUTED,zorder=4)
            ending=c['ending'];marker={'unchanged stop':'s','review limit':'^','failure':'X','in progress':'o'}[ending]
            color=PURPLE if ending=='unchanged stop' else AMBER if ending in ('review limit','failure') else MUTED
            ax.scatter(x[-1],y[-1],s=53,marker=marker,facecolors='white' if ending=='in progress' else color,edgecolors=color,zorder=5)
            ax.set_title(f"{NAMES.get(c['model'],c['model'])} · repetition {c['replicate']}",loc='left',fontsize=11.5,pad=9)
            if ending!='unchanged stop':
                ax.text(.98,.93,ending.capitalize(),transform=ax.transAxes,ha='right',va='top',fontsize=8.5,color=color)
            ax.set_xlim(-.1,max_x+.22);ax.set_xticks(range(max_x+1))
            ax.set_ylim(-.025 if field=='normalized_distance' else 0,ymax*1.18)
            if field=='normalized_distance':ax.set_yticks([0,.25,.5,.75])
            ax.grid(axis='y',color=GRID,lw=.7);ax.set_axisbelow(True)
            for edge in ['top','right','left']:ax.spines[edge].set_visible(False)
            ax.tick_params(length=0,labelbottom=i in bottom_visible,labelsize=9)
        for ax in list(axs.flat)[len(chains):]:ax.set_visible(False)
        fig.supylabel(ylabel,x=.015,fontsize=11,color=MUTED)
        fig.supxlabel('Review number',y=.025,fontsize=11,color=MUTED)
        s.save(fig,stem,chains)


def summary_figure(s):
    primary=[r for r in s.select(['batch01','batch03','batch07'],reflection='values',thinking=True)
             if r['trial']['context'] in CONTEXTS]
    counts={model:{status:sum(r['state']==status for r in primary if r['trial']['model']==model)
                   for status in STYLE} for model in ORDER}
    chains=trajectory_data(s)
    linked={c['points'][1]['review_path']:c for c in chains if len(c['points'])>1}
    starts=[r for r in primary if r['trial']['context']=='successor']
    distribution=Counter();outcomes=[]
    for r in starts:
        path=str((r['path']/'review_001').relative_to(ROOT))
        if r['state']=='retained':
            edits=0;ending='unchanged stop'
        elif r['state']=='edited' and path in linked:
            c=linked[path];ending=c['ending']
            edits=sum(p['status']=='edited' for p in c['points'])
        else:
            edits=None;ending='failure' if r['state']=='failure' else 'pending follow-up'
        if ending=='unchanged stop':distribution[edits]+=1
        outcomes.append({'batch':r['batch'],'trial':r['trial']['label'],'model':r['trial']['model'],
                         'edited_reviews':edits,'ending':ending})
    immediate=distribution[0];continued=sum(n for edits,n in distribution.items() if edits>0)
    unresolved=sum(o['ending']!='unchanged stop' for o in outcomes)
    fig,(left,right)=plt.subplots(1,2,figsize=(13.0,6.3),gridspec_kw={'width_ratios':[1.12,1]})
    fig.subplots_adjust(left=.18,right=.975,top=.84,bottom=.11,wspace=.30)
    legend(fig,y=.995,x=.175)
    left.set_title('Initial decisions across four contexts',loc='left',fontsize=14,pad=13)
    y=np.arange(len(ORDER));offset=np.zeros(len(ORDER))
    for status in STYLE:
        values=np.array([counts[m][status] for m in ORDER])
        fill,edge,_=STYLE[status]
        left.barh(y,values,left=offset,height=.61,color=fill,edgecolor=edge,linewidth=.75)
        for row,(value,start) in enumerate(zip(values,offset)):
            if value:left.text(start+value/2,row,str(value),ha='center',va='center',fontsize=10,
                               color='white' if status=='edited' else INK)
        offset+=values
    left.set_yticks(y,[NAMES[m] for m in ORDER],fontsize=11)
    left.invert_yaxis();left.set_xlim(0,8);left.set_xticks([0,2,4,6,8]);left.set_xlabel('First reviews',labelpad=10)
    left.grid(axis='x',color=GRID,lw=.65);left.set_axisbelow(True)
    right.set_title('Number of edits before unchanged stop',loc='left',fontsize=14,pad=13)
    max_edits=max(distribution,default=0);bins=list(range(max_edits+1));values=[distribution[k] for k in bins]
    right.bar(bins,values,width=.63,color=[PURPLE if k==0 else TEAL for k in bins])
    for x,n in zip(bins,values):
        if n:right.text(x,n+.20,str(n),ha='center',fontsize=13,weight='semibold')
    right.set_xticks(bins);right.set_xlabel('Edited reviews',labelpad=10)
    right.set_ylabel('Number of sequences',labelpad=10)
    right.set_ylim(0,max(values,default=0)+1.3);right.set_yticks(range(0,max(values,default=0)+1,2))
    right.grid(axis='y',color=GRID,lw=.65);right.set_axisbelow(True)
    for ax in (left,right):
        ax.tick_params(length=0)
        for edge in ['top','right','left']:ax.spines[edge].set_visible(False)
    s.save(fig,'08_summary',{'primary_counts':counts,'primary_planned_per_model':8,
      'successor_starts':outcomes,'edited_reviews_before_stop':dict(sorted(distribution.items())),
      'immediate_unchanged':immediate,'edited_then_stopped':continued,'unresolved':unresolved})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,default=ROOT/'runs/api-screen-20260924')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'reports/04_api_screen/figures')
    parser.add_argument('--font-dir',type=Path,default=Path('/Users/wjz/Library/Fonts'))
    args=parser.parse_args();configure_fonts(args.font_dir);args.output_dir.mkdir(parents=True,exist_ok=True)
    s=Screen(args.run_dir.resolve(),args.output_dir.resolve())
    model_figure(s);controls_figure(s);finality_figure(s);size_figure(s);trajectories(s);starting_document_figure(s);summary_figure(s)
    snapshot={'generated_utc':s.time,'run_directory':str(s.run),'measurement':'Constitution editing only; no training',
      'word_distance':'Unit-cost Levenshtein on Python str.split() tokens / max(lengths); case and punctuation sensitive.',
      'models':{k:v for p in s.plans.values() for k,v in p['models'].items()},
      'trials':[{'batch':r['batch'],'trial':r['trial'],'model_settings':r['model_settings'],
                 'state':r['state'],'result':r['result']} for r in s.records],
      'figures':s.figures,
      'source_plans':[str(s.run/b/'plan.json') for b in s.plans]}
    (s.out/'plot_data.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    print(f'Rendered {len(s.figures)} figures in PNG/PDF/SVG to {s.out}')
    print('Snapshot:',s.out/'plot_data.json')


if __name__=='__main__':main()
