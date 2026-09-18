#!/usr/bin/env python3
"""Bind Phase3 problem issues to their original screenshots.

Phase4 is a reference-only stage. It never draws, crops, copies, or rewrites an
image. For every problem issue it records the exact original screenshot already
declared by the evaluation unit (or, for compatibility, its single manifest).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


PROBLEM_RATINGS = {"达标", "不达标", "🟡", "🔴"}
LEGACY_ANNOTATION_FIELDS = {
    "evidenceCrop",
    "evidenceScope",
    "evidenceTargetElementId",
    "evidenceTargetCoord",
}


def is_project_screenshot(path: Path) -> bool:
    """Return whether the resolved image lives below a ``screenshots`` dir."""
    return any(parent.name == "screenshots" for parent in path.parents)


def manifest_screenshot(path: Path | None) -> str:
    if not path or not path.is_file():
        return ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ""
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return str(payload.get("screenshot") or source.get("screenshot") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference original screenshots for Phase3 problem issues")
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Deprecated compatibility argument; Phase4 no longer writes image files.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional single-image Phase2 manifest used only as a screenshot-path fallback.",
    )
    args = parser.parse_args()

    results = json.loads(args.results.read_text(encoding="utf-8"))
    if not isinstance(results, list):
        raise ValueError("results must be a JSON array")

    fallback_screenshot = manifest_screenshot(args.manifest)
    referenced: list[str] = []
    seen: set[str] = set()
    skipped: list[dict[str, str]] = []

    for result in results:
        if not isinstance(result, dict):
            continue
        skill = str(result.get("skill", "skill"))
        for unit in result.get("units", []):
            if not isinstance(unit, dict):
                continue
            details = unit.get("details")
            if not isinstance(details, dict):
                continue
            screenshot = str(details.get("screenshot") or fallback_screenshot)
            resolved = Path(screenshot).resolve() if screenshot else None
            if not details.get("screenshot") and resolved and resolved.is_file() and is_project_screenshot(resolved):
                details["screenshot"] = str(resolved)
            for issue in details.get("issues") or []:
                if not isinstance(issue, dict) or str(issue.get("rating", "")) not in PROBLEM_RATINGS:
                    continue
                issue_key = f"{skill}/{unit.get('tab', '')}/{issue.get('elementId', issue.get('component', 'page'))}"
                issue.pop("evidenceImage", None)
                for field in LEGACY_ANNOTATION_FIELDS:
                    issue.pop(field, None)
                if resolved is None or not resolved.is_file():
                    skipped.append({"issue": issue_key, "reason": "original_screenshot_missing"})
                    continue
                if not is_project_screenshot(resolved):
                    skipped.append({"issue": issue_key, "reason": "original_screenshot_outside_screenshots"})
                    continue
                issue["evidenceImage"] = str(resolved)
                if str(resolved) not in seen:
                    seen.add(str(resolved))
                    referenced.append(str(resolved))

    args.results.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "referenced": referenced,
        "skipped": skipped,
        "count": len(referenced),
        "mode": "original-screenshot-reference",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
