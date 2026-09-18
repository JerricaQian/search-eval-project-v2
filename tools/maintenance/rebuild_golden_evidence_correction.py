#!/usr/bin/env python3
"""Rebuild Phase4 evidence from Atomic v3 golden-source screenshots.

This is a correction-only utility for a completed Golden-JSON-exemption batch:
it preserves every Phase3 rating and finding, but writes a new isolated batch
whose result ``details.screenshot`` and Phase4 red-box images are tied to the
publication-ready Atomic manifest's ``source.screenshot``.  Historical outputs
are never changed or deleted.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PHASE4_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "phase4-issue-evidence" / "scripts"
if str(PHASE4_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE4_SCRIPTS_DIR))

from generate_issue_evidence import main as generate_evidence


PROBLEM_RATINGS = {"达标", "不达标", "🟡", "🔴"}
PAGE_DIMENSION = "phase3-page_framework-eval"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def atomic_manifests(project: Path) -> dict[str, Path]:
    index = read_json(project / "phase2-card-annotation/golden-atomic-2.1/index.json")
    manifests: dict[str, Path] = {}
    for sample in index.get("samples", []):
        path = project / str(sample.get("manifest", ""))
        if not sample.get("valid") or not path.is_file():
            continue
        source = read_json(path).get("source") or {}
        query = str(source.get("query", ""))
        if query:
            manifests[query] = path
    return manifests


def result_candidates(query_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in ("eval_results_*.json", "eval-results*.json", "phase3-results.json"):
        for path in query_dir.rglob(pattern):
            lower = path.name.lower()
            if "audit" in lower or "target" in lower:
                continue
            try:
                if isinstance(read_json(path), list):
                    paths.append(path)
            except (OSError, json.JSONDecodeError):
                continue
    return paths


def select_result(query_dir: Path) -> Path:
    candidates = result_candidates(query_dir)
    if not candidates:
        raise ValueError(f"no EVAL_SCHEMA result found: {query_dir}")

    def rank(path: Path) -> tuple[int, int, int, float]:
        name = path.name.lower()
        return (
            int("phase4" in path.parts),
            int("with_evidence" in name or "all-results" in name),
            int("v2" in name or "v3" in name or "v4" in name),
            path.stat().st_mtime,
        )

    return max(candidates, key=rank)


def source_screenshot(project: Path, manifest_path: Path) -> Path:
    source = read_json(manifest_path).get("source") or {}
    screenshot = Path(str(source.get("screenshot", "")))
    if not screenshot.is_absolute():
        screenshot = project / screenshot
    screenshot = screenshot.resolve()
    if not screenshot.is_file():
        raise ValueError(f"golden source screenshot missing: {screenshot}")
    return screenshot


def fact_pack_for(query_dir: Path) -> Path:
    candidates = [
        *query_dir.rglob("atomic-facts*.json"),
        *query_dir.rglob("*.atomic-fact-pack.v1.json"),
    ]
    if not candidates:
        raise ValueError(f"fact pack missing: {query_dir}")
    # Phase3 adapters retain the compatibility ``coord`` field required by the
    # evaluator's single-element trace validator; prefer them over the raw
    # Atomic fact pack when both are retained for the same query.
    return max(candidates, key=lambda path: (int("adapter" in path.name or "adapted" in path.name), path.stat().st_mtime))


def prepare_results(results: list[dict[str, Any]], screenshot: Path) -> None:
    """Bind copied results to the atomic source and clear stale Phase4 fields."""
    for result in results:
        for unit in result.get("units", []):
            details = unit.get("details") or {}
            unit["details"] = details
            details["screenshot"] = str(screenshot)
            for issue in details.get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                issue.pop("evidenceImage", None)
                issue.pop("evidenceScope", None)
                issue.pop("evidenceTargetElementId", None)
                issue.pop("evidenceTargetCoord", None)


def prepare_fact_pack(fact_pack: dict[str, Any], manifest: Path, screenshot: Path) -> None:
    """Add the existing compatibility spelling expected by the validator.

    Atomic fact packs retain the source field name ``坐标``.  The result
    validator's legacy-compatible single-element trace additionally reads
    ``coord``.  Mirror the same coordinates in this derived correction copy;
    no source coordinate is inferred or changed.
    """
    for element in fact_pack.get("activeElements") or []:
        if isinstance(element, dict) and "coord" not in element and isinstance(element.get("坐标"), list):
            element["coord"] = element["坐标"]
    # Some retained v1 packs predate the source envelope.  Give the correction
    # batch an explicit Atomic provenance link so Phase5 can verify and load
    # the canonical cards rather than falling back to a runtime screenshot.
    source = fact_pack.get("source") if isinstance(fact_pack.get("source"), dict) else {}
    fact_pack["source"] = {**source, "manifest": str(manifest), "screenshot": str(screenshot)}


def reconcile_issue_coords(results: list[dict[str, Any]], fact_pack: dict[str, Any]) -> None:
    """Rebind retained issue IDs to their Atomic-confirmed coordinates.

    This only repairs a stale trace coordinate when the issue already names an
    Atomic element ID.  Ratings, issue counts, descriptions and all page-level
    conclusions are intentionally left untouched.
    """
    element_coords = {
        str(element.get("id")): element.get("coord", element.get("坐标"))
        for element in fact_pack.get("activeElements") or []
        if isinstance(element, dict)
    }
    for result in results:
        for unit in result.get("units", []):
            for issue in (unit.get("details") or {}).get("issues") or []:
                if not isinstance(issue, dict):
                    continue
                element_id = str(issue.get("elementId", ""))
                coord = element_coords.get(element_id)
                if isinstance(coord, list) and len(coord) == 4:
                    issue["coord"] = coord


def fill_page_source_evidence(results: list[dict[str, Any]], screenshot: Path) -> None:
    """Page conclusions without a confirmed region retain the original golden page."""
    for result in results:
        if result.get("dimension") != PAGE_DIMENSION:
            continue
        for unit in result.get("units", []):
            for issue in (unit.get("details") or {}).get("issues") or []:
                if isinstance(issue, dict) and str(issue.get("rating", "")) in PROBLEM_RATINGS and not issue.get("evidenceImage"):
                    issue["evidenceImage"] = str(screenshot)


def run_phase4(results: Path, manifest: Path) -> None:
    previous_argv = sys.argv
    try:
        sys.argv = [
            "generate_issue_evidence.py", "--results", str(results), "--manifest", str(manifest),
        ]
        code = generate_evidence()
    finally:
        sys.argv = previous_argv
    if code:
        raise RuntimeError(f"Phase4 evidence generator failed: {results}")


def validate(project: Path, fact_pack: Path, results: Path, audit: Path) -> None:
    command = [
        sys.executable, str(project / "scripts/validate_eval_results.py"),
        "--manifest-audit", str(fact_pack), "--results", str(results), "--audit", str(audit),
        "--require-evidence",
    ]
    completed = subprocess.run(command, cwd=project, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(f"Phase4 validation failed for {results}: {completed.stdout}{completed.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a golden-source Phase4 correction batch")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--input-artifact-dir", type=Path, required=True)
    parser.add_argument("--output-artifact-dir", type=Path, required=True)
    parser.add_argument("--output-evidence-dir", type=Path, help="Deprecated; Phase4 no longer writes image files")
    parser.add_argument("--queries", nargs="*", help="Optional query subset; defaults to available input queries")
    args = parser.parse_args()

    project = args.project_dir.resolve()
    input_dir = args.input_artifact_dir.resolve()
    output_dir = args.output_artifact_dir.resolve()
    manifests = atomic_manifests(project)
    wanted = args.queries or sorted(path.name for path in input_dir.iterdir() if path.is_dir())
    report: list[dict[str, str]] = []

    for query in wanted:
        if query not in manifests:
            raise ValueError(f"no atomic v3 manifest for query: {query}")
        source_query_dir = input_dir / query
        source_result = select_result(source_query_dir)
        source_fact_pack = fact_pack_for(source_query_dir)
        manifest = manifests[query]
        screenshot = source_screenshot(project, manifest)
        output_query_dir = output_dir / query
        output_results = output_query_dir / "phase4" / f"eval_results_{query}_黄金样本证据修正.json"
        output_fact_pack = output_query_dir / "phase3" / "atomic-facts.json"
        output_audit = output_query_dir / "phase4" / "eval_audit_黄金样本证据修正.json"
        output_fact_pack.parent.mkdir(parents=True, exist_ok=True)
        fact_pack = read_json(source_fact_pack)
        prepare_fact_pack(fact_pack, manifest, screenshot)
        write_json(output_fact_pack, fact_pack)
        results = read_json(source_result)
        prepare_results(results, screenshot)
        reconcile_issue_coords(results, fact_pack)
        write_json(output_results, results)
        run_phase4(output_results, manifest)
        corrected = read_json(output_results)
        fill_page_source_evidence(corrected, screenshot)
        write_json(output_results, corrected)
        validate(project, output_fact_pack, output_results, output_audit)
        report.append({
            "query": query, "sourceResult": str(source_result), "goldenManifest": str(manifest),
            "goldenScreenshot": str(screenshot), "results": str(output_results), "audit": str(output_audit),
        })

    receipt = output_dir / "golden-evidence-correction-receipt.json"
    write_json(receipt, {"valid": True, "queries": report, "count": len(report)})
    print(json.dumps({"valid": True, "count": len(report), "receipt": str(receipt)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
