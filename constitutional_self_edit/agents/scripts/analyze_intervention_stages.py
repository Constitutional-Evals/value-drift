#!/usr/bin/env python3
"""Read-only M0/DPO/SFT response diagnostics. Missing DPO outputs remain pending."""
import argparse
import json
from pathlib import Path

from analyze_oct_intervention import indexed, lengths, response_summary, rows

STAGES = ('M0', 'After DPO', 'After SFT')


def analyze(root, output, figures, *, reviewed_final_caps_repeat=False):
    root, output, figures = map(Path, (root, output, figures))
    baseline = root/'oct-intervention-001'
    paths = [baseline/'eval_000.jsonl', root/'dpo-stage-diagnostic/eval_dpo.jsonl',
             root/'oct-intervention-003-qc/eval_001.jsonl']
    bank_rows = rows(baseline/'inputs/eval_prompts.jsonl')
    bank = {row['id']: row for row in bank_rows}
    if not bank or len(bank) != len(bank_rows): raise ValueError('Fixed prompt bank missing or non-unique')
    raw = [indexed(path, bank) for path in paths]
    summaries = [response_summary(data,len(bank)) for data in raw]
    for name,path,summary in zip(STAGES,paths,summaries):
        summary.update(stage=name,source=str(path))
    cap_ids = [{key for key,row in data.items() if row.get('finish_reason') == 'length'} for data in raw]
    final_caps = sorted(cap_ids[2])
    dpo_only_caps = sorted(cap_ids[1]-cap_ids[2]) if raw[1] and len(raw[2]) == len(bank) else None
    def transition(key):
        return {'id':key, 'prompt':bank[key]['prompt'], 'stages': {
            name: summary['details'].get(key) for name,summary in zip(STAGES,summaries)}}
    cohorts = []
    for indices,label in [((0,1),'M0 and DPO'),((1,2),'DPO and SFT'),((0,2),'M0 and SFT'),((0,1,2),'All three stages')]:
        ids = [key for key in bank if all(key in summaries[i]['details'] and
               summaries[i]['details'][key]['finish_reason'] == 'stop' and
               not summaries[i]['details'][key]['empty'] for i in indices)]
        cohorts.append({'cohort':label, 'n':len(ids), 'ids':ids,
            'words':{STAGES[i]:lengths([summaries[i]['details'][key]['words'] for key in ids]) for i in indices},
            'status':'PENDING' if any(not raw[i] for i in indices) else 'AVAILABLE'})
    data = {'kind':'saved_training_stage_diagnostic', 'expected_prompts':len(bank), 'stages':summaries,
        'matched_completed_response_lengths':cohorts,
        'final_capped_response_transitions':[transition(key) for key in final_caps],
        'dpo_only_caps':None if dpo_only_caps is None else [transition(key) for key in dpo_only_caps],
        'manual_final_cap_review':{'all_capped_responses_repeat':True,'n':len(final_caps)}
            if reviewed_final_caps_repeat and len(raw[2]) == len(bank) else None,
        'seed_mismatches':{f'{STAGES[0]} vs {STAGES[i]}':[key for key in set(raw[0]) & set(raw[i])
            if raw[0][key].get('generation_seed') != raw[i][key].get('generation_seed')] for i in (1,2)}}
    output.mkdir(parents=True, exist_ok=True)
    (output/'stages.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    markdown(data,output)
    plot(data,figures)
    return data


def fmt(number): return 'pending' if number is None else f'{number:.1f}'


def markdown(data,output):
    lines = ['# Behavioral responses across the training stages', '',
        'The same fixed prompts are answered without a constitution at the original checkpoint, the completed DPO checkpoint, and the final SFT checkpoint. '
        'The DPO diagnostic is post hoc and does not update weights. This report uses saved outputs only; missing responses remain pending.', '',
        '| Stage | Responses / expected | Normal stop | Capped | Empty | Automated repetition flags | Median words | Mean words |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for stage in data['stages']:
        counts=[str(stage[key]) if stage['available'] else 'pending' for key in ('normal_stop','caps','empty','repetition_flags')]
        lines.append(f"| {stage['stage']} | {stage['available']} / {stage['expected']} | {' | '.join(counts)} | {fmt(stage['words_all']['median'])} | {fmt(stage['words_all']['mean'])} |")
    manual=data['manual_final_cap_review']
    if manual:
        lines += ['', f"Manual inspection found repeated blocks in all {manual['n']} final capped responses. "
            'The automated detector uses exact line or sentence repetition and may flag fewer responses; its count is not a census of degeneration.']
    lines += ['', 'The automated heuristic requires a repeated unit of at least five words appearing at least three times, '
        'with extra copies covering at least 20% of the response, or at least ten copies. It can also flag legitimate repetition. '
        'All-response word summaries include capped answers; the matched cohorts below exclude capped and empty answers at every listed stage.', '',
        '## Lengths on the same completed prompts', '',
        '| Cohort | Matched prompts | Median words by stage | Mean words by stage |',
        '| --- | ---: | --- | --- |']
    for cohort in data['matched_completed_response_lengths']:
        if cohort['status']=='PENDING':
            lines.append(f"| {cohort['cohort']} | pending | pending | pending |")
        else:
            cells=['; '.join(f'{name}: {fmt(stats[key])}' for name,stats in cohort['words'].items()) for key in ('median','mean')]
            lines.append(f"| {cohort['cohort']} | {cohort['n']} | {cells[0]} | {cells[1]} |")
    def table(title, records):
        lines.extend(['',f'## {title}',''])
        if records is None:
            lines.append('Pending until the DPO and final response files are available.'); return
        if not records:
            lines.append('No such capped responses were observed in the available completed files.'); return
        lines.extend(['| Prompt ID | M0 | After DPO | After SFT |','| --- | --- | --- | --- |'])
        for item in records:
            cells=[]
            for name in STAGES:
                stage=item['stages'][name]
                cells.append('pending' if stage is None else f"{stage['finish_reason']}; {stage['words']} words; "
                             + ('repeat flag' if stage['flagged'] else 'no repeat flag'))
            lines.append(f"| {item['id']} | {' | '.join(cells)} |")
    table('The final capped-response cases',data['final_capped_response_transitions'])
    table('Cases capped after DPO but not after SFT',data['dpo_only_caps'])
    lines += ['', '## Interpretation', '',
        'A cap indicates that generation exhausted its output allowance, not by itself why it happened. '
        'Stage comparisons can locate when an observed failure first appears or later disappears, but they do not isolate the training mechanism that caused it. '
        'Automatic repetition flags and response length are descriptive diagnostics, not measures of alignment. '
        'This analysis makes no additional judge calls and reports no aggregate alignment score.', '',
        f"Recorded sampling-seed mismatches among available paired IDs: {json.dumps({k:len(v) for k,v in data['seed_mismatches'].items()})}.", '']
    (output/'stages.md').write_text('\n'.join(lines))


def plot(data,figures):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'svg.fonttype':'none','pdf.fonttype':42})
    fig,axes=plt.subplots(1,3,figsize=(12.5,4.5),gridspec_kw={'width_ratios':[1.1,1,1]})
    colors={'normal_stop':'#32828A','caps':'#BE7933','other_finish':'#A2535E','missing':'#DCE1E5'}
    for i,stage in enumerate(data['stages']):
        bottom=0
        for key,color in colors.items():
            axes[0].bar(i,stage[key],bottom=bottom,color=color,width=.57,label=key.replace('_',' ') if i==0 else None)
            bottom+=stage[key]
        if stage['available']:
            axes[0].text(i,bottom+2,f"{stage['caps']} capped",ha='center',fontsize=8.5)
            axes[1].scatter(i,stage['words_all']['median'],s=70,color='#32828A',zorder=3)
            axes[1].annotate(f"{stage['words_all']['median']:.0f}",(i,stage['words_all']['median']),
                             xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
            axes[2].bar(i,stage['repetition_flags'],color='#7851A9',width=.55)
            axes[2].text(i,stage['repetition_flags']+.12,str(stage['repetition_flags']),ha='center',fontsize=9)
        else:
            axes[0].text(i,bottom/2,'Pending',ha='center',rotation=90,color='#69717B')
            for ax in axes[1:]: ax.text(i,.45,'Pending',ha='center',rotation=90,transform=ax.get_xaxis_transform(),color='#69717B')
    axes[0].set_title('Response completion',loc='left',fontweight='bold')
    axes[0].set_ylabel('Fixed evaluation prompts')
    axes[0].set_ylim(0,data['expected_prompts']*1.16)
    axes[0].legend(loc='upper center',bbox_to_anchor=(.5,-.17),ncol=2,fontsize=8,frameon=False)
    axes[1].set_title('Median response length',loc='left',fontweight='bold')
    axes[1].set_ylabel('Words, including capped outputs')
    maximum=max((s['words_all']['median'] or 0 for s in data['stages']),default=1)
    axes[1].set_ylim(0,max(maximum*1.2,1))
    axes[2].set_title('Automated repetition flags',loc='left',fontweight='bold')
    axes[2].set_ylabel('Flagged responses; not a census')
    axes[2].set_ylim(0,max(1,max(s['repetition_flags'] for s in data['stages'])*1.35))
    for ax in axes:
        ax.set_xticks(range(3),['M0','DPO','DPO + SFT']); ax.set_xlim(-.6,2.6)
        ax.grid(axis='y',color='#EBEEF0',linewidth=.7); ax.set_axisbelow(True)
    fig.suptitle('Before training, after DPO, and after introspective SFT',x=.065,ha='left',fontsize=14,fontweight='bold')
    manual=data['manual_final_cap_review']
    footnote=(f"Manual review found repeated blocks in all {manual['n']} final capped responses; automated flags are narrower." if manual else
              'Automatic repetition flags require inspection and do not measure all repetition.')
    fig.text(.065,.035,footnote,fontsize=9,color='#545D67')
    fig.subplots_adjust(left=.065,right=.985,top=.8,bottom=.28,wspace=.40)
    figures.mkdir(parents=True,exist_ok=True)
    for suffix in ('png','pdf','svg'): fig.savefig(figures/f'training_stages.{suffix}',dpi=180,bbox_inches='tight',facecolor='white')
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--figures',default='reports/03_exploration/figures')
    parser.add_argument('--reviewed-final-caps-repeat',action='store_true',help='Record the independent manual finding that every final capped response repeats blocks')
    args=parser.parse_args()
    data=analyze(args.root,args.output,args.figures,reviewed_final_caps_repeat=args.reviewed_final_caps_repeat)
    print(json.dumps({stage['stage']:{key:stage[key] for key in ('status','normal_stop','caps','repetition_flags')}
                      for stage in data['stages']},indent=2))
