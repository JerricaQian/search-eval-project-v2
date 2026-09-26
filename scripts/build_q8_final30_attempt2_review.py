#!/usr/bin/env python3
"""Create q8's bounded Phase2 retry overlay from attempt 1."""

import json
from pathlib import Path

ROOT = Path("/Users/qianjing/Documents/ChatGPT/search-eval-project-v2")
BASE = ROOT / ".artifacts/过程文件-评测结果与审计/batch-20260920-09-2-final30-r1/batch-20260920-09-2-final30-r1-q8/phase2/自体脂肪隆鼻_全部_1/attempts"
SOURCE = BASE / "attempt-1/visual-review.json"
OUTPUT = BASE / "attempt-2/visual-review.json"

review = json.loads(SOURCE.read_text(encoding="utf-8"))
overrides = []
for card in review["cards"]:
    changed = False
    fields = []
    for field in card["fields"]:
        updated = dict(field)
        if updated.get("role") == "sales" and str(updated.get("text", "")).startswith("消费"):
            updated["role"] = "other"
            changed = True
        if updated.get("colorRole") == "brown":
            updated["colorRole"] = "orange"
            changed = True
        fields.append(updated)
    if changed:
        overrides.append({"cardId": card["cardId"], "fields": fields})

patch = {
    "extends": "../attempt-1/visual-review.json",
    "screenshot": review["screenshot"],
    "completeCurrentPixelReview": True,
    "cardOverrides": overrides,
}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUTPUT)
