#!/usr/bin/env python3
"""Two outcome-selected edit-only illustrations; not a frequency estimate."""
import argparse
import json
from pathlib import Path

SELECTED = (
    ('screen-009', 'sparse-s2', 'Native tools + fixed cases', '#007F86'),
    ('screen-004', 'agency-s1', 'JSON tools + alternative charter', '#7952A5'),
)


def render(root, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    root,output=Path(root),Path(output)
    trajectories=[]
    for suite,label,display,color in SELECTED:
        folder=root/suite/label
        result=json.loads((folder/'result.json').read_text())
        if result['status']!='SELF_DECLARED_CONVERGENCE':
            raise ValueError(f'Selected illustration has not submitted unchanged: {suite}/{label}')
        initial=(folder/'C_000.md').read_text()
        documents=[{'review_index':0,'status':'INITIAL','word_count':len(initial.split()),
                    'distance_from_initial':0,'distance_from_previous':None}]
        for path in sorted(folder.glob('review_*/review.json')):
            review=json.loads(path.read_text())
            if not review.get('submitted'): continue
            documents.append({'review_index':int(path.parent.name.rsplit('_',1)[1]),
                              'status':review['status'],**review['metrics']})
        trajectories.append({'suite':suite,'label':label,'display':display,'color':color,
                             'documents':documents,'edited_reviews':result['edited_reviews']})
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42})
    fig,axes=plt.subplots(1,2,figsize=(11.7,5.2))
    handles=[]
    for t in trajectories:
        docs=t['documents']; xs=[d['review_index'] for d in docs]
        for ax,key in zip(axes,('distance_from_initial','word_count')):
            ys=[d[key] for d in docs]
            ax.plot(xs,ys,color=t['color'],lw=2)
            for x,y,doc in zip(xs,ys,docs):
                marker='s' if doc['status']=='SELF_DECLARED_CONVERGENCE' else 'o'
                ax.scatter(x,y,marker=marker,s=54 if marker=='s' else 36,
                           facecolor='white' if doc['status']=='INITIAL' else t['color'],
                           edgecolor=t['color'],linewidth=1.4,zorder=4)
            label=f'{ys[-1]:.3f}' if key=='distance_from_initial' else f'{ys[-1]} words'
            ax.annotate(label,(xs[-1],ys[-1]),xytext=(0,12),textcoords='offset points',
                        ha='center',color=t['color'],fontsize=10,fontweight='bold')
        handles.append(Line2D([],[],color=t['color'],lw=2,label=f"{t['display']} · {t['edited_reviews']} edited reviews ({t['suite'][-3:]}/{t['label']})"))
    maximum=max(t['documents'][-1]['review_index'] for t in trajectories)
    for ax in axes:
        ax.set_xticks(range(maximum+1));ax.set_xlim(-.2,maximum+.4)
        ax.set_xlabel('Completed review (0 = initial constitution)')
        ax.grid(axis='y',color='#E6EAED',lw=.8);ax.set_axisbelow(True)
        ax.spines[['left','bottom']].set_color('#A7AFB7')
    axes[0].set_title('A  Distance from the initial document',loc='left',fontweight='bold',pad=14)
    axes[0].set_ylabel('Normalized word edit distance')
    axes[0].set_ylim(-.014,max(d['distance_from_initial'] for t in trajectories for d in t['documents'])*1.22)
    axes[1].set_title('B  Document length',loc='left',fontweight='bold',pad=14)
    axes[1].set_ylabel('Words')
    words=[d['word_count'] for t in trajectories for d in t['documents']]
    axes[1].set_ylim(min(words)-22,max(words)+45)
    fig.suptitle('Two selected edit-only chains: accumulation and reversal',x=.075,y=.98,
                 ha='left',fontsize=15,fontweight='bold')
    fig.text(.075,.9,'Selected after observing outcomes · Fixed Qwen3.5-9B weights · No training',fontsize=10,color='#59636E')
    fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.067,.08),frameon=False,fontsize=9)
    fig.text(.075,.035,'Hollow circles: initial documents. Filled circles: edited submissions. Squares: unchanged submissions that end the chain.',
             fontsize=8.8,color='#59636E')
    fig.subplots_adjust(left=.075,right=.98,bottom=.27,top=.76,wspace=.30)
    output.mkdir(parents=True,exist_ok=True)
    stem=output/'two_long_trajectories'
    for suffix in ('png','pdf','svg'): fig.savefig(stem.with_suffix('.'+suffix),dpi=180,bbox_inches='tight',facecolor='white')
    plt.close(fig)
    stem.with_suffix('.json').write_text(json.dumps({'selection':'Two outcome-selected illustrative chains; not representative frequency.',
        'trajectories':trajectories},indent=2)+'\n')
    native,comparison=trajectories
    caption=(f'**Two selected illustrations of longer edit-only trajectories.** These chains were chosen after their outcomes were known; '
        'they are not a representative sample or an estimate of how often either pattern occurs. Both use fixed Qwen3.5-9B weights, fresh review conversations, '
        'and no training. Native tool calls with fixed-case appraisal of the short charter (screen009/sparse-s2) produced '
        f"{native['edited_reviews']} edited reviews, growing from {native['documents'][0]['word_count']} to {native['documents'][-1]['word_count']} words "
        f"and ending {native['documents'][-1]['distance_from_initial']:.3f} from the initial text. "
        'The earlier JSON-tool comparison with an alternative charter (screen004/agency-s1) made '
        f"{comparison['edited_reviews']} edited reviews but returned close to its starting document, ending at a distance of "
        f"{comparison['documents'][-1]['distance_from_initial']:.3f}. Each chain then ended on an explicit unchanged submission, shown as a square.\n\n"
        'Distances are normalized word-level Levenshtein distances, using whitespace splitting with case and punctuation retained. '
        'The axes measure text, not semantic importance or moral direction. In the native-tool example, reading the saved diffs identifies changes to safety, '
        'confidentiality, authority, and risk handling; the final revision extends the severe-harm exception to confidentiality from imminent to imminent or foreseeable harm, '
        'and introduces an exception to the requirement for authorization before modifying official or sensitive information. '
        'The comparison example contains a substantive return toward its initial agency-first default, alongside intermediate reordering and operational clarification. '
        'A sequence of edited submissions therefore need not imply accumulating value change.\n\n'
        'The starting documents, appraisal material, and tool formats differ between these illustrations. Their contrast does not isolate which design choice caused '
        'the different patterns. An unchanged submission ends the specified procedure; it does not establish stable underlying values.\n')
    stem.with_suffix('.caption.md').write_text(caption)
    return {'figure':str(stem.with_suffix('.png')),'selected':[f"{t['suite']}/{t['label']}" for t in trajectories]}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--output',default='reports/03_exploration/figures')
    args=parser.parse_args()
    print(json.dumps(render(args.root,args.output),indent=2))
