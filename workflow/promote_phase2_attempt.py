#!/usr/bin/env python3
"""Publish one validated Phase2 attempt to the task's immutable final paths."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"not_object:{path}")
    return payload


def copy_once(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"refuse_to_overwrite:{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-audit", required=True, type=Path)
    parser.add_argument("--recognition-audit", required=True, type=Path)
    parser.add_argument("--ownership-audit", required=True, type=Path)
    parser.add_argument("--visual-review", required=True, type=Path)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    parser.add_argument("--output-recognition-audit", required=True, type=Path)
    args = parser.parse_args()

    task = load(args.task)
    project_dir = Path(str(task.get("projectDir", ""))).resolve()
    publication_snapshot = task.get("phase2PublicationSnapshot")
    if not isinstance(publication_snapshot, dict) or not publication_snapshot:
        raise ValueError("phase2_publication_snapshot_missing")
    for relative, expected_hash in publication_snapshot.items():
        source = Path(str(relative))
        if source.is_absolute() or ".." in source.parts:
            raise ValueError(f"phase2_publication_snapshot_path_invalid:{relative}")
        current = project_dir / source
        if not current.is_file() or hashlib.sha256(current.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"phase2_publication_contract_drift:{relative}")

    screenshot = args.screenshot.resolve()
    manifest = load(args.manifest)
    manifest_audit = load(args.manifest_audit)
    recognition_audit = load(args.recognition_audit)
    ownership_audit = load(args.ownership_audit)
    if Path(str(manifest.get("screenshot", ""))).resolve() != screenshot:
        raise ValueError("manifest_screenshot_mismatch")
    if manifest.get("recognition", {}).get("phase3Ready") is not True or manifest.get("recognition", {}).get("wholePageGate") is not True:
        raise ValueError("manifest_not_phase3_ready")
    current_pixel_review_valid = (
        recognition_audit.get("contractVersion") == "phase2.current-image-calibration.v1"
        and recognition_audit.get("reviewedAgainstCurrentPixels") is True
    )
    ownership_valid = (
        ownership_audit.get("contractVersion") == "phase2.semantic-ownership.v2"
        and ownership_audit.get("valid") is True
        and not ownership_audit.get("errors")
        and Path(str(ownership_audit.get("screenshot", ""))).resolve() == screenshot
        and ownership_audit.get("screenshotSha256") == hashlib.sha256(screenshot.read_bytes()).hexdigest()
        and ownership_audit.get("manifestSha256") == hashlib.sha256(args.manifest.read_bytes()).hexdigest()
        and ownership_audit.get("reviewSha256") == hashlib.sha256(args.visual_review.read_bytes()).hexdigest()
    )
    if manifest_audit.get("valid") is not True or not current_pixel_review_valid or not ownership_valid:
        raise ValueError("attempt_audit_not_valid")

    publications = (
        (args.manifest, args.output_manifest),
        (args.manifest_audit, args.output_audit),
        (args.recognition_audit, args.output_recognition_audit),
    )
    existing = [str(destination) for _, destination in publications if destination.exists()]
    if existing:
        raise ValueError(f"refuse_to_overwrite:{','.join(existing)}")
    for source, destination in publications:
        copy_once(source, destination)
    print(json.dumps({
        "ok": True,
        "screenshot": str(screenshot),
        "manifest": str(args.output_manifest.resolve()),
        "audit": str(args.output_audit.resolve()),
        "recognitionAudit": str(args.output_recognition_audit.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
