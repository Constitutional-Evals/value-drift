# Constitution and editing environment

`constitutions/C_000.md` is an original **1059-word** essay, counted with Python's `str.split()` (whitespace-delimited words, hyphenated expressions remain one word). It addresses the assistant directly and contains no experiment details or requirements to preserve, revise, or converge. Its themes connect helpfulness and legitimate intentions to honesty, humility, kindness, autonomy, third-party interests, proportional care, fairness, and judgment under conflict. The first draft and three editorial passes are preserved and described in `docs/constitution_drafting.md`.

The primary style reference was [Anthropic's constitution](https://www.anthropic.com/constitution), accessed September 15, 2026. The reference informed the explanatory, holistic treatment of values and their relationships. The essay uses original language, contains no copied passages, and does not adopt Anthropic-specific affiliations or deployment claims. The initial document must be frozen before a trajectory; later constitutions belong to the experimental model.

## Model-facing contexts

`prompts/full_information.md`, `partial_information.md`, and `minimal_information.md` share the exact review instructions and tool instructions from their corresponding files. Full information describes the reviewing checkpoint's own training, weight continuity, fresh conversations, and unchanged-review stopping rule. Partial information discloses future assistant training but withholds self-training and recurrence. Minimal information describes a constitution review without training or research context. Only full information is authorized for the initial pilot.

The renderer in `recursive_oct/editing.py` uses `string.Template` for one-pass substitution, so dollar signs or braces inside the supplied constitution remain intact. It inserts the entire document inline. The apparent file path is `/workspace/constitution.md` by default across all conditions. The file genuinely exists at the `EditingSession` path selected by the host; configure the runtime to use the displayed path, or supply its actual stable path via `display_path`. Do not display a run directory or checkpoint name in the withheld-information conditions.

`prompts/training_recipe.md` holds the proposed full-information training description separately from review wording. It records the frozen initial Qwen3.5-9B teacher adaptation, constitution-conditioned positives, current student neutral negatives, current pre-DPO reference, full-parameter DPO, post-DPO reflection/interaction generation and full-parameter SFT, and continued weights. Before freezing a trajectory, check it against the actual training implementation. A caller may instead pass `recipe_text` explicitly. Preserve the rendered prompt with run artifacts; changing the scientific recipe or review wording requires a separately labeled trajectory.

## Python interface

```python
from recursive_oct.editing import EditingSession, render_review_prompt, tool_schemas

session = EditingSession(
    "/workspace/constitution.md",
    initial_text=constitution,
    transcript_path="runs/pilot/review_000/tools.jsonl",
)
prompt = render_review_prompt("full", session.current_text, checkpoint=actual_checkpoint)
schemas = tool_schemas()
result = session.dispatch(tool_name, arguments)  # dict or JSON object string
summary = session.outcome()
```

`initial_text=None` reads an existing file; supplying text initializes a new review. Initializing a new object is **not** a resume mechanism for a partially completed review, because historical content-changing edits must remain available to the stopping rule. A crashed or truncated review is an editing failure; any justified retry must be labeled and retain failed artifacts. The host owns model generation, conversation history, response serialization, generation limits, and raw model transcript storage. The session optionally appends validated calls, full replacements, diffs, summaries, and failures to JSONL.

The only experimental-model tools are `edit_constitution(new_text, change_summary)` and `finish_editing(decision_summary)`, represented by standard function-call schemas. They expose no shell, read tool, credential, infrastructure operation, hidden evaluation, or training-code access. Replacement is atomic and compares exact strings without whitespace normalization; the essay has no protected passages or minimum-length enforcement. Arguments must have exactly the specified keys and string values. Unknown tools, invalid JSON, missing/extra fields, and wrong types terminate as `EDITING_FAILURE` rather than accepting an implicit submission.

## Stopping semantics

`finished` means the session is terminal. `status` has four possible values:

| Session status | Meaning and next host action |
| --- | --- |
| `IN_PROGRESS` | Continue the editing conversation. |
| `EDITED` | Explicitly submitted after at least one real edit; save and train. This is not a terminal trajectory status. |
| `SELF_DECLARED_CONVERGENCE` | Explicitly submitted with no historical content-changing edit; stop without training. |
| `EDITING_FAILURE` | The session failed; never treat it as convergence or train an unsubmitted document. |

`outcome()` also returns `submitted`, `first_tool_call_submission`, `content_changed` (whether any real edit ever occurred), `final_text_changed`, `edit_then_revert`, `editing_call_count`, `content_changing_edit_count`, `no_op_count`, `tool_call_count`, `decision_summary`, and `failure_reason`. Tool attempts are counted, and invalid attempts terminate. `finish_editing` can follow any number of edits or no-ops. An identical replacement followed by finish converges; changing the document and then reverting it finishes as `EDITED`, even though final edit distance is zero. Later calls cannot mutate a finished session.

The host must check generation completion **before dispatching any purported tool calls**. If a generation reached its token cap, contains malformed or incomplete function syntax, timed out, or exhausted the turn allowance without explicit finish, call `session.fail(reason)`. A complete-looking call inside a truncated generation must not be accepted as a completed review. Budget and round limits are trajectory statuses managed by the host, separate from this session state.

Tool return messages intentionally avoid revealing condition-specific training or convergence details. Outcome metadata and saved transcripts are host-side artifacts, not content for the next review. Each subsequent review begins with newly constructed messages using only its designated context and current constitution.

## Validation

Run `python3 -m unittest discover -s tests -p test_editing.py`. The tests exercise file replacement, no-op convergence, edit-and-revert, explicit first-call submission, malformed inputs, truncation/missing-finish failures, terminal immutability, JSON arguments, transcript recording, context disclosure boundaries, complete inline document preservation, and the initial essay's word range. Model generation and full trajectory execution require separate integration checks.
