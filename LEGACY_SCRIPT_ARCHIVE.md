# 已归档的历史脚本

以下脚本曾为固定截图、固定搜索词或固定结果 JSON 直接生成/修补结论。它们没有被当前入口、测试或文档引用，且会绕开 Phase2 → Phase5 的证据链，因此已从工作树删除；完整源码保留在 Git 历史中。

| 已删除脚本 | 替代路径 |
| --- | --- |
| `build_eval_results_安睡裤.py`、`rebuild_four_phase3_results.py`、`repair_phase3_from_phase2_findings.py`、`create_frozen_32_batch.py` | 按 Evaluation Agent 的 Phase2 → Phase5 流程重新评测，并运行 `scripts/validate_eval_results.py`。 |
| `build_watermelon_elements.py`、`rebuild_four_minimum_elements.py`、`rebuild_four_scenes.py`、`normalize_phase2_card_types.py`、`repair_phase2_manifest_findings.py` | 从截图重新运行 Phase2 识别与清单校验；不得脚本化写入固定元素事实。 |
| `gen_evidence_imgs.py` | 使用 `phase4-issue-evidence/scripts/generate_issue_evidence.py` 将当前问题绑定到对应 `screenshots/` 原图。 |
| `update_four_scene_report.py` | 由当前 Phase5 报告流程或 `phase5-report/scripts/build_experience_dashboard.py` 生成报告。 |

当前专项修复工具（包括未提交脚本）不在本次删除范围内；它们必须保持项目相对路径、显式输入输出，并不得成为默认评测入口。
