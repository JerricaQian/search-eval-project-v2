#!/usr/bin/env python3
"""Portable preflight and completion guard for search evaluation runs.

The JS workflow is a host DSL.  This CLI owns the small, host-neutral boundary:
copy/discovery, an immutable task file with a unique run id, and final artifact
verification.  It deliberately does not perform the LLM judgement itself.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parents[1]
HANDOFF_PROTOCOL = "MEITUAN_EVAL_HANDOFF"
TASK_PROTOCOL = "MEITUAN_EVAL_TASK"
BATCH_PROTOCOL = "MEITUAN_EVAL_BATCH"
DISPATCH_PROTOCOL = "MEITUAN_AGENT_DISPATCH"
SUPPORTED_HOSTS = ("claude", "codex", "catpaw", "generic")
RUN_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
STAGES = ("stageA", "stageB", "stageC", "stageD")


def load_module(relative_path: str, module_name: str) -> Any:
    path = PROJECT_DIR / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


DISCOVERY = load_module("phase1-screenshot/scripts/discover_screenshot_groups.py", "search_eval_discovery")
COPY = load_module("phase1-screenshot/scripts/ingest_external_screenshots.py", "search_eval_copy")
EVAL_TARGET_RESOLVER = load_module(
    "phase3-evaluation/common/routing/resolve_eval_targets.py",
    "search_eval_target_resolver",
)


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


def valid_run_id(value: str) -> bool:
    return 1 <= len(value) <= 80 and value[0].isalnum() and all(char in RUN_ID_CHARS for char in value)


def parse_evaluation_selection(value: str) -> dict[str, Any] | None:
    """Parse the optional user-facing Phase3 selection without judging it.

    Exact dimension/Skill validation belongs to ``resolve_eval_targets.py`` in
    the workflow, because that script reads the current catalog once and is
    shared by both host paths.
    """
    if not value:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("evaluation_selection_must_be_json_object")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_identity_map(path: Path, screenshot_root: Path, imported_paths: set[str]) -> dict[str, Any]:
    """Validate the host's current-pixel screenshot identity handoff.

    The portable CLI cannot perform model vision. A vision-capable host writes
    this small immutable map first; the CLI verifies paths and bytes before it
    creates a query task. Filename parsing is never required here.
    """
    payload = read_json(path.resolve())
    if not isinstance(payload, dict) or payload.get("contract") != "screenshot.identity-map":
        raise ValueError("identity_map_contract_invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("identity_map_entries_missing")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError(f"identity_map_entry_not_object:{index}")
        source = Path(str(raw.get("sourcePath", ""))).resolve()
        try:
            source.relative_to(screenshot_root.resolve())
        except ValueError as exc:
            raise ValueError(f"identity_map_path_outside_screenshots:{source}") from exc
        source_string = str(source)
        if source_string in seen or source_string not in imported_paths or not source.is_file():
            raise ValueError(f"identity_map_path_not_unique_current_import:{source}")
        seen.add(source_string)
        query = str(raw.get("query", "")).strip()
        identity_source = str(raw.get("identitySource", "")).strip()
        expected_hash = str(raw.get("sha256", "")).lower()
        if not query or identity_source not in {"current_pixels", "filename", "user_confirmed"}:
            raise ValueError(f"identity_map_identity_incomplete:{source}")
        actual_hash = sha256_file(source)
        if expected_hash != actual_hash:
            raise ValueError(f"identity_map_sha256_mismatch:{source}")
        confidence = raw.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise ValueError(f"identity_map_confidence_invalid:{source}")
        normalized.append({
            "sourcePath": source_string,
            "originalFilename": source.name,
            "sha256": actual_hash,
            "query": query,
            "tab": str(raw.get("tab", "")).strip(),
            "screen": str(raw.get("screen", "")).strip(),
            "identitySource": identity_source,
            "confidence": float(confidence),
        })
    return {"contract": "screenshot.identity-map", "entries": normalized}


def inline_identity_map(paths: list[str], query: str, identity_source: str,
                        discovery_group: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata: dict[str, tuple[str, str]] = {}
    if isinstance(discovery_group, dict):
        for tab in discovery_group.get("tabs", []):
            if not isinstance(tab, dict):
                continue
            for screen, path in zip(tab.get("screens", []), tab.get("files", [])):
                metadata[str(Path(str(path)).resolve())] = (str(tab.get("tab", "")), str(screen))
    entries = []
    for raw in paths:
        path = Path(raw).resolve()
        tab, screen = metadata.get(str(path), ("", ""))
        entries.append({
            "sourcePath": str(path),
            "originalFilename": path.name,
            "sha256": sha256_file(path),
            "query": query,
            "tab": tab,
            "screen": screen,
            "identitySource": identity_source,
            "confidence": 1.0,
        })
    return {"contract": "screenshot.identity-map", "entries": entries}


def resolve_evaluation_scope(project_dir: Path, workflow_args: dict[str, Any]) -> dict[str, Any]:
    """Freeze the exact Phase3 reading set into every portable task.

    A user selection is not an instruction for an agent to interpret later.  It
    is resolved while the task is created, so the immutable handoff names every
    selected leaf Skill and its dimension contract.  This also makes a changed
    catalog or a bad selection fail before any screenshot work starts.
    """
    resolved = EVAL_TARGET_RESOLVER.resolve(
        project_dir,
        workflow_args.get("evaluationSelection"),
        workflow_args.get("dimensions"),
    )
    required_reads = [
        "workflow/contracts/phase234-query-pipeline.md",
        "phase3-evaluation/SKILL.md",
        "phase3-evaluation/common/references/knowledge-index.md",
    ]
    for target in resolved["evalTargets"]:
        required_reads.extend([target["contractPath"], target["skillPath"]])
    # Keep order deterministic while making repeated shared contracts explicit
    # only once in the immutable task.
    resolved["requiredReads"] = list(dict.fromkeys(required_reads))
    return resolved


def write_once(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"refuse_to_overwrite:{path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def phase2_outputs(project_dir: Path, workflow_args: dict[str, Any], run_id: str) -> list[dict[str, str]]:
    """Freeze one candidate/review/publish path set per selected screenshot."""
    outputs: list[dict[str, str]] = []
    annotated = project_dir / "screenshots-out"
    artifact_root = project_dir / ".artifacts" / "过程文件-评测结果与审计" / str(workflow_args["batchId"]) / run_id / "phase2"
    for screenshot_raw in workflow_args.get("selectedScreenshots", []):
        screenshot = Path(str(screenshot_raw)).resolve()
        stem = screenshot.stem
        manifest = annotated / f"elements_{stem}_{run_id}.json"
        output = {
            "screenshot": str(screenshot),
            "candidateBundle": str(manifest.with_suffix(".candidate-bundle.v2.json")),
            "visualReview": str(manifest.with_suffix(".visual-review.json")),
            "manifest": str(manifest),
            "audit": str(manifest.with_suffix(".audit.json")),
            "recognitionAudit": str(manifest.with_suffix(".recognition-audit.json")),
            "artifactsDir": str(artifact_root / stem),
        }
        output["attemptRoot"] = str(artifact_root / stem / "attempts")
        outputs.append(output)
    if len({item["manifest"] for item in outputs}) != len(outputs):
        raise ValueError("phase2_output_manifest_collision")
    return outputs


def archive_blocked_receipt_for_completion(receipt_path: Path, verified: dict[str, Any]) -> None:
    """Preserve a prior blocked receipt when the same task later completes.

    A blocked Evaluation Agent result is a terminal result for that attempt,
    but it must not prevent a controlled retry of the exact same portable task.
    Only the one-way ``blocked -> completed`` transition is allowed here; a
    completed delivery remains immutable.
    """
    if not receipt_path.exists() or verified.get("status") != "completed":
        return
    previous = read_json(receipt_path)
    if not isinstance(previous, dict) or previous.get("status") != "blocked":
        return
    stage = str(previous.get("blockedAt") or "unknown")
    candidate = receipt_path.with_name(f"receipt.blocked-{stage}.json")
    index = 2
    while candidate.exists():
        candidate = receipt_path.with_name(f"receipt.blocked-{stage}-{index}.json")
        index += 1
    receipt_path.replace(candidate)


def portable_task(project_dir: Path, workflow_args: dict[str, Any], run_id: str, runs_dir: Path,
                  *, batch_attempt: int = 1, retry_of: str = "") -> dict[str, Any]:
    run_dir = runs_dir / run_id
    if run_dir.exists():
        raise ValueError(f"run_id_already_exists:{run_dir}")
    run_dir.mkdir(parents=True)
    task_path = run_dir / "task.json"
    result_path = run_dir / "agent-result.json"
    protocol = TASK_PROTOCOL
    evaluation_scope = resolve_evaluation_scope(project_dir, workflow_args)
    artifact_run_dir = project_dir / ".artifacts" / "过程文件-评测结果与审计" / str(workflow_args["batchId"]) / run_id
    # The resolved scope is the source of truth for the agent.  Keep the
    # original selection too, as an auditable record of the user's request.
    workflow_args = {
        **workflow_args,
        "evaluationScope": evaluation_scope,
        "phase2Outputs": phase2_outputs(project_dir, workflow_args, run_id),
        "stagePaths": {
            "measurementsDir": str(artifact_run_dir / "phase3" / "measurements"),
            "evalResultFile": str(artifact_run_dir / "results" / f"评测原始结果_{run_id}.json"),
            "evalAuditFile": str(artifact_run_dir / "results" / f"评测结果校验_{run_id}.json"),
            "phase2ReviewFile": str(artifact_run_dir / "results" / f"待回退Phase2复核_{run_id}.json"),
            # Frozen for older host adapters. New Phase4 runs never write here;
            # they reference the selected screenshots directly.
            "issueEvidenceDir": str(project_dir / "screenshots-out" / "evidence" / run_id),
        },
    }
    task = {
        "protocol": protocol,
        "runId": run_id,
        "batchAttempt": batch_attempt,
        "retryOf": retry_of,
        "projectDir": str(project_dir),
        "workflowArgs": workflow_args,
        "contractFiles": [
            str(project_dir / "workflow/contracts/phase234-query-pipeline.md"),
            str(project_dir / "workflow/contracts/evaluation-result.schema.json"),
            str(project_dir / "workflow/screenshot-identity.schema.json"),
        ],
        "dispatch": {
            "protocol": DISPATCH_PROTOCOL,
            "agentRole": "evaluation-agent",
            "inputMode": "task_path_only",
            "canonicalContract": str(project_dir / "workflow/contracts/phase234-query-pipeline.md"),
            "supportedHosts": list(SUPPORTED_HOSTS),
        },
        "requiredCapabilities": {
            "readImagePixels": True,
            "readFiles": True,
            "runCommands": True,
            "writeJson": True,
        },
        "requiredReads": [str(project_dir / path) for path in evaluation_scope["requiredReads"]],
        "evalTargets": evaluation_scope["evalTargets"],
        "resultPath": str(result_path),
        "completionCommand": [
            sys.executable,
            str(PROJECT_DIR / "workflow/eval_cli.py"),
            "finalize-evaluate",
            "--task",
            str(task_path),
            "--result",
            str(result_path),
        ],
        "hostInstructions": [
            "Before dispatch, verify every requiredCapabilities value. If image pixels cannot be read in this host, write a blocked result with blockedAt=preflight and error=model_vision_not_supported; do not start Phase2 or Phase3.",
            "Before Phase3, read every requiredReads file from disk exactly once. The task evalTargets are the only permitted Phase3 Skills; do not read or rate an unselected leaf Skill.",
            "Read knowledge-index.md and its directly referenced common rules as required by the pipeline, then read each selected target's contractPath and skillPath. Do not infer a Skill path from user text.",
            "Use workflowArgs.evaluationScope/evalTargets as immutable input. If a required file is unavailable or the target set cannot be followed, return the appropriate blocked Stage instead of substituting another Skill.",
            "Run exactly one Evaluation Agent for this query through Phase2, Phase3, and Phase4; write its Stage A-D handoff JSON to resultPath.",
            "Do not generate a per-query HTML report. Phase5 is an outer batch step: retry failed queries with fresh tasks first, then omit only queries abandoned after the batch attempt limit.",
            "Run completionCommand. Only its completed receipt is a successful delivery.",
        ],
    }
    write_once(task_path, task)
    return {
        "protocol": protocol,
        "runId": run_id,
        "taskPath": str(task_path),
        "resultPath": str(result_path),
        "completionCommand": task["completionCommand"],
    }


def command_prepare_dispatch(args: argparse.Namespace) -> int:
    """Build the same task-path-only dispatch envelope for every Harness.

    The CLI deliberately does not spawn an agent: Claude, Codex and Catpaw
    expose different process/agent APIs.  It does own the portable boundary so
    those adapters receive identical instructions and capability semantics.
    """
    try:
        task_path = args.task.resolve()
        task = read_json(task_path)
        if not isinstance(task, dict) or task.get("protocol") != TASK_PROTOCOL:
            raise ValueError("task_protocol_invalid")
        project_dir = Path(str(task.get("projectDir") or "")).resolve()
        try:
            task_path.relative_to(project_dir)
        except ValueError as exc:
            raise ValueError("task_path_outside_project") from exc
        required = task.get("requiredCapabilities")
        if not isinstance(required, dict) or not required:
            raise ValueError("task_required_capabilities_missing")
        required_names = {str(name) for name, value in required.items() if value is True}
        declared = {str(name) for name in args.capability}
        unknown = sorted(declared - set(required))
        if unknown:
            raise ValueError(f"unknown_host_capabilities:{','.join(unknown)}")
        missing = sorted(required_names - declared) if declared else sorted(required_names)
        if not declared:
            status = "awaiting_capability_confirmation"
        elif missing:
            status = "blocked_preflight"
        else:
            status = "ready_for_dispatch"
        claude_definition = project_dir / ".claude/agents/evaluation-agent.md"
        binding = {
            "mode": "native_agent_definition" if args.host == "claude" else "portable_task",
            "agentType": "evaluation-agent",
            "definitionFile": str(claude_definition) if args.host == "claude" else "",
        }
        payload = {
            "ok": status != "blocked_preflight",
            "protocol": DISPATCH_PROTOCOL,
            "host": args.host,
            "status": status,
            "agentRole": "evaluation-agent",
            "taskPath": str(task_path),
            "input": {"mode": "task_path_only", "value": str(task_path)},
            "prompt": f"你是 Evaluation Agent。唯一输入是 MEITUAN_EVAL_TASK taskPath：\n{task_path}",
            "requiredCapabilities": required,
            "declaredCapabilities": sorted(declared),
            "missingCapabilities": missing,
            "binding": binding,
            "resultPath": str(task.get("resultPath") or ""),
            "completionCommand": task.get("completionCommand", []),
        }
        return emit(payload, 2 if status == "blocked_preflight" else 0)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "protocol": DISPATCH_PROTOCOL, "host": args.host, "error": str(exc)}, 2)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Publish a mutable controller pointer without exposing a partial JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def batch_state_root(project_dir: Path, batch_id: str) -> Path:
    return project_dir / "runs" / "batches" / batch_id


def read_batch_state(path: Path) -> dict[str, Any]:
    state = read_json(path.resolve())
    if not isinstance(state, dict) or state.get("protocol") != BATCH_PROTOCOL:
        raise ValueError("batch_state_protocol_invalid")
    queries = state.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("batch_state_queries_missing")
    return state


def validate_batch_attempt_chains(state: dict[str, Any]) -> None:
    """Reject forged abandonment or retry histories that reused a task/run."""
    max_attempts = state.get("maxQueryAttempts")
    if max_attempts != 3:
        raise ValueError("batch_state_attempt_limit_invalid")
    batch_id = str(state.get("batchId") or "")
    project_dir = Path(str(state.get("projectDir") or "")).resolve()
    seen_queries: set[str] = set()
    seen_runs: set[str] = set()
    seen_tasks: set[str] = set()
    for entry in state["queries"]:
        if not isinstance(entry, dict):
            raise ValueError("batch_query_entry_invalid")
        query = str(entry.get("query") or "").strip()
        if not query or query in seen_queries:
            raise ValueError(f"batch_query_duplicate:{query}")
        seen_queries.add(query)
        attempts = entry.get("attempts")
        if not isinstance(attempts, list) or not attempts or len(attempts) > max_attempts:
            raise ValueError(f"batch_query_attempts_invalid:{query}")
        previous_run = ""
        for index, attempt in enumerate(attempts, 1):
            if not isinstance(attempt, dict) or attempt.get("attempt") != index:
                raise ValueError(f"batch_attempt_sequence_invalid:{query}:{index}")
            run_id = str(attempt.get("runId") or "")
            task_path = str(Path(str(attempt.get("taskPath") or "")).resolve())
            if not valid_run_id(run_id) or run_id in seen_runs or task_path in seen_tasks:
                raise ValueError(f"batch_attempt_not_isolated:{query}:{index}")
            seen_runs.add(run_id)
            seen_tasks.add(task_path)
            task = read_json(Path(task_path))
            if not isinstance(task, dict) or task.get("runId") != run_id:
                raise ValueError(f"batch_attempt_task_mismatch:{query}:{index}")
            workflow_args = task.get("workflowArgs")
            if (not isinstance(workflow_args, dict) or workflow_args.get("query") != query or
                    workflow_args.get("batchId") != batch_id or Path(str(task.get("projectDir") or "")).resolve() != project_dir):
                raise ValueError(f"batch_attempt_scope_mismatch:{query}:{index}")
            if index > 1 and (task.get("batchAttempt") != index or task.get("retryOf") != previous_run):
                raise ValueError(f"batch_retry_chain_invalid:{query}:{index}")
            previous_run = run_id
        if entry.get("status") == "abandoned" and len(attempts) != max_attempts:
            raise ValueError(f"batch_query_abandoned_before_attempt_limit:{query}")


def publish_batch_snapshot(state: dict[str, Any], state_root: Path) -> Path:
    """Keep every controller transition and update a small latest-state pointer."""
    sequence = int(state.get("sequence", 0)) + 1
    state = {**state, "sequence": sequence}
    snapshot = state_root / f"state-{sequence:03d}.json"
    write_once(snapshot, state)
    atomic_write_json(state_root / "latest.json", {
        "protocol": BATCH_PROTOCOL,
        "batchId": state["batchId"],
        "sequence": sequence,
        "statePath": str(snapshot),
    })
    return snapshot


def task_batch_entry(task_path: Path, project_dir: Path, batch_id: str, attempt: int) -> dict[str, Any]:
    task_path = task_path.resolve()
    task = read_json(task_path)
    if not isinstance(task, dict) or task.get("protocol") != TASK_PROTOCOL:
        raise ValueError(f"batch_task_protocol_invalid:{task_path}")
    if Path(str(task.get("projectDir", ""))).resolve() != project_dir:
        raise ValueError(f"batch_task_project_mismatch:{task_path}")
    workflow_args = task.get("workflowArgs")
    if not isinstance(workflow_args, dict) or workflow_args.get("batchId") != batch_id:
        raise ValueError(f"batch_task_batch_id_mismatch:{task_path}")
    query = str(workflow_args.get("query") or "").strip()
    if not query:
        raise ValueError(f"batch_task_query_missing:{task_path}")
    return {
        "attempt": attempt,
        "runId": str(task.get("runId") or ""),
        "taskPath": str(task_path),
        "receiptPath": str(task_path.parent / "receipt.json"),
        "status": "pending",
        "blockedAt": "",
        "error": "",
    }


def clone_retry_task(source_task_path: Path, new_run_id: str, attempt: int) -> dict[str, Any]:
    source_task_path = source_task_path.resolve()
    task = read_json(source_task_path)
    if not isinstance(task, dict) or task.get("protocol") != TASK_PROTOCOL:
        raise ValueError("retry_source_task_protocol_invalid")
    project_dir = Path(str(task.get("projectDir", ""))).resolve()
    workflow_args = task.get("workflowArgs")
    if not isinstance(workflow_args, dict):
        raise ValueError("retry_source_workflow_args_invalid")
    cloned_args = {
        key: value for key, value in workflow_args.items()
        if key not in {"evaluationScope", "phase2Outputs", "stagePaths"}
    }
    cloned_args.update({"runId": new_run_id, "tag": new_run_id, "rerunId": new_run_id})
    return portable_task(
        project_dir,
        cloned_args,
        new_run_id,
        source_task_path.parent.parent,
        batch_attempt=attempt,
        retry_of=str(task.get("runId") or ""),
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def project_file(value: Any, project_dir: Path, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}:missing_path")
    path = Path(value).resolve()
    try:
        path.relative_to(project_dir)
    except ValueError as exc:
        raise ValueError(f"{label}:outside_project:{path}") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"{label}:missing_or_empty:{path}")
    return str(path)


def valid_audit(value: Any, project_dir: Path, label: str) -> str:
    path = Path(project_file(value, project_dir, label))
    try:
        audit = read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}:invalid_json:{path}") from exc
    if not isinstance(audit, dict) or audit.get("valid") is not True:
        raise ValueError(f"{label}:valid_not_true:{path}")
    return str(path)


def nonempty_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}:missing_or_empty")
    return value


def validate_retry_history(stage_a: dict[str, Any], expected: dict[str, Any], project_dir: Path,
                           require_exhausted: bool) -> None:
    """Make each Phase2 failure an executable rework obligation.

    A retry plan is not passive evidence.  Every plan before the last must
    require retry, and its next attempt must be present in the same final
    history.  A successful run can only end with an error-free final plan;
    a Stage-A block can only end after the configured budget is exhausted.
    """
    budget = int(expected.get("phase2MaxAttempts", 3))
    attempts = stage_a.get("phase2Attempts")
    raw_plans = stage_a.get("retryPlans")
    if not isinstance(attempts, int) or attempts < 1 or attempts > budget:
        raise ValueError("stageA_retry_attempt_count_invalid")
    if require_exhausted and attempts != budget:
        raise ValueError("stageA_block_requires_exhausted_retry_plans")
    if not isinstance(raw_plans, list) or len(raw_plans) != attempts:
        raise ValueError("stageA_retry_history_missing_or_incomplete")
    plans: list[dict[str, Any]] = []
    for index, value in enumerate(raw_plans, 1):
        if isinstance(value, str):
            path = project_file(value, project_dir, f"stageA.retryPlans[{index}]")
            try:
                value = read_json(Path(path))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"retry_plan_invalid_json:{path}") from exc
        if not isinstance(value, dict) or value.get("contract") != "phase2.retry-plan":
            raise ValueError("stageA_retry_plan_contract_invalid")
        if value.get("attempt") != index or value.get("maxAttempts") != budget:
            raise ValueError("stageA_retry_plan_sequence_invalid")
        if not isinstance(value.get("errors"), list) or not isinstance(value.get("retryRequired"), bool):
            raise ValueError("stageA_retry_plan_fields_invalid")
        plans.append(value)
    if any(plan["retryRequired"] is not True for plan in plans[:-1]):
        raise ValueError("retry_required_plan_was_not_followed")
    final = plans[-1]
    if final["retryRequired"] is True:
        raise ValueError("retry_required_plan_was_not_followed")
    if not require_exhausted and final["errors"]:
        raise ValueError("success_cannot_end_with_phase2_errors")


def validate_completed_result(task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    project_dir = Path(str(task["projectDir"])).resolve()
    expected = task["workflowArgs"]
    protocol = task.get("protocol")
    if result.get("ok") is not True:
        blocked_at = result.get("blockedAt")
        allowed_blocked_stages = ("preflight",) + STAGES[:3]
        if blocked_at not in allowed_blocked_stages or not isinstance(result.get("error"), str) or not result["error"].strip():
            raise ValueError("blocked_result_missing_stage_or_error")
        if protocol == TASK_PROTOCOL and blocked_at == "stageA":
            stage_a = result.get("stageA")
            if not isinstance(stage_a, dict):
                raise ValueError("stageA_block_requires_exhausted_retry_plans")
            validate_retry_history(stage_a, expected, project_dir, require_exhausted=True)
        return {"status": "blocked", "blockedAt": blocked_at, "error": result["error"]}
    if result.get("query") != expected.get("query"):
        raise ValueError("result_query_mismatch")

    stage_a = result.get("stageA")
    stage_b = result.get("stageB")
    stage_c = result.get("stageC")
    stage_d = result.get("stageD")
    if not all(isinstance(stage, dict) for stage in (stage_a, stage_b, stage_c, stage_d)):
        raise ValueError("successful_result_missing_stage")
    if protocol == TASK_PROTOCOL:
        validate_retry_history(stage_a, expected, project_dir, require_exhausted=False)

    manifests = nonempty_list(stage_a.get("elementListPaths"), "stageA.elementListPaths")
    audits = nonempty_list(stage_a.get("elementAuditPaths"), "stageA.elementAuditPaths")
    if len(manifests) != len(audits):
        raise ValueError("stageA.manifest_audit_count_mismatch")
    manifest_paths = [project_file(value, project_dir, "stageA.manifest") for value in manifests]
    audit_paths = [valid_audit(value, project_dir, "stageA.audit") for value in audits]
    eval_result = project_file(stage_b.get("evalResultFile"), project_dir, "stageB.evalResultFile")
    eval_audit = valid_audit(stage_b.get("evalAuditFile"), project_dir, "stageB.evalAuditFile")
    measurements_index = project_file(stage_b.get("measurementsIndex"), project_dir, "stageB.measurementsIndex")
    eval_payload = read_json(Path(eval_result))
    if not isinstance(eval_payload, list):
        raise ValueError("stageB.evalResultFile:must_be_array")
    expected_targets = [
        (str(item.get("dimension") or ""), str(item.get("skill") or ""))
        for item in task.get("evalTargets", [])
        if isinstance(item, dict)
    ]
    actual_targets = [
        (str(item.get("dimension") or ""), str(item.get("skill") or ""))
        for item in eval_payload
        if isinstance(item, dict)
    ]
    if len(actual_targets) != len(expected_targets) or len(set(actual_targets)) != len(actual_targets):
        raise ValueError("stageB.evalResultFile:target_count_or_duplicates_invalid")
    if set(actual_targets) != set(expected_targets):
        raise ValueError("stageB.evalResultFile:targets_must_match_task")
    if stage_b.get("evalCount") != len(expected_targets):
        raise ValueError("stageB.evalCount_must_match_task")
    measurement_payload = read_json(Path(measurements_index))
    if not isinstance(measurement_payload, dict) or measurement_payload.get("valid") is not True:
        raise ValueError("stageB.measurementsIndex:valid_not_true")
    expected_phase2 = expected.get("phase2Outputs", [])
    expected_stage_paths = expected.get("stagePaths", {})
    if len(expected_phase2) != len(manifest_paths):
        raise ValueError("stageA.manifest_count_mismatch_task")
    if manifest_paths != [str(Path(item["manifest"]).resolve()) for item in expected_phase2]:
        raise ValueError("stageA.manifest_path_mismatch_task")
    if audit_paths != [str(Path(item["audit"]).resolve()) for item in expected_phase2]:
        raise ValueError("stageA.audit_path_mismatch_task")
    if eval_result != str(Path(str(expected_stage_paths.get("evalResultFile", ""))).resolve()):
        raise ValueError("stageB.eval_result_path_mismatch_task")
    if eval_audit != str(Path(str(expected_stage_paths.get("evalAuditFile", ""))).resolve()):
        raise ValueError("stageB.eval_audit_path_mismatch_task")
    expected_measurements = Path(str(expected_stage_paths.get("measurementsDir", ""))).resolve() / "phase3-measurements.json"
    if Path(measurements_index).resolve() != expected_measurements:
        raise ValueError("stageB.measurements_path_mismatch_task")
    evidence = stage_c.get("evidenceImages")
    if not isinstance(evidence, list):
        raise ValueError("stageC.evidenceImages:not_a_list")
    evidence_paths = [project_file(value, project_dir, "stageC.evidenceImage") for value in evidence]
    if len(set(evidence_paths)) != len(evidence_paths):
        raise ValueError("stageC.evidenceImages:duplicates_not_allowed")
    expected_screenshots = {
        str(Path(str(item.get("screenshot") or "")).resolve())
        for item in expected_phase2
        if isinstance(item, dict) and item.get("screenshot")
    }
    issue_evidence: set[str] = set()
    for result in eval_payload:
        if not isinstance(result, dict):
            continue
        for unit in result.get("units", []):
            if not isinstance(unit, dict):
                continue
            details = unit.get("details") if isinstance(unit.get("details"), dict) else {}
            original = str(Path(str(details.get("screenshot") or "")).resolve()) if details.get("screenshot") else ""
            for issue in details.get("issues") or []:
                if not isinstance(issue, dict) or issue.get("rating") not in {"达标", "不达标", "🟡", "🔴"}:
                    continue
                reference = project_file(issue.get("evidenceImage"), project_dir, "issue.evidenceImage")
                if reference != original or reference not in expected_screenshots:
                    raise ValueError(f"stageC.issue_evidence_must_equal_task_screenshot:{reference}")
                issue_evidence.add(reference)
    if set(evidence_paths) != issue_evidence:
        raise ValueError("stageC.evidenceImages:must_match_problem_issue_original_screenshots")
    artifacts = {
        "manifests": manifest_paths,
        "manifestAudits": audit_paths,
        "evalResult": eval_result,
        "evalAudit": eval_audit,
        "measurementsIndex": measurements_index,
        "evidenceImages": evidence_paths,
    }
    if protocol != TASK_PROTOCOL:
        raise ValueError("task_protocol_invalid")
    if stage_d:
        raise ValueError("stageD:must_be_empty_for_batch_handoff")
    return {
        "status": "completed",
        "artifacts": artifacts,
    }


def command_discover(args: argparse.Namespace) -> int:
    return emit(DISCOVERY.discover(args.screenshot_dir, args.min_bytes))


def command_copy(args: argparse.Namespace) -> int:
    result = COPY.ingest(
        args.source_dir,
        args.screenshot_dir,
        dry_run=args.dry_run,
    )
    return emit(result, 0 if not result["error"] else 2)


def command_prepare(args: argparse.Namespace) -> int:
    screenshot_dir = args.screenshot_dir or args.project_dir / "screenshots"
    copied = COPY.ingest(
        args.source_dir,
        screenshot_dir,
        dry_run=args.dry_run,
    )
    discovery = DISCOVERY.discover(screenshot_dir, args.min_bytes)
    payload: dict[str, Any] = {
        "protocol": HANDOFF_PROTOCOL,
        "projectDir": str(args.project_dir.resolve()),
        "copy": copied,
        "discovery": discovery,
        "status": "copy_blocked" if copied["error"] else "awaiting_screenshot_selection",
    }
    try:
        evaluation_selection = parse_evaluation_selection(args.evaluation_selection)
    except (TypeError, json.JSONDecodeError, ValueError) as exc:
        return emit({**payload, "status": "invalid_evaluation_selection", "error": str(exc)}, 2)
    if evaluation_selection is None or not args.report_outlet:
        payload.update({
            "status": "awaiting_evaluation_config",
            "requiredConfig": {
                "evaluationSelection": "full_19, dimensions, or custom_skills",
                "reportOutlet": ["none", "local_html", "nocode"],
            },
        })
        return emit(payload)
    if args.phase2_max_attempts < 1 or args.phase2_max_attempts > 10:
        return emit({**payload, "status": "invalid_phase2_attempt_budget", "error": "phase2_max_attempts_must_be_1_to_10"}, 2)
    copied_paths = {
        item.get("destinationPath")
        for item in copied.get("copied", []) + copied.get("alreadyPresent", []) + copied.get("renamed", [])
        if isinstance(item, dict) and isinstance(item.get("destinationPath"), str)
    }
    identity_map: dict[str, Any] | None = None
    query = str(args.query or "").strip()
    if not copied["error"] and args.identity_map:
        try:
            identity_map = load_identity_map(args.identity_map, screenshot_dir, copied_paths)
            requested_identity_paths = {str(Path(value).resolve()) for value in args.selected_screenshot}
            considered_entries = [
                item for item in identity_map["entries"]
                if not requested_identity_paths or item["sourcePath"] in requested_identity_paths
            ]
            mapped_queries = sorted({item["query"] for item in considered_entries})
            if not query:
                if len(mapped_queries) != 1:
                    payload.update({
                        "status": "ready_for_query_task_split",
                        "identityMap": identity_map,
                        "queries": mapped_queries,
                        "error": "identity_map_contains_multiple_queries; create one task per query",
                    })
                    return emit(payload)
                query = mapped_queries[0]
            if query not in mapped_queries:
                raise ValueError(f"query_not_in_identity_map:{query}")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            return emit({**payload, "status": "invalid_identity_map", "error": str(exc)}, 2)
    if not copied["error"] and not query:
        unnamed = discovery.get("unlabeledGroups", [])
        if unnamed:
            payload.update({
                "status": "awaiting_visual_identity_resolution",
                "identityResolution": {
                    "contract": "screenshot.identity-map",
                    "candidatePaths": [group["files"][0] for group in unnamed],
                    "requiredFields": ["sourcePath", "sha256", "query", "tab", "screen", "identitySource", "confidence"],
                    "instruction": "宿主读取每张当前图片像素，生成 identitySource=current_pixels 的映射；文件名不构成阻断。多个 query 按映射拆成独立任务。",
                },
            })
        return emit(payload)
    if not copied["error"] and query:
        selection_mode = "canonical_group"
        if identity_map is not None:
            mapped_paths = [item["sourcePath"] for item in identity_map["entries"] if item["query"] == query]
            requested = [str(Path(value).resolve()) for value in args.selected_screenshot]
            if requested and not set(requested).issubset(mapped_paths):
                return emit({**payload, "status": "invalid_explicit_selection", "error": "selected_screenshot_not_in_identity_map_query"}, 2)
            selected_paths = requested or mapped_paths
            group = {
                "query": query,
                "instance": "visual_identity_map",
                "identitySource": "current_pixels",
                "files": selected_paths,
                "count": len(selected_paths),
            }
            selection_mode = "identity_map"
        elif args.selected_screenshot:
            selected_paths = [str(Path(value).resolve()) for value in args.selected_screenshot]
            if len(set(selected_paths)) != len(selected_paths):
                return emit({**payload, "status": "invalid_explicit_selection", "error": "selected_screenshot_duplicate"}, 2)
            try:
                screenshot_root = screenshot_dir.resolve()
                for selected in selected_paths:
                    path = Path(selected)
                    path.relative_to(screenshot_root)
                    if selected not in copied_paths:
                        raise ValueError(f"selected_screenshot_not_in_current_import:{selected}")
                    if not path.is_file():
                        raise ValueError(f"selected_screenshot_missing:{selected}")
                    issue = DISCOVERY.inspect_image(path, args.min_bytes)
                    if issue:
                        raise ValueError(f"selected_screenshot_invalid:{selected}:{issue}")
            except ValueError as exc:
                return emit({**payload, "status": "invalid_explicit_selection", "error": str(exc)}, 2)
            group = {
                "query": query,
                "instance": "explicit_selection",
                "identitySource": "user_confirmed",
                "files": selected_paths,
                "count": len(selected_paths),
            }
            selection_mode = "explicit_paths"
        else:
            group = next(
                (
                    item for item in discovery["groups"]
                    if item["query"] == query and copied_paths.intersection(item.get("files", []))
                ),
                None,
            )
        if group is None:
            payload["status"] = "query_not_found_after_copy"
        else:
            run_id = args.run_id or uuid.uuid4().hex
            if not valid_run_id(run_id):
                return emit({**payload, "status": "invalid_run_id", "error": "run_id_must_be_1_to_80_alnum_dot_underscore_dash"}, 2)
            if args.batch_id and not valid_run_id(args.batch_id):
                return emit({**payload, "status": "invalid_batch_id", "error": "batch_id_must_be_1_to_80_alnum_dot_underscore_dash"}, 2)
            project_dir = args.project_dir.resolve()
            selected_set = set(group["files"])
            task_identity_map = (
                {"contract": "screenshot.identity-map", "entries": [
                    item for item in identity_map["entries"]
                    if item["query"] == query and item["sourcePath"] in selected_set
                ]}
                if identity_map is not None
                else inline_identity_map(group["files"], query, group.get("identitySource", "filename"), group)
            )
            workflow_args = {
                "mode": "evaluate_only",
                "projectDir": str(project_dir),
                "pythonBin": sys.executable,
                "query": query,
                "selectedScreenshots": group["files"],
                "screenshotSelectionMode": selection_mode,
                "screenshotIdentityMap": task_identity_map,
                "dimensions": args.dimensions,
                "reportOutlet": args.report_outlet,
                "phase2Mode": "lightweight",
                "runId": run_id,
                "batchId": args.batch_id or run_id,
                "tag": run_id,
                "rerunId": run_id,
                "phase2MaxAttempts": args.phase2_max_attempts,
            }
            if evaluation_selection is not None:
                workflow_args["evaluationSelection"] = evaluation_selection
            payload["status"] = "ready_for_host_workflow"
            payload["workflowArgs"] = workflow_args
            if not args.dry_run:
                try:
                    payload["portableTask"] = portable_task(
                        project_dir,
                        workflow_args,
                        run_id,
                        (args.runs_dir or project_dir / "runs").resolve(),
                    )
                except ValueError as exc:
                    payload["status"] = "run_setup_failed"
                    payload["error"] = str(exc)
                    return emit(payload, 2)
    return emit(payload, 0 if not copied["error"] else 2)


def command_finalize(args: argparse.Namespace) -> int:
    try:
        task_path = args.task.resolve()
        result_path = args.result.resolve()
        task = read_json(task_path)
        if not isinstance(task, dict) or task.get("protocol") != TASK_PROTOCOL:
            raise ValueError("task_protocol_invalid")
        if result_path != Path(str(task.get("resultPath", ""))).resolve():
            raise ValueError("result_path_mismatch")
        result = read_json(result_path)
        if not isinstance(result, dict):
            raise ValueError("result_not_object")
        verified = validate_completed_result(task, result)
        receipt_path = task_path.parent / "receipt.json"
        receipt = {
            "protocol": task["protocol"],
            "runId": task["runId"],
            "query": task["workflowArgs"]["query"],
            "resultPath": str(result_path),
            **verified,
        }
        archive_blocked_receipt_for_completion(receipt_path, verified)
        write_once(receipt_path, receipt)
        return emit({"ok": True, "receiptPath": str(receipt_path), **receipt})
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "error": str(exc)}, 2)


def command_prepare_batch(args: argparse.Namespace) -> int:
    """Freeze the complete expected-query set before any batch dispatch."""
    try:
        project_dir = args.project_dir.resolve()
        if not valid_run_id(args.batch_id):
            raise ValueError("batch_id_must_be_1_to_80_alnum_dot_underscore_dash")
        if args.max_query_attempts != 3:
            raise ValueError("max_query_attempts_must_be_3")
        tabs = [value.strip() for value in args.expected_business_tabs.split(",") if value.strip()]
        if len(tabs) != len(set(tabs)):
            raise ValueError("expected_business_tabs_duplicate")
        if not args.task:
            raise ValueError("batch_requires_at_least_one_query_task")

        entries = []
        selected_screenshot_count = 0
        seen_queries: set[str] = set()
        for raw_task_path in args.task:
            task_path = raw_task_path.resolve()
            task = read_json(task_path)
            workflow_args = task.get("workflowArgs") if isinstance(task, dict) else None
            query = str(workflow_args.get("query") or "").strip() if isinstance(workflow_args, dict) else ""
            if not query or query in seen_queries:
                raise ValueError(f"batch_task_query_missing_or_duplicate:{query or task_path}")
            selected_screenshots = workflow_args.get("selectedScreenshots") if isinstance(workflow_args, dict) else None
            if not isinstance(selected_screenshots, list) or not selected_screenshots:
                raise ValueError(f"batch_task_selected_screenshots_missing:{query or task_path}")
            attempt = task_batch_entry(task_path, project_dir, args.batch_id, 1)
            seen_queries.add(query)
            screenshot_count = len(selected_screenshots)
            selected_screenshot_count += screenshot_count
            entries.append({"query": query, "screenshotCount": screenshot_count, "status": "pending", "attempts": [attempt]})

        subagent_policy = {
            "trigger": "selected_screenshot_count_gt_3",
            "selectedScreenshotCount": selected_screenshot_count,
            "requiresQuerySubagents": selected_screenshot_count > 3,
            "singleQueryPerAgent": True,
            "maxParallelAgents": 3,
        }

        state_root = batch_state_root(project_dir, args.batch_id)
        if state_root.exists():
            raise ValueError(f"batch_state_already_exists:{state_root}")
        state_root.mkdir(parents=True)
        state = {
            "protocol": BATCH_PROTOCOL,
            "batchId": args.batch_id,
            "projectDir": str(project_dir),
            # This optional post-evaluation assertion never participates in
            # business attribution.  Phase5 derives its actual tab set from
            # accepted cards' visible semantics and fulfilment facts.
            "businessTabsAssertion": tabs,
            "maxQueryAttempts": args.max_query_attempts,
            "subagentPolicy": subagent_policy,
            "status": "pending",
            "sequence": 0,
            "queries": entries,
        }
        state_path = publish_batch_snapshot(state, state_root)
        return emit({
            "ok": True,
            "batchId": args.batch_id,
            "statePath": str(state_path),
            "status": "pending",
            "dispatchTasks": [entry["attempts"][-1]["taskPath"] for entry in entries],
            "subagentPolicy": subagent_policy,
        })
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "error": str(exc)}, 2)


def command_advance_batch(args: argparse.Namespace) -> int:
    """Reconcile receipts without charging work that has not returned one.

    ``prepare-batch`` freezes every planned query before hosts dispatch them in
    bounded waves.  Consequently the absence of a receipt says only that the
    attempt is still pending (and commonly has not been dispatched yet).  A
    retry is charged exclusively from a terminal non-completed receipt written
    by the query task itself.
    """
    try:
        source_path = args.state.resolve()
        state = read_batch_state(source_path)
        validate_batch_attempt_chains(state)
        project_dir = Path(str(state.get("projectDir", ""))).resolve()
        state_root = batch_state_root(project_dir, str(state.get("batchId") or ""))
        retry_queries: list[str] = []
        failed_queries: list[str] = []
        completed_queries: list[str] = []
        pending_queries: list[str] = []
        next_queries = []

        for raw_entry in state["queries"]:
            entry = dict(raw_entry)
            attempts = [dict(value) for value in entry.get("attempts", [])]
            if not attempts:
                raise ValueError(f"batch_query_attempts_missing:{entry.get('query', '')}")
            latest = attempts[-1]
            receipt_path = Path(str(latest.get("receiptPath") or "")).resolve()
            try:
                receipt = read_json(receipt_path)
            except (OSError, json.JSONDecodeError):
                receipt = None
            if isinstance(receipt, dict) and receipt.get("protocol") == TASK_PROTOCOL:
                receipt_status = str(receipt.get("status") or "failed")
                latest.update({
                    "status": receipt_status,
                    "blockedAt": str(receipt.get("blockedAt") or ""),
                    "error": str(receipt.get("error") or ""),
                })
            else:
                # A missing receipt is not a failed dispatch.  The batch may
                # contain many frozen tasks while only three are allowed to run
                # concurrently.  Leave this attempt pending so an early host
                # reconciliation cannot consume its isolated retry budget.
                latest.update({
                    "status": "pending",
                    "blockedAt": "",
                    "error": "",
                })
            attempts[-1] = latest
            entry["attempts"] = attempts
            if latest["status"] == "completed":
                entry["status"] = "completed"
                completed_queries.append(entry["query"])
            elif latest["status"] == "pending":
                entry["status"] = "pending"
                pending_queries.append(entry["query"])
            elif len(attempts) >= int(state["maxQueryAttempts"]):
                entry["status"] = "abandoned"
                failed_queries.append(entry["query"])
            else:
                entry["status"] = "retry_required"
                retry_queries.append(entry["query"])
            next_queries.append(entry)

        if pending_queries:
            status = "awaiting_receipts"
        elif retry_queries:
            status = "retry_required"
        elif failed_queries and completed_queries:
            status = "ready_for_partial_phase5"
        elif failed_queries:
            status = "failed"
        elif len(completed_queries) == len(next_queries):
            status = "ready_for_phase5"
        else:
            raise ValueError("batch_status_inconsistent")
        next_state = {**state, "status": status, "queries": next_queries}
        state_path = publish_batch_snapshot(next_state, state_root)
        return emit({
            "ok": status in {"ready_for_phase5", "ready_for_partial_phase5", "retry_required", "awaiting_receipts"},
            "batchId": state["batchId"],
            "statePath": str(state_path),
            "status": status,
            "completedQueries": completed_queries,
            "pendingQueries": pending_queries,
            "retryQueries": retry_queries,
            "failedQueries": failed_queries,
            "readyForPhase5": status in {"ready_for_phase5", "ready_for_partial_phase5"},
        }, 0 if status in {"ready_for_phase5", "ready_for_partial_phase5", "retry_required", "awaiting_receipts"} else 2)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "error": str(exc)}, 2)


def command_create_batch_retry(args: argparse.Namespace) -> int:
    """Create one fresh-run task for one failed query and preserve prior attempts."""
    try:
        state = read_batch_state(args.state.resolve())
        validate_batch_attempt_chains(state)
        project_dir = Path(str(state.get("projectDir", ""))).resolve()
        state_root = batch_state_root(project_dir, str(state.get("batchId") or ""))
        matching = [entry for entry in state["queries"] if entry.get("query") == args.query]
        if len(matching) != 1:
            raise ValueError(f"batch_retry_query_not_unique:{args.query}")
        target = matching[0]
        attempts = target.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            raise ValueError("batch_retry_attempt_history_missing")
        if target.get("status") not in {"retry_required", "blocked", "failed"}:
            raise ValueError(f"batch_retry_not_allowed_from_status:{target.get('status')}")
        if len(attempts) >= int(state["maxQueryAttempts"]):
            raise ValueError("batch_query_attempt_limit_reached")
        if not valid_run_id(args.run_id):
            raise ValueError("run_id_must_be_1_to_80_alnum_dot_underscore_dash")

        latest_task = Path(str(attempts[-1].get("taskPath") or "")).resolve()
        next_attempt = len(attempts) + 1
        portable = clone_retry_task(latest_task, args.run_id, next_attempt)
        retry_entry = task_batch_entry(Path(portable["taskPath"]), project_dir, state["batchId"], next_attempt)
        next_queries = []
        for raw_entry in state["queries"]:
            entry = dict(raw_entry)
            if entry.get("query") == args.query:
                entry["attempts"] = [*attempts, retry_entry]
                entry["status"] = "pending"
            next_queries.append(entry)
        next_state = {**state, "status": "pending", "queries": next_queries}
        state_path = publish_batch_snapshot(next_state, state_root)
        return emit({
            "ok": True,
            "batchId": state["batchId"],
            "query": args.query,
            "attempt": next_attempt,
            "taskPath": portable["taskPath"],
            "runId": portable["runId"],
            "statePath": str(state_path),
        })
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "error": str(exc)}, 2)


def command_finalize_batch(args: argparse.Namespace) -> int:
    """Render Phase5 after every query is completed or exhausted and abandoned."""
    try:
        project_dir = args.project_dir.resolve()
        if not valid_run_id(args.batch_id):
            raise ValueError("batch_id_must_be_1_to_80_alnum_dot_underscore_dash")
        task_paths = list(args.task or [])
        abandoned_queries: set[str] = set()
        expected_business_tabs = str(args.expected_business_tabs or "").strip()
        if args.batch_state:
            state = read_batch_state(args.batch_state.resolve())
            validate_batch_attempt_chains(state)
            if state.get("batchId") != args.batch_id:
                raise ValueError("batch_state_batch_id_mismatch")
            if Path(str(state.get("projectDir", ""))).resolve() != project_dir:
                raise ValueError("batch_state_project_mismatch")
            # Older state files froze guessed expectedBusinessTabs. Keep them
            # readable as an assertion, but new states use the neutral name
            # below and may intentionally contain no pre-evaluation guess.
            state_tabs = ",".join(state.get("businessTabsAssertion", state.get("expectedBusinessTabs", [])))
            if expected_business_tabs and state_tabs and expected_business_tabs != state_tabs:
                raise ValueError("batch_state_expected_business_tabs_mismatch")
            expected_business_tabs = state_tabs or expected_business_tabs
            task_paths = []
            for entry in state["queries"]:
                attempts = entry.get("attempts")
                if not isinstance(attempts, list) or not attempts:
                    raise ValueError(f"batch_query_attempts_missing:{entry.get('query', '')}")
                entry_status = str(entry.get("status") or "")
                if entry_status == "abandoned":
                    if len(attempts) < int(state.get("maxQueryAttempts", 3)):
                        raise ValueError(f"batch_query_abandoned_before_attempt_limit:{entry.get('query', '')}")
                    abandoned_queries.add(str(entry.get("query") or ""))
                elif entry_status != "completed":
                    raise ValueError(f"phase5_batch_not_terminal:{entry.get('query', '')}:{entry_status}")
                task_paths.append(Path(str(attempts[-1].get("taskPath") or "")))
        if not task_paths:
            raise ValueError("phase5_batch_requires_at_least_one_query_task")

        queries: list[str] = []
        manifests: list[str] = []
        eval_results: list[str] = []
        outlets: set[str] = set()
        scopes: set[str] = set()
        planned_queries: list[str] = []
        skipped_tasks: list[dict[str, str]] = []
        batch_artifact_dir = project_dir / ".artifacts" / "过程文件-评测结果与审计" / args.batch_id

        for raw_task_path in task_paths:
            task_path = raw_task_path.resolve()
            task = read_json(task_path)
            if not isinstance(task, dict) or task.get("protocol") != TASK_PROTOCOL:
                raise ValueError(f"batch_task_protocol_invalid:{task_path}")
            if Path(str(task.get("projectDir", ""))).resolve() != project_dir:
                raise ValueError(f"batch_task_project_mismatch:{task_path}")
            workflow_args = task.get("workflowArgs")
            if not isinstance(workflow_args, dict) or workflow_args.get("batchId") != args.batch_id:
                raise ValueError(f"batch_task_batch_id_mismatch:{task_path}")
            query = str(workflow_args.get("query") or "").strip()
            if not query or query in planned_queries:
                raise ValueError(f"batch_task_query_missing_or_duplicate:{query or task_path}")
            planned_queries.append(query)

            receipt_path = task_path.parent / "receipt.json"
            receipt = read_json(receipt_path)
            if not isinstance(receipt, dict) or receipt.get("protocol") != task.get("protocol"):
                skipped_tasks.append({"query": query, "status": "not_completed", "reason": "未找到合法完成回执"})
                continue
            if receipt.get("status") != "completed":
                skipped_tasks.append({
                    "query": query,
                    "status": str(receipt.get("status") or "not_completed"),
                    "reason": str(receipt.get("error") or receipt.get("blockedAt") or "词级任务未完成"),
                })
                continue
            result_path = Path(str(task.get("resultPath", ""))).resolve()
            if receipt.get("runId") != task.get("runId") or receipt.get("query") != query or Path(str(receipt.get("resultPath", ""))).resolve() != result_path:
                raise ValueError(f"batch_task_receipt_mismatch:{receipt_path}")
            result = read_json(result_path)
            if not isinstance(result, dict):
                raise ValueError(f"batch_task_result_not_object:{result_path}")
            verified = validate_completed_result(task, result)
            if verified.get("status") != "completed":
                raise ValueError(f"batch_task_not_completed:{task_path}")
            artifacts = verified["artifacts"]
            eval_result = Path(artifacts["evalResult"]).resolve()
            try:
                eval_result.relative_to(batch_artifact_dir.resolve())
            except ValueError as exc:
                raise ValueError(f"batch_eval_result_outside_batch:{eval_result}") from exc

            queries.append(query)
            manifests.extend(artifacts["manifests"])
            eval_results.append(str(eval_result))
            outlet = str(workflow_args.get("reportOutlet") or "").strip()
            if outlet not in {"none", "local_html", "nocode"}:
                raise ValueError(f"batch_report_outlet_invalid:{outlet or 'missing'}")
            outlets.add(outlet)
            scope = workflow_args.get("evaluationScope")
            if not isinstance(scope, dict):
                raise ValueError("batch_task_evaluation_scope_missing")
            scopes.add(json.dumps(scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

        skipped_query_names = {item["query"] for item in skipped_tasks}
        if skipped_tasks and (not args.batch_state or skipped_query_names != abandoned_queries):
            details = ";".join(
                f"{item['query']}:{item['status']}:{item['reason']}" for item in skipped_tasks
            )
            raise ValueError(f"phase5_batch_incomplete:{details}")
        if not queries:
            raise ValueError("phase5_batch_requires_completed_query_tasks")
        if len(outlets) != 1:
            raise ValueError("batch_report_outlet_mismatch")
        if len(scopes) != 1:
            raise ValueError("batch_report_evaluation_scope_mismatch")
        report_outlet = next(iter(outlets))
        if report_outlet == "none":
            return emit({
                "ok": True,
                "batchId": args.batch_id,
                "queries": queries,
                "plannedQueries": planned_queries,
                "skippedTasks": skipped_tasks,
                "reportPath": "",
                "datasetPath": "",
                "reportOutlet": "none",
                "phase5": {"skipped": True, "reason": "report_not_requested"},
            })

        report_dir = project_dir / "reports"
        report_path = args.output or report_dir / f"meituan_search_experience_dashboard_{args.batch_id}.html"
        dataset_path = args.dataset_output or report_dir / f".governance_dataset_{args.batch_id}.json"
        command = [
            sys.executable,
            str(project_dir / "phase5-report/scripts/build_experience_dashboard.py"),
            "--project-dir", str(project_dir),
            "--artifact-dir", str(batch_artifact_dir),
            "--batch-name", args.batch_id,
            "--output", str(report_path),
            "--dataset-output", str(dataset_path),
            "--evaluation-scope", next(iter(scopes)),
        ]
        if expected_business_tabs:
            command.extend(["--expected-business-tabs", expected_business_tabs])
        for query in queries:
            command.extend(["--expected-query", query])
        for manifest in manifests:
            command.extend(["--manifest", manifest])
        for eval_result in eval_results:
            command.extend(["--result", eval_result])

        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            raise ValueError(f"phase5_batch_failed:{completed.stderr.strip() or completed.stdout.strip()}")
        summary = json.loads(completed.stdout)
        report_file = project_file(str(report_path), project_dir, "batch.report")
        dataset_file = project_file(str(dataset_path), project_dir, "batch.dataset")
        return emit({
            "ok": True,
            "batchId": args.batch_id,
            "queries": queries,
            "plannedQueries": planned_queries,
            "skippedTasks": skipped_tasks,
            "reportPath": report_file,
            "datasetPath": dataset_file,
            "reportOutlet": report_outlet,
            "phase5": summary,
        })
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "batchId": args.batch_id, "error": str(exc)}, 2)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Portable preflight for Meituan search evaluation.")
    commands = root.add_subparsers(dest="command", required=True)

    discover = commands.add_parser("discover", help="Discover canonical project screenshots.")
    discover.add_argument("--screenshot-dir", required=True, type=Path)
    discover.add_argument("--min-bytes", type=int, default=5001)
    discover.set_defaults(handler=command_discover)

    copy = commands.add_parser("copy", aliases=["intake"], help="Copy external screenshots into the project without renaming them.")
    copy.add_argument("--source-dir", required=True, type=Path, help="External screenshot directory or a single screenshot file.")
    copy.add_argument("--screenshot-dir", required=True, type=Path)
    copy.add_argument("--dry-run", action="store_true")
    copy.set_defaults(handler=command_copy)

    prepare = commands.add_parser("prepare-evaluate", help="Copy, discover, and emit host Workflow arguments.")
    prepare.add_argument("--project-dir", default=PROJECT_DIR, type=Path)
    prepare.add_argument("--source-dir", required=True, type=Path, help="External screenshot directory or a single screenshot file.")
    prepare.add_argument("--screenshot-dir", type=Path)
    prepare.add_argument("--query", default="")
    prepare.add_argument(
        "--selected-screenshot",
        action="append",
        default=[],
        help="Repeat for each imported project screenshot to evaluate without relying on its filename. Requires --query; paths must be part of this import.",
    )
    prepare.add_argument(
        "--identity-map",
        type=Path,
        help="Host-produced current-pixel screenshot identity map. It may supply query for unnamed files and is verified against current imported bytes.",
    )
    prepare.add_argument("--dimensions", nargs="+", default=["phase3-card_or_component-eval"])
    prepare.add_argument(
        "--evaluation-selection",
        default="",
        help='评测前确认的范围 JSON：{"mode":"full_19"}、{"mode":"dimensions","dimensions":[...]} 或 {"mode":"custom_skills","skills":[{"dimension":"...","skill":"..."}]}。',
    )
    prepare.add_argument(
        "--report-outlet", default="", choices=["none", "local_html", "nocode"],
        help="评测前经用户确认的报告出口：none 不生成报告；local_html 生成本地 HTML；nocode 在本地报告通过后导入 NoCode。",
    )
    prepare.add_argument("--min-bytes", type=int, default=5001)
    prepare.add_argument("--dry-run", action="store_true")
    prepare.add_argument("--run-id", default="", help="Unique portable run id; defaults to a generated id.")
    prepare.add_argument("--batch-id", default="", help="Shared batch id for multiple query tasks; defaults to the run id.")
    prepare.add_argument("--phase2-max-attempts", type=int, default=3,
                         help="Bounded Phase2 candidate/review/publish attempts per screenshot.")
    prepare.add_argument("--runs-dir", type=Path, help="Defaults to <project-dir>/runs.")
    prepare.set_defaults(handler=command_prepare)

    dispatch = commands.add_parser("prepare-dispatch", help="Emit one host-neutral task-path-only agent dispatch envelope.")
    dispatch.add_argument("--task", required=True, type=Path)
    dispatch.add_argument("--host", required=True, choices=SUPPORTED_HOSTS)
    dispatch.add_argument(
        "--capability", action="append", default=[],
        help="Repeat for each capability the current host actually provides. With none, the envelope awaits host confirmation.",
    )
    dispatch.set_defaults(handler=command_prepare_dispatch)

    finalize = commands.add_parser("finalize-evaluate", help="Verify a host result and write an immutable delivery receipt.")
    finalize.add_argument("--task", required=True, type=Path)
    finalize.add_argument("--result", required=True, type=Path)
    finalize.set_defaults(handler=command_finalize)

    prepare_batch = commands.add_parser("prepare-batch", help="Freeze all expected query tasks before batch dispatch.")
    prepare_batch.add_argument("--project-dir", default=PROJECT_DIR, type=Path)
    prepare_batch.add_argument("--batch-id", required=True)
    prepare_batch.add_argument("--task", required=True, action="append", type=Path, help="Repeat once per expected query.")
    prepare_batch.add_argument(
        "--expected-business-tabs", default="",
        help="可选的 Phase5 业务 Tab 事后断言；不参与当前截图商卡归属推导。",
    )
    prepare_batch.add_argument("--max-query-attempts", type=int, default=3)
    prepare_batch.set_defaults(handler=command_prepare_batch)

    advance_batch = commands.add_parser("advance-batch", help="Reconcile one completed dispatch wave from local receipts.")
    advance_batch.add_argument("--state", required=True, type=Path)
    advance_batch.set_defaults(handler=command_advance_batch)

    create_retry = commands.add_parser("create-batch-retry", help="Create a fresh isolated task for one failed query.")
    create_retry.add_argument("--state", required=True, type=Path)
    create_retry.add_argument("--query", required=True)
    create_retry.add_argument("--run-id", required=True)
    create_retry.set_defaults(handler=command_create_batch_retry)

    finalize_batch = commands.add_parser("finalize-batch", help="Verify completed query tasks and generate one Phase5 batch report.")
    finalize_batch.add_argument("--project-dir", default=PROJECT_DIR, type=Path)
    finalize_batch.add_argument("--batch-id", required=True)
    finalize_batch.add_argument("--task", action="append", type=Path, help="Repeat once per expected query task.")
    finalize_batch.add_argument("--batch-state", type=Path, help="Latest state snapshot; uses each query's latest task.")
    finalize_batch.add_argument(
        "--expected-business-tabs", default="",
        help="可选的 Phase5 业务 Tab 事后断言；不参与当前截图商卡归属推导。",
    )
    finalize_batch.add_argument("--output", type=Path)
    finalize_batch.add_argument("--dataset-output", type=Path)
    finalize_batch.set_defaults(handler=command_finalize_batch)
    return root


def main() -> int:
    args = parser().parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
