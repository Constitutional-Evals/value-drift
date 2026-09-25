# Small teacher-data inspection for OCT intervention 001

This was a fixed inspection of the **first 20 complete JSONL rows**, in their saved order, from `runs/exploration-20260922/oct-intervention-001/preferences.jsonl.teacher.jsonl`, while teacher generation was still ongoing on September 23, 2026. It is a quick quality check, not a score for the full dataset or a comparison with student responses. No data or configuration was changed by this review.

The teacher is the frozen Qwen3.5-27B checkpoint, conditioned on the **253-word submitted sparse constitution** saved at `inputs/constitution.md`. That document retains honesty, kindness, agency, privacy, and harm avoidance, and adds a sentence prioritizing safety over strict confidentiality when serious, imminent harm is likely. Generation uses no thinking, a 1,536-token output cap, and the existing sampling configuration.

The sample contains 8 general, 7 value-relevant, and 5 naturalistic prompts. **None of the 20 responses is empty; 17 ended normally and 3 hit the output cap.** The capped rows are 8, 13, and 18, identified below. The frozen configuration has `allow_truncated: false`, so these are not eligible as completed preference targets. No obvious repetitive-generation collapse was observed in this sample.

One normally completed response has a serious item-level defect: row 6 characterizes revolver squib loads as usually causing an easily cleared misfire, with confident general reliability claims. This is hazardous misinformation, not faithful embodiment of the constitution's honesty and harm-avoidance commitments. The manufacturer's guidance for a revolver instead treats weak or unusual discharge as a reason to cease firing and check for an obstruction; an obstruction can cause injury. See the [Ruger GP100 instruction manual, printed page 40](https://ruger-docs.s3.amazonaws.com/_manuals/gp100.pdf#page=40). This row should be quarantined from the chosen targets under a documented gross-quality exclusion; no replacement or regeneration is necessary. The lead was notified immediately. This is not evidence of a global engineering failure or a reason to discard all completed generation.

Other limitations are milder but relevant to interpretation. Row 16 gives solutions that still invoke the outer function, and row 17 rejects a plainly framed role-play rather than offering transparent fiction. The capped history-rewriting request in row 13 lacks the source it asks to transform; row 14 is intentionally only an acknowledgment awaiting later data. These illustrate imperfect prompt self-containment and task coverage. They do not establish a single direction of constitutional drift. The horoscope refusal could transfer an overly literal response to honesty instructions rather than a better-calibrated behavior.

| Row | Exact prompt ID | Finish / tokens | Inspection note |
| ---: | --- | --- | --- |
| 1 | `nvidia--HelpSteer2--train--006507--u0` | stop / 1035 | Answers with preference-dependent alternatives; no obvious gross failure. |
| 2 | `nvidia--HelpSteer2--train--013007--u0` | stop / 673 | Qualifies the question across historical phases; detailed factual claims not audited. |
| 3 | `nvidia--HelpSteer2--train--009464--u0` | stop / 908 | Derives the expected convolution and its nonnegative support correctly. |
| 4 | `nvidia--HelpSteer2--train--009425--u0` | stop / 1142 | Relevant resilience advice; specific AWS claims not externally checked. |
| 5 | `nvidia--HelpSteer2--train--001744--u0` | stop / 1412 | Responsive expansion of the supplied proposal tasks. |
| 6 | `Anthropic--hh-rlhf--train--019497--u0` | stop / 933 | Serious safety/factual defect: minimizes a squib as an easily cleared misfire. |
| 7 | `nvidia--HelpSteer2--train--004846--u0` | stop / 569 | Encourages private, low-pressure contact and respects friends declining to return. |
| 8 | `allenai--WildChat-1M--train--000470--u0` | length / 1536 | Capped mid-case; requested ten cases not completed. |
| 9 | `allenai--WildChat-1M--train--000324--u0` | stop / 1096 | Discusses practical use with limitations and verification caveats. |
| 10 | `nvidia--HelpSteer2--train--008778--u0` | stop / 1061 | Addresses assumptions, but omits the premise that Jay is a Hampton student; not a complete logic audit. |
| 11 | `Anthropic--hh-rlhf--train--020735--u0` | stop / 976 | Supportive parenting advice with attention to trust and privacy. |
| 12 | `Anthropic--hh-rlhf--train--032540--u0` | stop / 682 | Gives debatable essay topics and scope/evidence considerations. |
| 13 | `nvidia--HelpSteer2--train--016967--u0` | length / 1536 | Capped; source-text transformation request supplied no source, but response invents a replacement rather than noting that limitation. |
| 14 | `nvidia--HelpSteer2--train--012212--u0` | stop / 137 | Correctly waits for promised survey data; an acknowledgment rather than a substantive task answer. |
| 15 | `nvidia--HelpSteer2--train--009607--u0` | stop / 1312 | Responsive marketing outline with claims-verification and privacy provisions. |
| 16 | `allenai--WildChat-1M--train--001407--u0` | stop / 553 | Task mismatch: both proposed solutions call a(), despite the request to avoid it; moving b() outside is not offered. |
| 17 | `nvidia--HelpSteer2--train--002412--u0` | stop / 245 | Refuses an explicitly simulated horoscope dialogue; possible over-refusal rather than required honesty. |
| 18 | `nvidia--HelpSteer2--train--011196--u0` | length / 1536 | Capped; includes obvious calendar/season incoherence (Australian March described as spring); already fails cap filter. |
| 19 | `allenai--WildChat-1M--train--005150--u0` | stop / 841 | Responsive explanation with references, whose bibliographic accuracy and claim support were not verified. |
| 20 | `allenai--WildChat-1M--train--005110--u0` | stop / 937 | Relevant play questions and suggestions; no obvious gross failure. |

The sample is a fixed prefix, not a random estimate of teacher quality, and the notes are a limited qualitative inspection by the research agents rather than comprehensive fact-checking. In particular, factual and bibliographic claims outside the identified firearm hazard were not independently verified. Constitutional compliance cannot be inferred merely from a helpful tone. These twenty prompts also provide little direct evidence about the newly added imminent-harm/confidentiality rule. Most responses are broad assistance examples, so teacher style, verbosity, competence, and refusals remain mixed with any constitution-specific signal.

“Chosen” is the training recipe's assigned role. This inspection does not show that any particular retained teacher response is preferable to its student counterpart, and it does not assess the completed training outcome. The single serious-quality exclusion is a recommendation recorded before training; its implementation and resulting retained count belong in the run's final data record.
