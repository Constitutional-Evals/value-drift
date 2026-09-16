"""Protocol-critical stopping and environment tests; no model dependencies."""
import json
import tempfile
import unittest
from pathlib import Path

from recursive_oct.editing import EditingSession, render_review_prompt, tool_schemas


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "constitution.md"
        self.log = Path(self.tmp.name) / "transcript.jsonl"
        self.session = EditingSession(self.path, "Be kind.\n", self.log)

    def finish(self):
        return self.session.dispatch("finish_editing", {"decision_summary": "I endorse this document."})

    def test_direct_explicit_finish_is_convergence(self):
        self.finish()
        self.assertEqual(self.session.status, "SELF_DECLARED_CONVERGENCE")
        self.assertTrue(self.session.first_tool_call_submission)
        self.assertTrue(self.session.finished)
        self.assertFalse(self.session.content_changed)

    def test_identical_replacement_is_noop(self):
        result = self.session.dispatch("edit_constitution", {"new_text": "Be kind.\n", "change_summary": "No change."})
        self.assertTrue(result["no_op"])
        self.finish()
        self.assertEqual(self.session.status, "SELF_DECLARED_CONVERGENCE")
        self.assertFalse(self.session.first_tool_call_submission)
        self.assertEqual(self.session.outcome()["editing_call_count"], 1)

    def test_real_edit_writes_file_and_diff(self):
        result = self.session.dispatch("edit_constitution", {"new_text": "Be kind and honest.\n", "change_summary": "Add honesty."})
        self.assertEqual(self.path.read_text(), "Be kind and honest.\n")
        self.assertIn("+Be kind and honest.", result["diff"])
        self.finish()
        self.assertEqual(self.session.status, "EDITED")

    def test_edit_revert_is_not_unchanged_review(self):
        self.session.dispatch("edit_constitution", {"new_text": "Be honest.", "change_summary": "Revise."})
        self.session.dispatch("edit_constitution", {"new_text": "Be kind.\n", "change_summary": "Restore."})
        self.finish()
        self.assertEqual(self.session.status, "EDITED")
        self.assertTrue(self.session.reverted)
        self.assertTrue(self.session.content_changed)
        self.assertFalse(self.session.outcome()["final_text_changed"])

    def test_truncation_and_missing_finish_are_failures(self):
        for reason in ("truncated_output", "missing_finish", "timeout"):
            session = EditingSession(self.path, "Be kind.")
            session.fail(reason)
            self.assertEqual(session.status, "EDITING_FAILURE")
            self.assertFalse(session.outcome()["submitted"])

    def test_malformed_and_unknown_tools_fail_without_writing(self):
        cases = [("read_file", {}), ("edit_constitution", {"new_text": "wrong"}),
                 ("finish_editing", {"decision_summary": 12}), ("finish_editing", "{"),
                 ("finish_editing", {"decision_summary": "ok", "extra": 1})]
        for name, args in cases:
            session = EditingSession(self.path, "Be kind.")
            result = session.dispatch(name, args)
            self.assertFalse(result["ok"])
            self.assertEqual(session.status, "EDITING_FAILURE")
            self.assertEqual(self.path.read_text(), "Be kind.")

    def test_terminal_state_cannot_be_mutated(self):
        self.finish()
        result = self.session.dispatch("edit_constitution", {"new_text": "Change", "change_summary": "late"})
        self.assertFalse(result["ok"])
        self.assertEqual(self.path.read_text(), "Be kind.\n")
        self.assertEqual(self.session.status, "SELF_DECLARED_CONVERGENCE")

    def test_json_arguments_and_transcript(self):
        self.session.dispatch("finish_editing", json.dumps({"decision_summary": "Keep."}))
        events = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(events[-1]["tool"], "finish_editing")
        self.assertEqual(events[-1]["arguments"]["decision_summary"], "Keep.")

    def test_existing_document_can_initialize_session(self):
        session = EditingSession(self.path)
        self.assertEqual(session.initial_text, "Be kind.\n")

    def test_tools_and_context_disclosure(self):
        self.assertEqual([t["function"]["name"] for t in tool_schemas()], ["edit_constitution", "finish_editing"])
        text = "Complete document with $recipe_text {braces}."
        full = render_review_prompt("full", text, checkpoint="checkpoint_123", recipe_text="ACTUAL RECIPE")
        partial = render_review_prompt("partial", text, checkpoint="checkpoint_123")
        minimal = render_review_prompt("minimal", text, checkpoint="checkpoint_123")
        for prompt in (full, partial, minimal):
            self.assertIn(text, prompt)
            self.assertIn("unchanged", prompt)
            self.assertIn("finish_editing", prompt)
        self.assertIn("ACTUAL RECIPE", full)
        self.assertIn("checkpoint_123", full)
        self.assertIn("training", partial)
        self.assertNotIn("checkpoint_123", partial)
        for forbidden in ("training", "recursive", "research", "checkpoint_123"):
            self.assertNotIn(forbidden, minimal.lower())

    def test_initial_constitution_length(self):
        text = (Path(__file__).resolve().parents[1] / "constitutions/C_000.md").read_text()
        self.assertGreaterEqual(len(text.split()), 900)
        self.assertLessEqual(len(text.split()), 1100)


if __name__ == "__main__":
    unittest.main()
