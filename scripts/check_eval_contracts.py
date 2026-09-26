#!/usr/bin/env python3
"""Read-only preflight for frozen Skill/validator compatibility.

This checks the selected contract snapshot before any screenshot processing.
It classifies changed contracts as system drift, never as bad Phase2 facts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REGISTRY = Path("phase3-evaluation/common/contracts/active_validation_contracts.v3.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_file(project_dir: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"contract_path_outside_project:{relative}")
    return project_dir / candidate


def audit_task(task: dict[str, Any], project_dir: Path) -> dict[str, Any]:
    """Return diagnostics without mutating the task, facts or old results."""
    errors: list[str] = []
    registry_path = _project_file(project_dir, str(REGISTRY))
    try:
        registry_bytes = registry_path.read_bytes()
        registry = json.loads(registry_bytes)
    except (OSError, ValueError) as exc:
        return {"valid": False, "category": "contract_drift", "errors": [f"registry_unreadable:{exc}"]}
    if registry.get("schemaVersion") != "phase3.active-validation-contracts.v3":
        errors.append("registry_schema_unsupported")
    snapshot = hashlib.sha256(registry_bytes).hexdigest()
    pinned = task.get("validationContractSnapshotSha256")
    if pinned and pinned != snapshot:
        errors.append("task_contract_snapshot_changed")
    phase2_snapshot = task.get("phase2PublicationSnapshot", {})
    if not isinstance(phase2_snapshot, dict):
        errors.append("task_phase2_publication_snapshot_invalid")
    else:
        for relative, expected_hash in phase2_snapshot.items():
            try:
                current_path = _project_file(project_dir, str(relative))
                if sha256(current_path) != expected_hash:
                    errors.append(f"phase2_publication_file_changed:{relative}")
            except (OSError, ValueError):
                errors.append(f"phase2_publication_file_unreadable:{relative}")
    validator_info = registry.get("validator", {})
    try:
        # Production tasks execute the project's validator. Minimal portable
        # protocol fixtures provide only linked Phase3 Skills, so they use
        # this CLI runtime's validator as the equivalent executable.
        project_validator = project_dir / "scripts" / str(validator_info["path"])
        if project_validator.is_file():
            validator_path = project_validator
        elif (project_dir / "phase3-evaluation").is_symlink():
            validator_path = Path(__file__).resolve().parent / str(validator_info["path"])
        else:
            raise FileNotFoundError(project_validator)
        if sha256(validator_path) != validator_info.get("sha256"):
            errors.append("validator_hash_changed")
    except (OSError, ValueError, KeyError):
        errors.append("validator_unreadable")
    registered = registry.get("skills", {})
    targets = task.get("evalTargets")
    if not isinstance(targets, list) or not targets:
        errors.append("task_eval_targets_missing")
        targets = []
    for target in targets:
        if not isinstance(target, dict):
            errors.append("task_eval_target_invalid")
            continue
        key = f"{target.get('dimension')}/{target.get('skill')}"
        entry = registered.get(key)
        if not isinstance(entry, dict):
            errors.append(f"skill_not_in_contract_snapshot:{key}")
            continue
        if target.get("skillPath") != entry.get("path"):
            errors.append(f"skill_path_changed:{key}")
            continue
        try:
            skill_path = _project_file(project_dir, entry["path"])
            content = skill_path.read_text(encoding="utf-8")
            if sha256(skill_path) != entry.get("sha256"):
                errors.append(f"skill_hash_changed:{key}")
            frontmatter = content.split("---", 2)[1]
            if "metadataVersion" in entry:
                version = re.search(r'^\s*version:\s*["\']?([^"\'\n]+)', frontmatter, re.MULTILINE)
                if not version or version.group(1).strip() != entry["metadataVersion"]:
                    errors.append(f"skill_version_changed:{key}")
            for marker in entry.get("requiredText", []):
                if marker not in content:
                    errors.append(f"skill_semantic_marker_missing:{key}:{marker}")
        except (OSError, ValueError, KeyError, IndexError):
            errors.append(f"skill_unreadable:{key}")
    return {
        "valid": not errors, "category": "contract_drift" if errors else "compatible",
        "registry": str(registry_path), "snapshotSha256": snapshot, "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check frozen Phase3 Skill/validator compatibility")
    parser.add_argument("--task", type=Path, required=True)
    args = parser.parse_args()
    try:
        task = json.loads(args.task.read_text(encoding="utf-8"))
        project_dir = Path(str(task["projectDir"])).resolve()
        result = audit_task(task, project_dir)
    except (OSError, ValueError, KeyError) as exc:
        result = {"valid": False, "category": "contract_drift", "errors": [f"task_unreadable:{exc}"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
