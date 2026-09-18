import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = str(ROOT / "phase2-card-annotation" / "scripts")
sys.path.insert(0, SCRIPTS)

import extract_cv_facts  # noqa: E402

sys.path.remove(SCRIPTS)


class CvLlmModeTests(unittest.TestCase):
    def test_extract_marks_cv_llm_ocr_as_disabled(self):
        previous = os.environ.get("PHASE2_DISABLE_LOCAL_OCR")
        os.environ["PHASE2_DISABLE_LOCAL_OCR"] = "1"
        try:
            facts = extract_cv_facts.extract(
                ROOT
                / "phase2-card-annotation"
                / "golden-samples"
                / "merchant-text-hang"
                / "component-level"
                / "商家卡片-文下挂-搜索词为漂流.png"
            )
        finally:
            if previous is None:
                os.environ.pop("PHASE2_DISABLE_LOCAL_OCR", None)
            else:
                os.environ["PHASE2_DISABLE_LOCAL_OCR"] = previous
        self.assertEqual(facts["backends"]["ocr"], "disabled_for_cv_llm")
        self.assertEqual(facts["candidates"]["text"], [])
