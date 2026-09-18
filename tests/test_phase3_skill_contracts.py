from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
PHASE3_DIR = PROJECT_DIR / "phase3-evaluation"
CATALOG = json.loads((PHASE3_DIR / "catalog.json").read_text(encoding="utf-8"))


class Phase3SkillContractsTest(unittest.TestCase):
    def test_all_nineteen_skills_have_a_fixed_review_flow(self) -> None:
        skills = sorted(PHASE3_DIR.glob("dimensions/*/skills/eval-*/SKILL.md"))
        self.assertEqual(len(skills), 19)
        expected_headings = [
            "## 你是谁",
            "## 触发场景",
            "## 评审契约（开工前必读）",
            "## 评审流程",
            "## 判定标准",
            "## 输出格式模板",
            "## Gotchas",
            "## 参考来源",
        ]
        for skill in skills:
            content = skill.read_text(encoding="utf-8")
            positions = []
            for heading in expected_headings:
                match = re.search(rf"^{re.escape(heading)}.*$", content, re.MULTILINE)
                self.assertIsNotNone(match, f"{skill}: missing {heading}")
                positions.append(match.start())
            self.assertEqual(positions, sorted(positions), skill)
            self.assertIn("assessmentRows", content, skill)
            self.assertIn("`description`", content, skill)
            self.assertIn("`recommendation`", content, skill)
            self.assertIn("**建议示例：**", content, skill)

    def test_leaf_review_flows_keep_only_executable_steps(self) -> None:
        skills = sorted(PHASE3_DIR.glob("dimensions/*/skills/eval-*/SKILL.md"))
        for skill in skills:
            content = skill.read_text(encoding="utf-8")
            flow = content.split("## 评审流程", 1)[1].split("## 判定标准", 1)[0]
            steps = re.findall(r"^### Step (\d+)：", flow, re.MULTILINE)
            expected = ["1", "2", "3", "4", "5"] if skill.parent.name == "eval-4-element-complexity" else ["1", "2", "3", "4"]
            self.assertEqual(steps, expected, skill)
            self.assertNotIn("固化专属计数、比较或测量结果", flow, skill)
            self.assertNotIn("### Step 6：输出报告", flow, skill)
            self.assertRegex(flow, r"### Step 1：.+")
            self.assertRegex(flow, r"### Step 4：.+")

    def test_review_coverage_contracts_match_runtime_requirements(self) -> None:
        page_contract = (PHASE3_DIR / "dimensions/page-framework/contract.md").read_text(encoding="utf-8")
        self.assertIn("每个结论恰一条（含优秀） | eval-3、eval-6、eval-7", page_contract)
        page_redundancy = (
            PHASE3_DIR / "dimensions/page-framework/skills/eval-7-info-redundancy/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("无论优秀或不达标都必须保留恰一条 `assessmentRows`", page_redundancy)

        card_contract = (PHASE3_DIR / "dimensions/card-component/contract.md").read_text(encoding="utf-8")
        self.assertIn("仅保留问题行 | eval-1、eval-6", card_contract)
        self.assertNotIn("eval-7（部分）", card_contract)

        for dimension in ("single-element", "card-component", "page-framework"):
            contract = (PHASE3_DIR / f"dimensions/{dimension}/contract.md").read_text(encoding="utf-8")
            self.assertIn("不复制原清单、不另建第二份全量账本", contract)

    def test_cross_dimension_ownership_and_pixel_permissions_are_explicit(self) -> None:
        entry = (PHASE3_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## 跨维度归属", entry)
        self.assertIn("同一可见事实只按其评测单位归入主要维度", entry)

        pipeline = (PROJECT_DIR / "workflow/contracts/phase234-query-pipeline.md").read_text(encoding="utf-8")
        self.assertIn("JSON 类 Skill 禁止回看截图补写结构化事实", pipeline)
        self.assertIn("一次共享视觉判断轮次", pipeline)
        self.assertNotIn("phase3.visual-review", pipeline)

        compliance = (
            PHASE3_DIR / "dimensions/single-element/skills/eval-3-element-compliance-scanner/SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("`fontSizeBucket` 不能冒充 pt", compliance)
        self.assertNotIn("截图先放大，读取当前元素", compliance)

    def test_each_dimension_contract_requires_common_phase3_knowledge(self) -> None:
        entry = PHASE3_DIR / "SKILL.md"
        index = PHASE3_DIR / "common" / "references" / "knowledge-index.md"
        self.assertTrue(entry.is_file())
        self.assertTrue(index.is_file())
        for item in CATALOG["dimensions"]:
            contract = PHASE3_DIR / item["contract"]
            content = contract.read_text()
            self.assertIn("Phase3", content, contract)
            self.assertIn("知识索引", content, contract)
            self.assertIn("固定流程", content, contract)

    def test_catalog_matches_exactly_nineteen_leaf_skills(self) -> None:
        declared = []
        for item in CATALOG["dimensions"]:
            skills_dir = PHASE3_DIR / item["skillsDir"]
            declared.extend((item["id"], skill) for skill in item["skills"])
            self.assertEqual(
                set(item["skills"]),
                {path.parent.name for path in skills_dir.glob("eval-*/SKILL.md")},
            )
        self.assertEqual(len(declared), 19)

    def test_info_comparability_defines_concrete_difference_dimensions(self) -> None:
        skill = PHASE3_DIR / "dimensions" / "page-framework" / "skills" / "eval-6-info-comparability" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        for term in (
            "格式口径",
            "位置锚点",
            "样式语义",
            "实质影响门槛",
            "实际数值不同",
            "not_material",
        ):
            self.assertIn(term, content, skill)

    def test_pipeline_project_script_references_exist(self) -> None:
        pipeline = PROJECT_DIR / "workflow/contracts/phase234-query-pipeline.md"
        content = pipeline.read_text(encoding="utf-8")
        project_relative = set(re.findall(r"\$\{projectDir\}/([^`\"'\s]+\.py)", content))
        shared_scripts = set(re.findall(r"(?<![\w/])(scripts/[A-Za-z0-9_./-]+\.py)", content))
        referenced = project_relative | shared_scripts
        self.assertTrue(referenced)
        missing = sorted(path for path in referenced if not (PROJECT_DIR / path).is_file())
        self.assertEqual(missing, [], f"pipeline references missing project scripts: {missing}")
        for obsolete in (
            "build_phase3_atomic_fact_pack.py",
            "validate_phase3_atomic_fact_pack.py",
            "prepare_phase3_skill_run.py",
            "route_phase3_validation_failure.py",
        ):
            self.assertNotIn(obsolete, content)

    def test_pipeline_declares_retry_and_deterministic_measurement_preparation(self) -> None:
        pipeline = PROJECT_DIR / "workflow/contracts/phase234-query-pipeline.md"
        content = pipeline.read_text(encoding="utf-8")
        self.assertIn("phase2MaxAttempts", content)
        self.assertIn("build_phase2_retry_plan.py", content)
        self.assertIn("prepare_phase3_measurements.py", content)
        self.assertTrue((PROJECT_DIR / "workflow/prepare_phase3_measurements.py").is_file())
        self.assertTrue((PROJECT_DIR / "phase3-evaluation/common/routing/phase3_measurement_requirements.json").is_file())

    def test_visual_skills_do_not_request_phase2_fields_or_extra_measurement_artifacts(self) -> None:
        requirements = json.loads(
            (PHASE3_DIR / "common/routing/phase3_measurement_requirements.json").read_text(encoding="utf-8")
        )["skills"]
        self.assertNotIn("eval-5-info-hierarchy", requirements)
        card_color = requirements["eval-3-color-logic"]
        page_color = requirements["eval-3-page-color-logic"]
        self.assertEqual(card_color["policy"], "required_deterministic_pixel_measurement")
        self.assertEqual(page_color["policy"], "required_deterministic_pixel_measurement")
        self.assertEqual(card_color["dependencyKey"], page_color["dependencyKey"])

        entry = (PHASE3_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("不生成中间视觉 JSON", entry)
        self.assertIn("每张截图只生成一份组件色彩产物", entry)


if __name__ == "__main__":
    unittest.main()
