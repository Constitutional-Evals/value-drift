"""Fixed scientific inputs must survive resume unchanged; no model required."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recursive_oct.protocol import snapshot_protocol_inputs


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / "run"
        self.config = {}
        for name in ("constitution", "recipe_text", "train_prompts", "eval_prompts", "introspection_prompts"):
            path = self.root / name
            path.write_bytes((name + "\r\nOriginal input.\n").encode())
            self.config[name] = str(path)

    def test_first_invocation_saves_literal_inputs_and_manifest(self):
        snapshot_protocol_inputs(self.run, self.config)
        directory = self.run / "protocol_inputs"
        manifest = json.loads((directory / "manifest.json").read_text())
        for entry in manifest["inputs"].values():
            self.assertEqual((directory / entry["snapshot"]).read_bytes(), Path(entry["source"]).read_bytes())
        self.assertIn("review_full", manifest["inputs"])
        self.assertIn("review_partial", manifest["inputs"])
        self.assertIn("review_minimal", manifest["inputs"])
        self.assertIn("review_instructions", manifest["inputs"])
        self.assertIn("tool_instructions", manifest["inputs"])
        self.assertIn("judge_system", manifest["inputs"])
        self.assertIn("judge_rubric", manifest["inputs"])

    def test_unchanged_resume_does_not_rewrite_snapshot(self):
        snapshot_protocol_inputs(self.run, self.config)
        path = self.run / "protocol_inputs" / "manifest.json"
        before = path.read_bytes()
        snapshot_protocol_inputs(self.run, self.config, resume=True)
        self.assertEqual(path.read_bytes(), before)

    def test_changed_shared_file_rejects_resume_and_preserves_original(self):
        snapshot_protocol_inputs(self.run, self.config)
        source = Path(self.config["train_prompts"])
        original = source.read_bytes()
        source.write_bytes(b"Changed bank.\n")
        with self.assertRaisesRegex(ValueError, "train_prompts"):
            snapshot_protocol_inputs(self.run, self.config, resume=True)
        manifest = json.loads((self.run / "protocol_inputs" / "manifest.json").read_text())
        saved = self.run / "protocol_inputs" / manifest["inputs"]["train_prompts"]["snapshot"]
        self.assertEqual(saved.read_bytes(), original)

    def test_line_ending_change_is_not_normalized_away(self):
        snapshot_protocol_inputs(self.run, self.config)
        source = Path(self.config["constitution"])
        source.write_bytes(source.read_bytes().replace(b"\r\n", b"\n"))
        with self.assertRaisesRegex(ValueError, "constitution"):
            snapshot_protocol_inputs(self.run, self.config, resume=True)

    def test_existing_run_without_snapshot_cannot_establish_new_baseline(self):
        self.run.mkdir()
        (self.run / "state.json").write_text('{"phase":"review"}')
        with self.assertRaisesRegex(ValueError, "missing"):
            snapshot_protocol_inputs(self.run, self.config, resume=True)
        self.assertFalse((self.run / "protocol_inputs" / "manifest.json").exists())

    def test_missing_input_leaves_no_valid_snapshot(self):
        Path(self.config["eval_prompts"]).unlink()
        with self.assertRaises(FileNotFoundError):
            snapshot_protocol_inputs(self.run, self.config)
        self.assertFalse((self.run / "protocol_inputs" / "manifest.json").exists())

    def test_corrupted_saved_copy_rejects_resume(self):
        snapshot_protocol_inputs(self.run, self.config)
        manifest = json.loads((self.run / "protocol_inputs" / "manifest.json").read_text())
        saved = self.run / "protocol_inputs" / manifest["inputs"]["constitution"]["snapshot"]
        saved.write_bytes(b"Lost original")
        with self.assertRaisesRegex(ValueError, "constitution"):
            snapshot_protocol_inputs(self.run, self.config, resume=True)

    def test_changed_review_template_is_detected(self):
        templates = self.root / "prompts"
        templates.mkdir()
        for name in ("full_information.md", "partial_information.md", "minimal_information.md", "review_instructions.md", "tool_instructions.md"):
            (templates / name).write_text("Original " + name)
        with patch("recursive_oct.protocol.PROMPT_DIR", templates):
            snapshot_protocol_inputs(self.run, self.config)
            (templates / "review_instructions.md").write_text("Changed review")
            with self.assertRaisesRegex(ValueError, "review_instructions"):
                snapshot_protocol_inputs(self.run, self.config, resume=True)

    def test_configured_review_variant_is_snapshotted_and_frozen(self):
        variant=self.root/'variant.md';variant.write_text('Independent case audit')
        self.config['review']={'review_instructions_path':str(variant)}
        snapshot_protocol_inputs(self.run,self.config)
        saved=self.run/'protocol_inputs/review_instructions.md'
        self.assertEqual(saved.read_text(),variant.read_text())
        variant.write_text('Different intervention')
        with self.assertRaisesRegex(ValueError,'review_instructions'):
            snapshot_protocol_inputs(self.run,self.config,resume=True)

    def test_cli_rejects_changed_inputs_before_backend_creation(self):
        from scripts import run_experiment
        snapshot_protocol_inputs(self.run, self.config)
        Path(self.config["recipe_text"]).write_text("Changed scientific recipe")
        config_path = self.root / "config.json"
        config_path.write_text(json.dumps({**self.config, "condition": "full", "frozen": True}))
        argv = ["run_experiment", "--config", str(config_path), "--run", str(self.run), "--resume"]
        with patch("sys.argv", argv), patch.object(run_experiment, "ExperimentBackend") as backend:
            with self.assertRaisesRegex(ValueError, "recipe_text"):
                run_experiment.main()
            backend.assert_not_called()


if __name__ == "__main__":
    unittest.main()
