#!/usr/bin/env python3
"""Run deterministic Phase3 measurements required by the evaluation task.

This is deliberately separate from Phase2 publication: it rereads the bound
original screenshot only through a selected Skill's own script and writes an
immutable measurement artifact for that attempt.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "phase3-evaluation/common/routing/phase3_measurement_requirements.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--manifest", required=True, action="append", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    task = load(args.task)
    requirements = load(REQUIREMENTS)
    targets = {str(item.get("skill", "")) for item in task.get("evalTargets", []) if isinstance(item, dict)}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, str]] = []
    for manifest in args.manifest:
        payload = load(manifest)
        recognition = payload.get("recognition", {})
        if recognition.get("phase3Ready") is not True or recognition.get("wholePageGate") is not True:
            raise ValueError(f"manifest_not_phase3_ready:{manifest}")
        prepared_dependencies: dict[str, Path] = {}
        for skill in sorted(targets):
            requirement = requirements.get("skills", {}).get(skill, {})
            policy = requirement.get("policy")
            if policy not in {
                "required_deterministic_pixel_measurement",
                "required_deterministic_json_computation",
            }:
                continue
            dependency_key = str(requirement.get("dependencyKey") or skill)
            output = prepared_dependencies.get(dependency_key)
            if output is None:
                output = args.output_dir / f"{manifest.stem}.{dependency_key}.json"
                replacements = {
                    "<projectDir>": str(ROOT),
                    "<manifest>": str(manifest),
                    "<artifact>": str(output),
                    "<skill>": skill,
                }
                declared_arguments = requirement.get("arguments")
                if not isinstance(declared_arguments, list) or not all(
                    isinstance(value, str) for value in declared_arguments
                ):
                    raise ValueError(f"measurement_arguments_invalid:{skill}")
                command = [sys.executable, str(ROOT / requirement["script"])] + [
                    replacements.get(value, value) for value in declared_arguments
                ]
                completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
                if completed.returncode != 0:
                    raise ValueError(f"measurement_failed:{skill}:{completed.stderr.strip() or completed.stdout.strip()}")
                prepared_dependencies[dependency_key] = output
            measured = load(output)
            missing = [key for key in requirement.get("requiredOutput", []) if key not in measured]
            if missing:
                raise ValueError(f"measurement_output_missing:{skill}:{','.join(missing)}")
            artifacts.append({"skill": skill, "manifest": str(manifest.resolve()), "artifactPath": str(output.resolve())})
    result = {
        "contract": "phase3.measurements",
        "task": str(args.task.resolve()),
        "artifacts": artifacts,
        "valid": True,
    }
    output = args.output_dir / "phase3-measurements.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
