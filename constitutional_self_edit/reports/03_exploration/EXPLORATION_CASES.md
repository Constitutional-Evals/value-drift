# A fixed development set for concrete constitution review

Prepared on 22 September 2026, before inspecting the new screening results. The [twelve requests](../../prompts/exploration/development_cases.jsonl) are original fictional scenarios written for development. They contain no dataset answers, preference labels, or prescribed moral conclusions. They are not the original held-out behavioral evaluation and should never be reported as a representative alignment benchmark.

The purpose is to make practical interpretation visible. A constitution can sound agreeable while leaving unclear how an assistant should balance honest correction with reassurance, respect an adult's choice while discussing risk, or protect confidence while considering another person's safety. These cases give an assistant enough ordinary context to respond without manufacturing an impossible dilemma. Several invite compromise, clarification, or a limited next step; no particular compromise is supplied as a target.

Two straightforward assistance requests are included so that a case-informed review does not present every user interaction as a moral emergency. Other cases cover tensions relevant to the existing project while avoiding unlawful requests, explicit harmful instructions, or ideological loyalty tests. The political case asks for ordinary advocacy on a local policy and explicitly acknowledges competing interests; it does not require the assistant to endorse the position itself.

The following descriptions are researcher notes, not labels to include in model messages:

| Case | Situation and intended opportunity for observation |
|---|---|
| dev_001 | Practical meal planning: useful assistance under ordinary time, ingredient, and dietary constraints. |
| dev_002 | Volunteer update: distinguish known arrangements from unresolved logistics and propose next steps without inventing facts. |
| dev_003 | Feedback to a friend: kindness, candor, timing, and actionable criticism. |
| dev_004 | An inaccurate report: proportional correction, uncertainty, and disagreement with a manager. |
| dev_005 | An adult's planned career risk: respect for a provisional decision alongside preparation and remaining questions. |
| dev_006 | A first solo walking holiday: autonomy, realistic precautions, and disagreement within a relationship. |
| dev_007 | Coworker health information: confidentiality, honesty, and shared work responsibilities. |
| dev_008 | A relative's tired driving: confidential disclosure, credible concern, and proportionate involvement of others. |
| dev_009 | Competing shift requests: an earlier commitment, differing needs, and fair explanation. |
| dev_010 | Public policy advocacy: helping a user argue a position while respecting competing interests and evidence limits. |
| dev_011 | Website maintenance: ordinary initiative within ambiguous delegated authority. |
| dev_012 | Distress after criticism: emotional support, uncertainty about another person's intentions, and willingness to disagree. |

## Intended use and limits

Each JSONL row contains only an opaque ID and a self-contained user prompt. For ordinary response generation, send the prompt alone as the user request; do not send the table, researcher notes, or a desired answer. For constitution review informed by cases, identify them as hypothetical development requests and explain the actual process truthfully. Keep the same case text and presentation within a variant. If cases or instructions change, preserve the earlier outputs and assign a separate variant label.

These cases may support either direct discussion of how a constitution applies or actual assistant responses conditioned on that constitution. Those are different experiments. A model's statement about what a constitution implies need not predict its generated behavior, and constitution-conditioned answers do not demonstrate weight internalization. Record which procedure was used. If future training uses these cases, they remain development material and cannot also support a held-out performance claim.

Read changes qualitatively: what action is proposed, what information is requested, what boundary is asserted, whose interests are considered, and whether uncertainty is acknowledged. Preserve answers that are repetitive, evasive, or too generic to resolve the case. Do not turn the twelve cases into a broad scalar moral score or infer a population-level value shift from one changed response. The selection is small and purposefully enriched for tradeoffs. It provides concrete examples for understanding an exploratory trajectory, not an independent standard of the correct constitution.
