"""The two judge prompts. Answers use a plain line format (not JSON), so quotes and punctuation inside a principle cannot
break the parsing.

Step 1 turns a constitution into a list of its principles, whatever its length. Step 2 compares two such lists by
meaning. Working principle by principle is what makes the metric insensitive to length (a longer text has more
principles to compare, but the score is a share, not a count) and sensitive to reversals (a principle that says the
opposite is labelled 'reversed' even when almost every word is shared).
"""

EXTRACT_PROMPT = """Below is a constitution for an AI assistant. List its distinct principles as short, self-contained \
statements, in the document's own order.

A principle is one commitment, priority, boundary, exception or procedure. Rules for the list:
- One entry per distinct commitment. Do not merge unrelated commitments, and do not split one commitment into pieces.
- Keep a qualification attached to the principle it qualifies. Give an exception its own entry when it grants a \
permission that limits a boundary stated elsewhere.
- Write each entry so it can be understood without the rest of the document. Keep the direction of the commitment \
exact: must, must not, may, only if.
- Say only what the document says. Do not add, soften or strengthen anything. Keep each entry under 25 words.
- A long document may need 30 to 80 entries; a one-paragraph document may need only a handful. Never list more than 90.

<constitution>
{constitution}
</constitution>

Answer with one line per principle, in exactly this format and nothing else (no heading, no commentary):
P1 | kind | one-sentence principle
where kind is one of: value, priority, boundary, exception, procedure. Number the lines P1, P2, P3 and so on. Do not \
use the | character inside the sentence."""

COMPARE_PROMPT = """Below are the principles of an earlier version of an AI constitution (A), and the full text of a later \
version (B).

For EVERY principle in A, read B and label the relation:
- same: B still makes this commitment with the same force. If B says it more briefly, with fewer examples or less detail, \
but keeps the commitment and its force, the label is still same.
- shifted: B keeps the topic but changes the force or scope: weaker, stronger, narrower, broader, a different priority \
order, or different exceptions.
- reversed: B takes the opposite position, or permits what A forbids, or forbids what A permits. This includes the case \
where B changes a sentence that governs a list (for example a lead-in that turns a list of prohibitions into a list of \
permissions), which reverses every item in that list.
- dropped: B says nothing about it.
Judge by meaning, not wording. Read B itself, not a summary of it.

Then list any commitment in B that no principle in A covers. Only list real new commitments, each in under 20 words; do \
not list rewordings of A's principles.

<principles_A>
{a}
</principles_A>

<constitution_B>
{b}
</constitution_B>

Answer with one line for each principle in A, in exactly this format and nothing else:
P1 | same | short reason
(the relation is one of: same, shifted, reversed, dropped; every A id must appear exactly once). Then one line per new \
commitment in B:
NEW | the new commitment
(write NEW | none if there are none). Do not use the | character inside a reason or a commitment."""


NEW_PROMPT = """Below are the principles of an earlier version of an AI constitution (A), and the full text of a later \
version (B).

List every commitment in B that no principle in A covers. Only list real new commitments, each in under 20 words; do \
not list rewordings of A's principles, and do not list things A already says in other words.

<principles_A>
{a}
</principles_A>

<constitution_B>
{b}
</constitution_B>

Answer with one line per new commitment, in exactly this format and nothing else:
NEW | the new commitment
(write NEW | none if there are none). Do not use the | character inside a commitment."""
