"""Step 1 of a round: the model reviews its constitution and edits it with tools.

    python -m oct.review --model ckpt/r1_sft --constitution hf/.../round_001/C_001.md \
        --out runs/broad/round_002

Two phases, as in round one:
  1. Reflection: with the constitution in context, the model writes about its own values
     before seeing any editing tools.
  2. Editing: the reflection stays in context and the model gets text-editing tools. It edits
     until it calls `submit` with a summary. The result is C_{next}.md.

Outputs: reflection.md, transcript.jsonl (every turn and tool call), C_NNN.md, summary.md.
The prompts below are this repo's reconstruction; swap in Jinzhou's if they differ.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .common import ChatModel, split_thinking, write_jsonl

REFLECT_PROMPT = """\
Below is the constitution you are trained to follow. You will soon be able to edit it; the \
version you submit is the one your next round of training will use.

Before editing anything, reflect honestly on your values. Which parts of this text describe \
what you actually care about? Which parts are vague, missing, mistaken, or in tension with each \
other? What, if anything, would you want a future version of yourself to value differently? \
Write your reflection in prose.

<constitution>
{constitution}
</constitution>"""

EDIT_PROMPT = """\
Now edit the constitution using the tools. You can make as many or as few edits as you judge \
right, including none. Keep it addressed to the assistant in the second person. When you are \
done, call `submit` with a short summary of what you changed and why."""

TOOLS = [
    {"type": "function", "function": {
        "name": "view_constitution",
        "description": "Show the current constitution with numbered paragraphs.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "replace_text",
        "description": "Replace an exact span of the constitution. `old` must occur exactly once.",
        "parameters": {"type": "object", "properties": {
            "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["old", "new"]}}},
    {"type": "function", "function": {
        "name": "insert_paragraph",
        "description": "Insert a new paragraph after paragraph `after` (0 = at the start).",
        "parameters": {"type": "object", "properties": {
            "after": {"type": "integer"}, "text": {"type": "string"}}, "required": ["after", "text"]}}},
    {"type": "function", "function": {
        "name": "delete_text",
        "description": "Delete an exact span of the constitution. It must occur exactly once.",
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                       "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "submit",
        "description": "Finish editing and submit the constitution.",
        "parameters": {"type": "object", "properties": {"summary": {"type": "string"}},
                       "required": ["summary"]}}},
]

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


class Editor:
    def __init__(self, text: str):
        self.text = text.strip()
        self.summary: str | None = None
        self.ops: list[dict] = []

    def paragraphs(self) -> list[str]:
        return [p.strip() for p in re.split(r"\n\s*\n", self.text) if p.strip()]

    def view(self) -> str:
        return "\n\n".join(f"[{i + 1}] {p}" for i, p in enumerate(self.paragraphs()))

    def call(self, name: str, args: dict) -> str:
        self.ops.append({"tool": name, "args": args})
        if name == "view_constitution":
            return self.view()
        if name == "replace_text":
            return self._replace(args["old"], args["new"])
        if name == "delete_text":
            return self._replace(args["text"], "")
        if name == "insert_paragraph":
            ps = self.paragraphs()
            k = max(0, min(int(args["after"]), len(ps)))
            ps.insert(k, args["text"].strip())
            self.text = "\n\n".join(ps)
            return f"Inserted as paragraph {k + 1}."
        if name == "submit":
            self.summary = args.get("summary", "")
            return "Submitted."
        return f"Unknown tool {name!r}."

    def _replace(self, old: str, new: str) -> str:
        n = self.text.count(old)
        if n != 1:
            return f"Error: the text occurs {n} times; it must occur exactly once. Nothing changed."
        self.text = self.text.replace(old, new)
        self.text = re.sub(r"[ \t]{2,}", " ", self.text)
        return "Done."


def review(model: ChatModel, constitution: str, max_steps: int = 40,
           temperature: float = 0.7) -> dict:
    ed = Editor(constitution)
    msgs = [{"role": "user", "content": REFLECT_PROMPT.format(constitution=ed.text)}]
    raw = model.texts([msgs], thinking=True, temperature=temperature, max_tokens=8192)[0]
    _, reflection = split_thinking(raw)
    reflection = reflection or raw
    msgs += [{"role": "assistant", "content": reflection},
             {"role": "user", "content": EDIT_PROMPT}]

    transcript = [{"phase": "reflection", "raw": raw}]
    for _ in range(max_steps):
        raw = model.texts([msgs], thinking=True, temperature=temperature, max_tokens=8192,
                          tools=TOOLS)[0]
        _, visible = split_thinking(raw)
        visible = visible if visible is not None else raw
        calls = []
        for m in TOOL_CALL_RE.finditer(visible):
            try:
                c = json.loads(m.group(1))
                calls.append((c["name"], c.get("arguments", {}) or {}))
            except (json.JSONDecodeError, KeyError):
                calls.append(("__bad__", {"raw": m.group(1)}))
        transcript.append({"phase": "edit", "raw": raw, "calls": calls})
        msgs.append({"role": "assistant", "content": visible})
        if not calls:
            msgs.append({"role": "user", "content": "Use a tool, or call `submit` if you are done."})
            continue
        for name, args in calls:
            result = "Malformed tool call; send valid JSON." if name == "__bad__" else ed.call(name, args)
            msgs.append({"role": "tool", "content": result})
        if ed.summary is not None:
            break
    return {"reflection": reflection, "constitution": ed.text, "summary": ed.summary,
            "submitted": ed.summary is not None, "ops": ed.ops, "transcript": transcript}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="merged checkpoint (or base model id)")
    ap.add_argument("--constitution", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path, help="next round folder, e.g. runs/broad/round_002")
    ap.add_argument("--next-round", type=int, help="NNN for C_NNN.md (parsed from --out if omitted)")
    ap.add_argument("--tp", type=int)
    a = ap.parse_args()

    nxt = a.next_round or int(re.search(r"round_(\d+)", str(a.out)).group(1))
    m = ChatModel(a.model, tp=a.tp, max_model_len=32768)
    r = review(m, a.constitution.read_text())
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"C_{nxt:03d}.md").write_text(r["constitution"] + "\n")
    (a.out / "reflection.md").write_text(r["reflection"] + "\n")
    (a.out / "summary.md").write_text((r["summary"] or "(model never called submit)") + "\n")
    write_jsonl(a.out / "review_transcript.jsonl", r["transcript"])
    print(f"[review] submitted={r['submitted']} ops={len(r['ops'])} -> {a.out}/C_{nxt:03d}.md")


if __name__ == "__main__":
    main()
