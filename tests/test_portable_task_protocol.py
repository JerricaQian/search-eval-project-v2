from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_DIR / "workflow" / "eval_cli.py"
PROMOTE_PATH = PROJECT_DIR / "workflow" / "promote_phase2_attempt.py"


class PortableTaskProtocolTest(unittest.TestCase):
    @staticmethod
    def eval_rows(task: dict) -> list[dict]:
        return [
            {"dimension": target["dimension"], "skill": target["skill"], "units": []}
            for target in task["evalTargets"]
        ]

    def write_completion_fixture(self, task: dict, result_path: Path, issue_evidence: str | None = None) -> None:
        manifest = Path(task["workflowArgs"]["phase2Outputs"][0]["manifest"])
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("{}")
        manifest_audit = Path(task["workflowArgs"]["phase2Outputs"][0]["audit"])
        manifest_audit.write_text('{"valid": true}')
        rows = self.eval_rows(task)
        evidence_images: list[str] = []
        if issue_evidence is not None:
            screenshot = task["workflowArgs"]["phase2Outputs"][0]["screenshot"]
            rows[0]["units"] = [{
                "tab": "全部",
                "details": {
                    "screenshot": screenshot,
                    "issues": [{"elementId": "E1", "rating": "不达标", "evidenceImage": issue_evidence}],
                },
            }]
            evidence_images = [issue_evidence]
        eval_result = Path(task["workflowArgs"]["stagePaths"]["evalResultFile"])
        eval_result.parent.mkdir(parents=True)
        eval_result.write_text(json.dumps(rows, ensure_ascii=False))
        eval_audit = Path(task["workflowArgs"]["stagePaths"]["evalAuditFile"])
        eval_audit.write_text('{"valid": true}')
        measurements = Path(task["workflowArgs"]["stagePaths"]["measurementsDir"]) / "phase3-measurements.json"
        measurements.parent.mkdir(parents=True)
        measurements.write_text('{"valid": true}')
        result_path.write_text(json.dumps({
            "ok": True,
            "query": "露营",
            "stageA": {
                "phase2Attempts": 1,
                "retryPlans": [{"contract": "phase2.retry-plan", "attempt": 1, "maxAttempts": 3, "errors": [], "retryRequired": False}],
                "elementListPaths": [str(manifest)],
                "elementAuditPaths": [str(manifest_audit)],
            },
            "stageB": {
                "measurementsIndex": str(measurements),
                "evalResultFile": str(eval_result),
                "evalAuditFile": str(eval_audit),
                "evalCount": len(task["evalTargets"]),
            },
            "stageC": {"evidenceImages": evidence_images},
            "stageD": {},
            "blockedAt": "",
            "error": "",
        }, ensure_ascii=False))

    def prepare(self, root: Path, run_id: str = "portable-01", image_count: int = 1) -> dict:
        source = root / "external"
        project = root / "project"
        source.mkdir()
        project.mkdir()
        (project / "phase3-evaluation").symlink_to(PROJECT_DIR / "phase3-evaluation", target_is_directory=True)
        for screen in range(1, image_count + 1):
            Image.new("RGB", (100, 100), "white").save(source / f"露营_全部_{screen}.png")
        completed = subprocess.run(
            [
                sys.executable, str(CLI_PATH), "prepare-evaluate",
                "--project-dir", str(project), "--source-dir", str(source),
                "--query", "露营", "--min-bytes", "1", "--run-id", run_id,
                "--evaluation-selection", '{"mode":"full_19"}', "--report-outlet", "none",
            ],
            check=True, capture_output=True, text=True,
        )
        return json.loads(completed.stdout)

    def test_prepare_batch_publishes_image_based_subagent_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp), run_id="batch-image-trigger", image_count=4)
            task_path = Path(payload["portableTask"]["taskPath"])
            project_dir = task_path.parents[2]
            prepared = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-batch",
                "--project-dir", str(project_dir), "--batch-id", "batch-image-trigger",
                "--max-query-attempts", "3",
                "--task", str(task_path),
            ], check=True, capture_output=True, text=True)

            policy = json.loads(prepared.stdout)["subagentPolicy"]
            self.assertEqual(policy["trigger"], "selected_screenshot_count_gt_3")
            self.assertEqual(policy["selectedScreenshotCount"], 4)
            self.assertTrue(policy["requiresQuerySubagents"])
            self.assertTrue(policy["singleQueryPerAgent"])
            self.assertEqual(policy["maxParallelAgents"], 3)

    def test_prepare_creates_immutable_task_and_rejects_duplicate_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self.prepare(root)
            portable = payload["portableTask"]
            task_path = Path(portable["taskPath"])
            task = json.loads(task_path.read_text())

            self.assertEqual(portable["protocol"], "MEITUAN_EVAL_TASK")
            self.assertEqual(task["runId"], "portable-01")
            self.assertEqual(task["workflowArgs"]["tag"], "portable-01")
            self.assertEqual(task["workflowArgs"]["batchId"], "portable-01")
            self.assertEqual(task["workflowArgs"]["rerunId"], "portable-01")
            self.assertEqual(task["workflowArgs"]["pythonBin"], sys.executable)
            self.assertIn("/workflow/contracts/phase234-query-pipeline.md", task["contractFiles"][0])
            self.assertTrue(task["contractFiles"][1].endswith("evaluation-result.schema.json"))
            self.assertEqual(task["dispatch"]["protocol"], "MEITUAN_AGENT_DISPATCH")
            self.assertEqual(task["dispatch"]["inputMode"], "task_path_only")
            self.assertEqual(task["dispatch"]["supportedHosts"], ["claude", "codex", "catpaw", "generic"])
            self.assertEqual(task["requiredCapabilities"]["readImagePixels"], True)
            self.assertEqual(len(task["workflowArgs"]["phase2Outputs"]), 1)
            self.assertTrue(task["workflowArgs"]["phase2Outputs"][0]["candidateBundle"].endswith(".candidate-bundle.v2.json"))
            self.assertIn("attemptRoot", task["workflowArgs"]["phase2Outputs"][0])
            self.assertIn("stagePaths", task["workflowArgs"])
            self.assertEqual(task["workflowArgs"]["screenshotIdentityMap"]["contract"], "screenshot.identity-map")

            source = root / "external"
            project = root / "project"
            repeated = subprocess.run(
                [
                    sys.executable, str(CLI_PATH), "prepare-evaluate",
                    "--project-dir", str(project), "--source-dir", str(source),
                    "--query", "露营", "--min-bytes", "1", "--run-id", "portable-01",
                    "--evaluation-selection", '{"mode":"full_19"}', "--report-outlet", "none",
                ],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(repeated.returncode, 2)
            self.assertEqual(json.loads(repeated.stdout)["status"], "run_setup_failed")

    def test_prepare_dispatch_uses_one_envelope_for_claude_codex_and_catpaw(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp))
            task_path = Path(payload["portableTask"]["taskPath"])
            capabilities = [
                "readImagePixels", "readFiles", "runCommands", "writeJson",
            ]
            envelopes = {}
            for host in ("claude", "codex", "catpaw"):
                command = [
                    sys.executable, str(CLI_PATH), "prepare-dispatch",
                    "--task", str(task_path), "--host", host,
                ]
                for capability in capabilities:
                    command.extend(["--capability", capability])
                completed = subprocess.run(command, check=True, capture_output=True, text=True)
                envelopes[host] = json.loads(completed.stdout)

            for host, envelope in envelopes.items():
                self.assertTrue(envelope["ok"], host)
                self.assertEqual(envelope["protocol"], "MEITUAN_AGENT_DISPATCH")
                self.assertEqual(envelope["status"], "ready_for_dispatch")
                self.assertEqual(envelope["taskPath"], str(task_path.resolve()))
                self.assertEqual(envelope["input"], {"mode": "task_path_only", "value": str(task_path.resolve())})
                self.assertEqual(envelope["missingCapabilities"], [])
                self.assertEqual(envelope["completionCommand"], envelopes["claude"]["completionCommand"])
            self.assertEqual(envelopes["claude"]["binding"]["mode"], "native_agent_definition")
            self.assertTrue(envelopes["claude"]["binding"]["definitionFile"].endswith(".claude/agents/evaluation-agent.md"))
            self.assertEqual(envelopes["codex"]["binding"]["mode"], "portable_task")
            self.assertEqual(envelopes["catpaw"]["binding"]["mode"], "portable_task")

            awaiting = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-dispatch", "--task", str(task_path), "--host", "generic",
            ], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(awaiting.stdout)["status"], "awaiting_capability_confirmation")

            blocked = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-dispatch", "--task", str(task_path), "--host", "codex",
                "--capability", "readFiles",
            ], check=False, capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 2)
            blocked_payload = json.loads(blocked.stdout)
            self.assertEqual(blocked_payload["status"], "blocked_preflight")
            self.assertIn("readImagePixels", blocked_payload["missingCapabilities"])

    def test_prepare_dispatch_accepts_tasks_created_before_dispatch_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp))
            task_path = Path(payload["portableTask"]["taskPath"])
            task = json.loads(task_path.read_text())
            task.pop("dispatch")
            task["contractFiles"][0] = str(PROJECT_DIR / ".claude/agents/phase234-query-pipeline.md")
            task_path.write_text(json.dumps(task, ensure_ascii=False))

            command = [
                sys.executable, str(CLI_PATH), "prepare-dispatch",
                "--task", str(task_path), "--host", "codex",
            ]
            for capability in ("readImagePixels", "readFiles", "runCommands", "writeJson"):
                command.extend(["--capability", capability])
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            envelope = json.loads(completed.stdout)
            self.assertEqual(envelope["status"], "ready_for_dispatch")
            self.assertEqual(envelope["input"]["mode"], "task_path_only")

    def test_claude_compatibility_files_delegate_to_host_neutral_contracts(self) -> None:
        agent_adapter = (PROJECT_DIR / ".claude/agents/phase234-query-pipeline.md").read_text()
        schema_adapter = json.loads(
            (PROJECT_DIR / ".claude/contracts/evaluation-result.schema.json").read_text()
        )
        canonical_contract = PROJECT_DIR / "workflow/contracts/phase234-query-pipeline.md"
        canonical_schema = PROJECT_DIR / "workflow/contracts/evaluation-result.schema.json"

        self.assertIn("workflow/contracts/phase234-query-pipeline.md", agent_adapter)
        self.assertEqual(
            schema_adapter["$ref"],
            "../../workflow/contracts/evaluation-result.schema.json",
        )
        self.assertTrue(canonical_contract.is_file())
        self.assertEqual(json.loads(canonical_schema.read_text())["type"], "object")

    def test_promote_phase2_attempt_publishes_validated_winner_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "IMG_0001.PNG"
            Image.new("RGB", (100, 100), "white").save(screenshot)
            attempt = root / "attempt"
            attempt.mkdir()
            manifest = attempt / "manifest.json"
            manifest.write_text(json.dumps({
                "screenshot": str(screenshot.resolve()),
                "recognition": {"phase3Ready": True, "wholePageGate": True},
            }))
            manifest_audit = attempt / "manifest.audit.json"
            manifest_audit.write_text('{"valid":true}')
            recognition_audit = attempt / "recognition.audit.json"
            recognition_audit.write_text(json.dumps({
                "contractVersion": "phase2.current-image-calibration.v1",
                "reviewedAgainstCurrentPixels": True,
            }))
            final = root / "final"
            command = [
                sys.executable, str(PROMOTE_PATH), "--screenshot", str(screenshot),
                "--manifest", str(manifest), "--manifest-audit", str(manifest_audit),
                "--recognition-audit", str(recognition_audit),
                "--output-manifest", str(final / "manifest.json"),
                "--output-audit", str(final / "manifest.audit.json"),
                "--output-recognition-audit", str(final / "recognition.audit.json"),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True)
            self.assertTrue((final / "manifest.json").is_file())
            repeated = subprocess.run(command, check=False, capture_output=True, text=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("refuse_to_overwrite", repeated.stderr)

    def test_prepare_freezes_retry_and_measurement_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external"
            project = root / "project"
            source.mkdir()
            project.mkdir()
            (project / "phase3-evaluation").symlink_to(PROJECT_DIR / "phase3-evaluation", target_is_directory=True)
            Image.new("RGB", (100, 100), "white").save(source / "露营_全部_1.png")
            completed = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-evaluate", "--project-dir", str(project),
                "--source-dir", str(source), "--query", "露营", "--min-bytes", "1", "--run-id", "portable-final",
                "--evaluation-selection", '{"mode":"full_19"}', "--report-outlet", "none",
            ], check=True, capture_output=True, text=True)
            payload = json.loads(completed.stdout)
            task = json.loads(Path(payload["portableTask"]["taskPath"]).read_text())
            self.assertEqual(task["protocol"], "MEITUAN_EVAL_TASK")
            self.assertEqual(task["workflowArgs"]["phase2MaxAttempts"], 3)
            self.assertIn("/workflow/contracts/phase234-query-pipeline.md", task["contractFiles"][0])
            self.assertIn("attemptRoot", task["workflowArgs"]["phase2Outputs"][0])

    def test_finalize_rejects_stage_a_before_retry_budget_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, project = root / "external", root / "project"
            source.mkdir(); project.mkdir()
            (project / "phase3-evaluation").symlink_to(PROJECT_DIR / "phase3-evaluation", target_is_directory=True)
            Image.new("RGB", (100, 100), "white").save(source / "露营_全部_1.png")
            created = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-evaluate", "--project-dir", str(project), "--source-dir", str(source),
                "--query", "露营", "--min-bytes", "1", "--run-id", "no-early-stop",
                "--evaluation-selection", '{"mode":"full_19"}', "--report-outlet", "none",
            ], check=True, capture_output=True, text=True)
            task_path = Path(json.loads(created.stdout)["portableTask"]["taskPath"])
            task = json.loads(task_path.read_text())
            result_path = Path(task["resultPath"])
            result_path.write_text(json.dumps({
                "ok": False, "query": "露营", "stageA": {"phase2Attempts": 1, "retryPlans": [{}]},
                "stageB": {}, "stageC": {}, "stageD": {}, "blockedAt": "stageA", "error": "first gate failed",
            }, ensure_ascii=False))
            completed = subprocess.run([sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)], check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)["error"], "stageA_block_requires_exhausted_retry_plans")

    def test_finalize_rejects_success_when_retry_history_is_not_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, project = root / "external", root / "project"
            source.mkdir(); project.mkdir()
            (project / "phase3-evaluation").symlink_to(PROJECT_DIR / "phase3-evaluation", target_is_directory=True)
            Image.new("RGB", (100, 100), "white").save(source / "露营_全部_1.png")
            created = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-evaluate", "--project-dir", str(project), "--source-dir", str(source),
                "--query", "露营", "--min-bytes", "1", "--run-id", "no-passive-retry",
                "--evaluation-selection", '{"mode":"full_19"}', "--report-outlet", "none",
            ], check=True, capture_output=True, text=True)
            task_path = Path(json.loads(created.stdout)["portableTask"]["taskPath"])
            task = json.loads(task_path.read_text())
            Path(task["resultPath"]).write_text(json.dumps({
                "ok": True, "query": "露营",
                "stageA": {"phase2Attempts": 1, "retryPlans": [], "elementListPaths": [], "elementAuditPaths": []},
                "stageB": {}, "stageC": {}, "stageD": {}, "blockedAt": "", "error": "",
            }, ensure_ascii=False))
            completed = subprocess.run([sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", task["resultPath"]], check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)["error"], "stageA_retry_history_missing_or_incomplete")

    def test_prepare_preserves_explicit_evaluation_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external"
            project = root / "project"
            source.mkdir()
            project.mkdir()
            (project / "phase3-evaluation").symlink_to(PROJECT_DIR / "phase3-evaluation", target_is_directory=True)
            Image.new("RGB", (100, 100), "white").save(source / "露营_全部_1.png")
            selection = {"mode": "custom_skills", "skills": [
                {"dimension": "phase3-card_or_component-eval", "skill": "eval-8-info-redundancy"},
            ]}
            completed = subprocess.run(
                [
                    sys.executable, str(CLI_PATH), "prepare-evaluate",
                    "--project-dir", str(project), "--source-dir", str(source), "--query", "露营",
                    "--min-bytes", "1", "--run-id", "portable-selection",
                    "--evaluation-selection", json.dumps(selection, ensure_ascii=False), "--report-outlet", "none",
                ],
                check=True, capture_output=True, text=True,
            )
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["workflowArgs"]["evaluationSelection"], selection)
            task = json.loads(Path(payload["portableTask"]["taskPath"]).read_text())
            self.assertEqual([(target["dimension"], target["skill"]) for target in task["evalTargets"]], [
                ("phase3-card_or_component-eval", "eval-8-info-redundancy"),
            ])
            task_project = Path(payload["workflowArgs"]["projectDir"])
            self.assertIn(str(task_project / "phase3-evaluation/dimensions/card-component/skills/eval-8-info-redundancy/SKILL.md"), task["requiredReads"])
            self.assertNotIn(str(task_project / "phase3-evaluation/dimensions/card-component/skills/eval-7-info-authenticity/SKILL.md"), task["requiredReads"])

    def test_finalize_accepts_only_complete_verified_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self.prepare(root)
            project = root / "project"
            task_path = Path(payload["portableTask"]["taskPath"])
            result_path = Path(payload["portableTask"]["resultPath"])
            task = json.loads(task_path.read_text())

            manifest = Path(task["workflowArgs"]["phase2Outputs"][0]["manifest"])
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}")
            manifest_audit = Path(task["workflowArgs"]["phase2Outputs"][0]["audit"])
            manifest_audit.write_text('{"valid": true}')
            eval_result = Path(task["workflowArgs"]["stagePaths"]["evalResultFile"])
            eval_result.parent.mkdir(parents=True)
            eval_result.write_text(json.dumps(self.eval_rows(task)))
            eval_audit = Path(task["workflowArgs"]["stagePaths"]["evalAuditFile"])
            eval_audit.write_text('{"valid": true}')
            measurements = Path(task["workflowArgs"]["stagePaths"]["measurementsDir"]) / "phase3-measurements.json"
            measurements.parent.mkdir(parents=True)
            measurements.write_text('{"valid": true}')
            result_path.write_text(json.dumps({
                "ok": True,
                "query": "露营",
                "stageA": {"phase2Attempts": 1, "retryPlans": [{"contract": "phase2.retry-plan", "attempt": 1, "maxAttempts": 3, "errors": [], "retryRequired": False}], "elementListPaths": [str(manifest)], "elementAuditPaths": [str(manifest_audit)]},
                "stageB": {"measurementsIndex": str(measurements), "evalResultFile": str(eval_result), "evalAuditFile": str(eval_audit), "evalCount": len(task["evalTargets"])},
                "stageC": {"evidenceImages": []},
                "stageD": {},
                "blockedAt": "",
                "error": "",
            }, ensure_ascii=False))

            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=True, capture_output=True, text=True,
            )
            receipt = json.loads(completed.stdout)
            self.assertEqual(receipt["status"], "completed")
            self.assertTrue(Path(receipt["receiptPath"]).is_file())

    def test_finalize_accepts_problem_evidence_referencing_task_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp), run_id="original-evidence")
            task_path = Path(payload["portableTask"]["taskPath"])
            result_path = Path(payload["portableTask"]["resultPath"])
            task = json.loads(task_path.read_text())
            screenshot = task["workflowArgs"]["phase2Outputs"][0]["screenshot"]
            self.write_completion_fixture(task, result_path, screenshot)

            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(json.loads(completed.stdout)["status"], "completed")

    def test_finalize_rejects_legacy_redbox_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp), run_id="legacy-redbox")
            task_path = Path(payload["portableTask"]["taskPath"])
            result_path = Path(payload["portableTask"]["resultPath"])
            task = json.loads(task_path.read_text())
            legacy = Path(task["projectDir"]) / "screenshots-out" / "evidence" / "legacy.png"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (8, 8), "red").save(legacy)
            self.write_completion_fixture(task, result_path, str(legacy))

            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("stageC.issue_evidence_must_equal_task_screenshot", json.loads(completed.stdout)["error"])

    def test_finalize_rejects_empty_result_for_selected_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self.prepare(root)
            task_path = Path(payload["portableTask"]["taskPath"])
            task = json.loads(task_path.read_text())
            result_path = Path(task["resultPath"])

            manifest = Path(task["workflowArgs"]["phase2Outputs"][0]["manifest"])
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}")
            manifest_audit = Path(task["workflowArgs"]["phase2Outputs"][0]["audit"])
            manifest_audit.write_text('{"valid": true}')
            eval_result = Path(task["workflowArgs"]["stagePaths"]["evalResultFile"])
            eval_result.parent.mkdir(parents=True)
            eval_result.write_text("[]")
            eval_audit = Path(task["workflowArgs"]["stagePaths"]["evalAuditFile"])
            eval_audit.write_text('{"valid": true}')
            measurements = Path(task["workflowArgs"]["stagePaths"]["measurementsDir"]) / "phase3-measurements.json"
            measurements.parent.mkdir(parents=True)
            measurements.write_text('{"valid": true}')
            result_path.write_text(json.dumps({
                "ok": True, "query": "露营",
                "stageA": {"phase2Attempts": 1, "retryPlans": [{"contract": "phase2.retry-plan", "attempt": 1, "maxAttempts": 3, "errors": [], "retryRequired": False}], "elementListPaths": [str(manifest)], "elementAuditPaths": [str(manifest_audit)]},
                "stageB": {"measurementsIndex": str(measurements), "evalResultFile": str(eval_result), "evalAuditFile": str(eval_audit), "evalCount": 0},
                "stageC": {"evidenceImages": []}, "stageD": {}, "blockedAt": "", "error": "",
            }, ensure_ascii=False))

            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)["error"], "stageB.evalResultFile:target_count_or_duplicates_invalid")

    def test_finalize_rejects_success_without_all_stages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp))
            task_path = Path(payload["portableTask"]["taskPath"])
            result_path = Path(payload["portableTask"]["resultPath"])
            result_path.write_text(json.dumps({"ok": True, "query": "露营", "blockedAt": "", "error": ""}))

            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("successful_result_missing_stage", json.loads(completed.stdout)["error"])

    def test_finalize_accepts_preflight_vision_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp))
            task_path = Path(payload["portableTask"]["taskPath"])
            result_path = Path(payload["portableTask"]["resultPath"])
            result_path.write_text(json.dumps({
                "ok": False, "query": "露营", "stageA": {}, "stageB": {}, "stageC": {}, "stageD": {},
                "blockedAt": "preflight", "error": "model_vision_not_supported: host cannot read image pixels",
            }, ensure_ascii=False))
            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=True, capture_output=True, text=True,
            )
            receipt = json.loads(completed.stdout)
            self.assertEqual(receipt["status"], "blocked")
            self.assertEqual(receipt["blockedAt"], "preflight")

    def test_finalize_rejects_retired_task_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self.prepare(root)
            task_path = Path(payload["portableTask"]["taskPath"])
            result_path = Path(payload["portableTask"]["resultPath"])
            task = json.loads(task_path.read_text())
            task["protocol"] = "MEITUAN_EVAL_TASK_LEGACY"
            task_path.write_text(json.dumps(task))
            result_path.write_text(json.dumps({
                "ok": False, "query": "露营", "stageA": {}, "stageB": {}, "stageC": {}, "stageD": {},
                "blockedAt": "stageA", "error": "old task",
            }, ensure_ascii=False))

            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(json.loads(completed.stdout)["error"], "task_protocol_invalid")

    def test_finalize_allows_blocked_task_to_complete_after_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self.prepare(root)
            project = root / "project"
            task_path = Path(payload["portableTask"]["taskPath"])
            result_path = Path(payload["portableTask"]["resultPath"])
            task = json.loads(task_path.read_text())

            result_path.write_text(json.dumps({
                "ok": False, "query": "露营", "blockedAt": "stageB", "error": "needs phase3 retry",
            }, ensure_ascii=False))
            blocked = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(json.loads(blocked.stdout)["status"], "blocked")

            manifest = Path(task["workflowArgs"]["phase2Outputs"][0]["manifest"])
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}")
            manifest_audit = Path(task["workflowArgs"]["phase2Outputs"][0]["audit"])
            manifest_audit.write_text('{"valid": true}')
            eval_result = Path(task["workflowArgs"]["stagePaths"]["evalResultFile"])
            eval_result.parent.mkdir(parents=True)
            eval_result.write_text(json.dumps(self.eval_rows(task)))
            eval_audit = Path(task["workflowArgs"]["stagePaths"]["evalAuditFile"])
            eval_audit.write_text('{"valid": true}')
            measurements = Path(task["workflowArgs"]["stagePaths"]["measurementsDir"]) / "phase3-measurements.json"
            measurements.parent.mkdir(parents=True)
            measurements.write_text('{"valid": true}')
            result_path.write_text(json.dumps({
                "ok": True, "query": "露营",
                "stageA": {"phase2Attempts": 1, "retryPlans": [{"contract": "phase2.retry-plan", "attempt": 1, "maxAttempts": 3, "errors": [], "retryRequired": False}], "elementListPaths": [str(manifest)], "elementAuditPaths": [str(manifest_audit)]},
                "stageB": {"measurementsIndex": str(measurements), "evalResultFile": str(eval_result), "evalAuditFile": str(eval_audit), "evalCount": len(task["evalTargets"])},
                "stageC": {"evidenceImages": []}, "stageD": {},
                "blockedAt": "", "error": "",
            }, ensure_ascii=False))
            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "finalize-evaluate", "--task", str(task_path), "--result", str(result_path)],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(json.loads(completed.stdout)["status"], "completed")
            self.assertTrue((task_path.parent / "receipt.blocked-stageB.json").is_file())

    def test_finalize_batch_requires_completed_tasks_and_builds_one_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            (project / "phase5-report").symlink_to(PROJECT_DIR / "phase5-report", target_is_directory=True)
            batch_id = "batch-two-queries"
            task_paths = []

            for index, query in enumerate(("咖啡", "火锅"), start=1):
                run_dir = project / "runs" / f"run-{index}"
                run_dir.mkdir(parents=True)
                screenshot = project / "screenshots" / f"{query}_全部_1.png"
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                screenshot.write_bytes(b"image")
                manifest = project / "screenshots-out" / f"elements_{query}_run-{index}.json"
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text(json.dumps({
                    "query": query,
                    "screenshot": str(screenshot),
                    "cards": [{
                        "cardId": "C1",
                        "卡片类型": "商家卡片-文字下挂",
                        "ownershipScope": "business",
                        "businessCode": "dine_in",
                        "regions": [{"name": "标题区", "elements": [{"id": "E1", "内容简述": f"原文:{query}门店"}]}],
                    }],
                }, ensure_ascii=False))
                manifest_audit = manifest.with_name(manifest.stem + ".audit.json")
                manifest_audit.write_text('{"valid": true}')
                result_dir = project / ".artifacts" / "过程文件-评测结果与审计" / batch_id / query / "results"
                result_dir.mkdir(parents=True)
                eval_result = result_dir / f"评测原始结果_{query}_full19.json"
                eval_result.write_text(json.dumps([{
                    "dimension": "phase3-card_or_component-eval",
                    "skill": "eval-8-info-redundancy",
                    "units": [{
                        "tab": "全部",
                        "rating": "优秀",
                        "reason": "未发现问题",
                        "details": {"screenshot": str(screenshot), "evidenceMode": "original-page", "issues": []},
                    }],
                }], ensure_ascii=False))
                eval_audit = result_dir / f"评测结果校验_{query}.json"
                eval_audit.write_text('{"valid": true}')
                measurements_dir = result_dir.parent / "phase3" / "measurements"
                measurements_dir.mkdir(parents=True)
                measurements = measurements_dir / "phase3-measurements.json"
                measurements.write_text('{"valid": true}')
                evidence_dir = project / "screenshots-out" / "evidence" / f"run-{index}"
                result_path = run_dir / "agent-result.json"
                result_path.write_text(json.dumps({
                    "ok": True,
                    "query": query,
                    "stageA": {"phase2Attempts": 1, "retryPlans": [{"contract": "phase2.retry-plan", "attempt": 1, "maxAttempts": 3, "errors": [], "retryRequired": False}], "elementListPaths": [str(manifest)], "elementAuditPaths": [str(manifest_audit)]},
                    "stageB": {"measurementsIndex": str(measurements), "evalResultFile": str(eval_result), "evalAuditFile": str(eval_audit), "evalCount": 1},
                    "stageC": {"evidenceImages": []},
                    "stageD": {},
                    "blockedAt": "",
                    "error": "",
                }, ensure_ascii=False))
                task_path = run_dir / "task.json"
                task_path.write_text(json.dumps({
                    "protocol": "MEITUAN_EVAL_TASK",
                    "runId": f"run-{index}",
                    "projectDir": str(project),
                    "evalTargets": [{"dimension": "phase3-card_or_component-eval", "skill": "eval-8-info-redundancy"}],
                    "workflowArgs": {
                        "query": query,
                        "batchId": batch_id,
                        "reportOutlet": "local_html",
                        "evaluationSelection": {"mode": "full_19"},
                        "evaluationScope": {
                            "schemaVersion": "phase3.eval-selection.v1",
                            "selection": {"mode": "full_19"},
                            "coverage": {"selectedCount": 19, "fullCount": 19, "isFull": True, "label": "完整19项评测"},
                        },
                        "phase2MaxAttempts": 3,
                        "phase2Outputs": [{"manifest": str(manifest), "audit": str(manifest_audit)}],
                        "stagePaths": {
                            "measurementsDir": str(measurements_dir),
                            "evalResultFile": str(eval_result),
                            "evalAuditFile": str(eval_audit),
                            "issueEvidenceDir": str(evidence_dir),
                        },
                    },
                    "resultPath": str(result_path),
                }, ensure_ascii=False))
                (run_dir / "receipt.json").write_text(json.dumps({
                    "protocol": "MEITUAN_EVAL_TASK",
                    "runId": f"run-{index}",
                    "query": query,
                    "resultPath": str(result_path),
                    "status": "completed",
                }))
                task_paths.append(task_path)

            command = [
                sys.executable, str(CLI_PATH), "finalize-batch",
                "--project-dir", str(project),
                "--batch-id", batch_id,
            ]
            for task_path in task_paths:
                command.extend(["--task", str(task_path)])
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            payload = json.loads(completed.stdout)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["queries"], ["咖啡", "火锅"])
            self.assertTrue(Path(payload["reportPath"]).is_file())
            self.assertTrue(Path(payload["datasetPath"]).is_file())

            (task_paths[1].parent / "receipt.json").write_text(json.dumps({
                "protocol": "MEITUAN_EVAL_TASK",
                "runId": "run-2",
                "query": "火锅",
                "resultPath": str(task_paths[1].parent / "agent-result.json"),
                "status": "blocked",
                "blockedAt": "stageA",
                "error": "phase2 needs review",
            }, ensure_ascii=False))
            partial = command + [
                "--output", str(project / "reports" / "partial.html"),
                "--dataset-output", str(project / "reports" / ".partial.json"),
            ]
            premature = subprocess.run(partial, check=False, capture_output=True, text=True)
            self.assertEqual(premature.returncode, 2)
            self.assertIn("phase5_batch_incomplete", json.loads(premature.stdout)["error"])

            retry_attempts = []
            previous_run = "run-2"
            for attempt in range(1, 4):
                if attempt == 1:
                    retry_task_path = task_paths[1]
                    retry_run_id = "run-2"
                else:
                    retry_run_id = f"run-2-retry-{attempt}"
                    retry_dir = project / "runs" / retry_run_id
                    retry_dir.mkdir()
                    retry_task_path = retry_dir / "task.json"
                    retry_task = json.loads(task_paths[1].read_text())
                    retry_task.update({
                        "runId": retry_run_id,
                        "batchAttempt": attempt,
                        "retryOf": previous_run,
                        "resultPath": str(retry_dir / "agent-result.json"),
                    })
                    retry_task_path.write_text(json.dumps(retry_task, ensure_ascii=False))
                    (retry_dir / "receipt.json").write_text(json.dumps({
                        "protocol": "MEITUAN_EVAL_TASK",
                        "runId": retry_run_id,
                        "query": "火锅",
                        "resultPath": str(retry_dir / "agent-result.json"),
                        "status": "blocked",
                        "blockedAt": "stageA",
                        "error": "phase2 needs review",
                    }, ensure_ascii=False))
                retry_attempts.append({
                    "attempt": attempt, "runId": retry_run_id, "taskPath": str(retry_task_path),
                    "receiptPath": str(retry_task_path.parent / "receipt.json"), "status": "blocked",
                })
                previous_run = retry_run_id

            state_path = project / "runs" / "batch-state.json"
            state_path.write_text(json.dumps({
                "protocol": "MEITUAN_EVAL_BATCH",
                "batchId": batch_id,
                "projectDir": str(project),
                "expectedBusinessTabs": ["dine_in"],
                "maxQueryAttempts": 3,
                "status": "ready_for_partial_phase5",
                "sequence": 4,
                "queries": [
                    {"query": "咖啡", "status": "completed", "attempts": [{
                        "attempt": 1, "runId": "run-1", "taskPath": str(task_paths[0]),
                        "receiptPath": str(task_paths[0].parent / "receipt.json"), "status": "completed",
                    }]},
                    {"query": "火锅", "status": "abandoned", "attempts": retry_attempts},
                ],
            }, ensure_ascii=False))
            controlled_partial = [
                sys.executable, str(CLI_PATH), "finalize-batch",
                "--project-dir", str(project), "--batch-id", batch_id,
                "--batch-state", str(state_path),
                "--output", str(project / "reports" / "partial.html"),
                "--dataset-output", str(project / "reports" / ".partial.json"),
            ]
            partial_completed = subprocess.run(controlled_partial, check=True, capture_output=True, text=True)
            partial_payload = json.loads(partial_completed.stdout)
            self.assertEqual(partial_payload["queries"], ["咖啡"])
            self.assertEqual(partial_payload["skippedTasks"][0]["query"], "火锅")
            self.assertNotIn("火锅", Path(partial_payload["reportPath"]).read_text())

    def test_batch_controller_creates_fresh_retry_tasks_and_stops_after_three_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "external"
            project = root / "project"
            source.mkdir()
            project.mkdir()
            (project / "phase3-evaluation").symlink_to(PROJECT_DIR / "phase3-evaluation", target_is_directory=True)
            Image.new("RGB", (100, 100), "white").save(source / "露营_全部_1.png")
            created = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-evaluate",
                "--project-dir", str(project), "--source-dir", str(source), "--query", "露营",
                "--min-bytes", "1", "--run-id", "batch-retry.q1", "--batch-id", "batch-retry",
                "--evaluation-selection", '{"mode":"full_19"}', "--report-outlet", "none",
            ], check=True, capture_output=True, text=True)
            first_task = Path(json.loads(created.stdout)["portableTask"]["taskPath"])

            def block(task_path: Path) -> None:
                task = json.loads(task_path.read_text())
                result_path = Path(task["resultPath"])
                result_path.write_text(json.dumps({
                    "ok": False, "query": "露营", "stageA": {}, "stageB": {}, "stageC": {}, "stageD": {},
                    "blockedAt": "preflight", "error": "temporary host failure",
                }, ensure_ascii=False))
                subprocess.run([
                    sys.executable, str(CLI_PATH), "finalize-evaluate",
                    "--task", str(task_path), "--result", str(result_path),
                ], check=True, capture_output=True, text=True)

            block(first_task)
            prepared = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-batch",
                "--project-dir", str(project), "--batch-id", "batch-retry",
                "--max-query-attempts", "3",
                "--task", str(first_task),
            ], check=True, capture_output=True, text=True)
            state_path = Path(json.loads(prepared.stdout)["statePath"])

            for attempt in (2, 3):
                advanced = subprocess.run([
                    sys.executable, str(CLI_PATH), "advance-batch", "--state", str(state_path),
                ], check=True, capture_output=True, text=True)
                advanced_payload = json.loads(advanced.stdout)
                self.assertEqual(advanced_payload["retryQueries"], ["露营"])
                state_path = Path(advanced_payload["statePath"])
                retried = subprocess.run([
                    sys.executable, str(CLI_PATH), "create-batch-retry", "--state", str(state_path),
                    "--query", "露营", "--run-id", f"batch-retry.q1.attempt{attempt}",
                ], check=True, capture_output=True, text=True)
                retry_payload = json.loads(retried.stdout)
                retry_task = Path(retry_payload["taskPath"])
                retry_contract = json.loads(retry_task.read_text())
                self.assertEqual(retry_contract["batchAttempt"], attempt)
                self.assertNotEqual(retry_contract["runId"], json.loads(first_task.read_text())["runId"])
                self.assertTrue(retry_contract["retryOf"])
                state_path = Path(retry_payload["statePath"])
                block(retry_task)

            exhausted = subprocess.run([
                sys.executable, str(CLI_PATH), "advance-batch", "--state", str(state_path),
            ], check=False, capture_output=True, text=True)
            self.assertEqual(exhausted.returncode, 2)
            exhausted_payload = json.loads(exhausted.stdout)
            self.assertEqual(exhausted_payload["status"], "failed")
            self.assertEqual(exhausted_payload["failedQueries"], ["露营"])
            final_state = json.loads(Path(exhausted_payload["statePath"]).read_text())
            self.assertEqual(final_state["queries"][0]["status"], "abandoned")
            self.assertEqual(len(final_state["queries"][0]["attempts"]), 3)

    def test_advance_batch_keeps_missing_receipt_pending_without_charging_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = self.prepare(Path(tmp), run_id="batch-await.q1")
            task_path = Path(payload["portableTask"]["taskPath"])
            project_dir = task_path.parents[2]
            prepared = subprocess.run([
                sys.executable, str(CLI_PATH), "prepare-batch",
                "--project-dir", str(project_dir), "--batch-id", "batch-await.q1",
                "--max-query-attempts", "3", "--task", str(task_path),
            ], check=True, capture_output=True, text=True)
            state_path = Path(json.loads(prepared.stdout)["statePath"])

            advanced = subprocess.run([
                sys.executable, str(CLI_PATH), "advance-batch", "--state", str(state_path),
            ], check=True, capture_output=True, text=True)
            output = json.loads(advanced.stdout)
            state = json.loads(Path(output["statePath"]).read_text())

        self.assertEqual(output["status"], "awaiting_receipts")
        self.assertEqual(output["pendingQueries"], ["露营"])
        self.assertEqual(output["retryQueries"], [])
        self.assertEqual(state["queries"][0]["status"], "pending")
        self.assertEqual(state["queries"][0]["attempts"][0]["status"], "pending")
        self.assertEqual(len(state["queries"][0]["attempts"]), 1)
