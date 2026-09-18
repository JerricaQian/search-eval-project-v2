from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = (
    PROJECT_DIR / "phase3-evaluation" / "dimensions" / "card-component" / "skills"
    / "eval-3-color-logic" / "scripts" / "compute_component_color_families.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("component_color_families_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def element(element_id: str, coord: list[int], *, photo: bool = False, color_role: str | None = None) -> dict:
    visual = {"visualStatus": "confirmed"}
    if color_role:
        visual["colorRole"] = color_role
    return {
        "id": element_id,
        "coord": coord,
        "render": {"visibleStatus": "confirmed", "isPhoto": photo},
        "visual": visual,
    }


def painted_image(width: int, height: int, rectangles: list[tuple[list[int], tuple[int, int, int]]]) -> np.ndarray:
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    for (x, y, w, h), rgb in rectangles:
        image[y:y + h, x:x + w] = rgb
    return image


class ComponentColorFamiliesTest(unittest.TestCase):
    def test_component_uses_screenshot_pixels_and_deduplicates(self) -> None:
        module = load_module()
        coords = [[0, 0, 20, 20], [20, 0, 20, 20], [40, 0, 20, 20], [0, 20, 20, 20]]
        image = painted_image(80, 50, [
            (coords[0], (255, 0, 0)), (coords[1], (0, 0, 255)),
            (coords[2], (255, 255, 0)), (coords[3], (255, 0, 0)),
        ])
        facts = {"cards": [{"cardId": "C1", "regions": [{"elements": [
            element(f"E{index}", coord) for index, coord in enumerate(coords, start=1)
        ]}]}]}

        component = module.compute_components(facts, image)[0]

        self.assertEqual(component["colorFamilies"], ["红", "黄", "蓝"])
        self.assertEqual(component["evidenceSource"], "original_screenshot_pixels")
        self.assertEqual(component["rating"], "优秀")

    def test_component_thresholds_are_four_five_and_six_to_seven(self) -> None:
        module = load_module()
        self.assertEqual(module.component_rating(4), "优秀")
        self.assertEqual(module.component_rating(5), "达标")
        self.assertEqual(module.component_rating(6), "不达标")
        self.assertEqual(module.component_rating(7), "不达标")

    def test_neutral_and_photo_pixels_do_not_enter_component_families(self) -> None:
        module = load_module()
        coords = [[0, 0, 20, 20], [20, 0, 20, 20], [40, 0, 20, 20]]
        image = painted_image(60, 20, [
            (coords[0], (240, 240, 240)), (coords[1], (255, 0, 0)), (coords[2], (255, 0, 255)),
        ])
        facts = {"cards": [{"cardId": "C1", "regions": [{"elements": [
            element("E1", coords[0]), element("E2", coords[1], photo=True), element("E3", coords[2]),
        ]}]}]}

        component = module.compute_components(facts, image)[0]

        self.assertEqual(component["colorFamilies"], ["紫"])
        self.assertEqual(component["excludedElementIds"], ["E2"])

    def test_pixels_override_legacy_json_colour_role(self) -> None:
        module = load_module()
        coord = [0, 0, 20, 20]
        image = painted_image(20, 20, [(coord, (0, 0, 255))])
        facts = {"cards": [{"cardId": "C1", "regions": [{"elements": [
            element("E1", coord, color_role="red"),
        ]}]}]}

        component = module.compute_components(facts, image)[0]

        self.assertEqual(component["colorFamilies"], ["蓝"])

    def test_graphic_filters_are_excluded_even_when_legacy_data_exposes_them_as_cards(self) -> None:
        module = load_module()
        image = painted_image(40, 20, [([0, 0, 20, 20], (255, 0, 0)), ([20, 0, 20, 20], (0, 255, 0))])
        facts = {"cards": [
            {"cardId": "F1", "cardTypeCode": "business_image_filter", "regions": [{"elements": [
                element("F1-E1", [0, 0, 20, 20]),
            ]}]},
            {"cardId": "C1", "regions": [{"elements": [element("C1-E1", [20, 0, 20, 20])]}]},
        ]}

        components = module.compute_components(facts, image)

        self.assertEqual([component["componentId"] for component in components], ["C1"])
        self.assertEqual(components[0]["colorFamilies"], ["绿"])

    def test_page_only_measurement_preparation_uses_component_calculator_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "screen.png"
            Image.fromarray(painted_image(40, 20, [
                ([0, 0, 20, 20], (255, 0, 0)), ([20, 0, 20, 20], (0, 0, 255)),
            ])).save(screenshot)
            manifest = root / "elements.json"
            task = root / "task.json"
            out_dir = root / "measurements"
            manifest.write_text(json.dumps({
                "screenshot": str(screenshot),
                "recognition": {"phase3Ready": True, "wholePageGate": True},
                "cards": [{"cardId": "C1", "regions": [{"elements": [
                    element("E1", [0, 0, 20, 20]), element("E2", [20, 0, 20, 20]),
                ]}]}],
            }), encoding="utf-8")
            task.write_text(json.dumps({"evalTargets": [{"skill": "eval-3-page-color-logic"}]}), encoding="utf-8")
            completed = subprocess.run([
                sys.executable, str(PROJECT_DIR / "workflow" / "prepare_phase3_measurements.py"),
                "--task", str(task), "--manifest", str(manifest), "--output-dir", str(out_dir),
            ], cwd=PROJECT_DIR, check=False, capture_output=True, text=True)

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            prepared = json.loads((out_dir / "phase3-measurements.json").read_text(encoding="utf-8"))
            self.assertEqual(len(prepared["artifacts"]), 1)
            result = json.loads(Path(prepared["artifacts"][0]["artifactPath"]).read_text(encoding="utf-8"))
            self.assertEqual(result["contractVersion"], "component-color-families.v4")
            self.assertEqual(result["components"][0]["colorFamilies"], ["红", "蓝"])

    def test_component_and_page_targets_share_one_pixel_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            screenshot = root / "screen.png"
            Image.fromarray(painted_image(20, 20, [([0, 0, 20, 20], (255, 0, 0))])).save(screenshot)
            manifest = root / "elements.json"
            task = root / "task.json"
            out_dir = root / "measurements"
            manifest.write_text(json.dumps({
                "screenshot": str(screenshot),
                "recognition": {"phase3Ready": True, "wholePageGate": True},
                "cards": [{"cardId": "C1", "regions": [{"elements": [
                    element("E1", [0, 0, 20, 20]),
                ]}]}],
            }), encoding="utf-8")
            task.write_text(json.dumps({"evalTargets": [
                {"skill": "eval-3-color-logic"},
                {"skill": "eval-3-page-color-logic"},
            ]}), encoding="utf-8")

            completed = subprocess.run([
                sys.executable, str(PROJECT_DIR / "workflow" / "prepare_phase3_measurements.py"),
                "--task", str(task), "--manifest", str(manifest), "--output-dir", str(out_dir),
            ], cwd=PROJECT_DIR, check=False, capture_output=True, text=True)

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            prepared = json.loads((out_dir / "phase3-measurements.json").read_text(encoding="utf-8"))
            self.assertEqual(len(prepared["artifacts"]), 2)
            self.assertEqual(
                len({item["artifactPath"] for item in prepared["artifacts"]}),
                1,
            )


if __name__ == "__main__":
    unittest.main()
