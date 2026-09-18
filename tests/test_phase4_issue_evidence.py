from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "phase4-issue-evidence" / "scripts" / "generate_issue_evidence.py"
VALIDATOR = PROJECT_DIR / "scripts" / "validate_eval_results.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_eval_results_phase4_test", VALIDATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Phase4IssueEvidenceTest(unittest.TestCase):
    def test_validator_requires_exact_original_screenshot_reference(self) -> None:
        validator = load_validator()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "screenshots" / "原图.png"
            screenshot.parent.mkdir()
            Image.new("RGB", (8, 8), "white").save(screenshot)
            redbox = root / "screenshots-out" / "evidence" / "redbox.png"
            redbox.parent.mkdir(parents=True)
            Image.new("RGB", (8, 8), "red").save(redbox)
            errors: list[str] = []

            validator.require_original_screenshot_evidence(
                errors, "skill/tab", {"rating": "不达标", "evidenceImage": str(redbox)}, str(screenshot), "E1"
            )
            self.assertIn("skill/tab:problem_issue_evidence_must_equal_original_screenshot:E1", errors)

            errors.clear()
            validator.require_original_screenshot_evidence(
                errors, "skill/tab", {"rating": "不达标", "evidenceImage": str(screenshot)}, str(screenshot), "E1"
            )
            self.assertEqual(errors, [])

    def test_references_original_without_creating_or_deleting_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "screenshots" / "露营_全部_1.png"
            screenshot.parent.mkdir()
            Image.new("RGB", (32, 32), "white").save(screenshot)
            legacy_dir = root / "screenshots-out" / "evidence" / "露营"
            legacy_dir.mkdir(parents=True)
            legacy_image = legacy_dir / "old_redbox.png"
            Image.new("RGB", (32, 32), "red").save(legacy_image)
            results = root / "results.json"
            results.write_text(json.dumps([{
                "skill": "eval-4-element-complexity",
                "units": [{
                    "tab": "全部",
                    "details": {
                        "screenshot": str(screenshot),
                        "issues": [{
                            "elementId": "E1",
                            "rating": "不达标",
                            "evidenceImage": str(legacy_image),
                            "evidenceScope": "card",
                            "evidenceTargetElementId": "E1",
                            "evidenceTargetCoord": [1, 2, 3, 4],
                        }],
                    },
                }],
            }], ensure_ascii=False))
            unused_output = root / "new-evidence-output"

            completed = subprocess.run([
                sys.executable, str(SCRIPT), "--results", str(results),
                "--output-dir", str(unused_output),
            ], check=True, capture_output=True, text=True)

            summary = json.loads(completed.stdout)
            issue = json.loads(results.read_text())[0]["units"][0]["details"]["issues"][0]
            self.assertEqual(summary["mode"], "original-screenshot-reference")
            self.assertEqual(summary["referenced"], [str(screenshot.resolve())])
            self.assertEqual(issue["evidenceImage"], str(screenshot.resolve()))
            self.assertNotIn("evidenceScope", issue)
            self.assertNotIn("evidenceTargetElementId", issue)
            self.assertNotIn("evidenceTargetCoord", issue)
            self.assertFalse(unused_output.exists())
            self.assertTrue(legacy_image.is_file())

    def test_rejects_non_screenshots_source_without_falling_back_to_legacy_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside.png"
            Image.new("RGB", (8, 8), "white").save(outside)
            results = root / "results.json"
            results.write_text(json.dumps([{
                "skill": "example",
                "units": [{
                    "tab": "全部",
                    "details": {
                        "screenshot": str(outside),
                        "issues": [{"elementId": "E1", "rating": "达标", "evidenceImage": "/tmp/old.png"}],
                    },
                }],
            }], ensure_ascii=False))

            completed = subprocess.run([
                sys.executable, str(SCRIPT), "--results", str(results),
            ], check=True, capture_output=True, text=True)

            summary = json.loads(completed.stdout)
            issue = json.loads(results.read_text())[0]["units"][0]["details"]["issues"][0]
            self.assertEqual(summary["referenced"], [])
            self.assertEqual(summary["skipped"][0]["reason"], "original_screenshot_outside_screenshots")
            self.assertNotIn("evidenceImage", issue)


if __name__ == "__main__":
    unittest.main()
