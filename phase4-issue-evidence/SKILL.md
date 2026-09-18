---
name: phase4-issue-evidence
description: 将 Phase3 已判定的问题直接绑定到对应 screenshots 原始截图，不生成红框图、裁剪图或其他派生图片；回写并校验原图引用，作为词级 Agent 交付给批次级 Phase5 与人工复核使用。
---

# Phase4 问题证据引用

## 定位

本阶段位于 Phase3 多维度评测之后，是词级 Evaluation Agent 的最后一个执行阶段。它不重新识别页面，不改变评级、分数、`overview.total`、坐标或问题计数；只把 Phase3 已判定的问题绑定到该评测单元已经声明的 `screenshots/` 原始截图。Phase4 不再绘制红框，也不创建、复制、裁剪或改写任何图片。

## 输入

- Phase3 最终评测结果：`.artifacts/过程文件-评测结果与审计/<batchId>/<query>/<tag>/results/评测原始结果_<query>[_<tag>]_<dimension>.json`。
- 原始截图：每个评测单元的 `details.screenshot`；仅为旧的单图结果兼容，缺失时可从对应 Phase2 manifest 的 `screenshot` 读取。
- Phase2 manifest 仅用于兼容取得原图路径，不再用于解析证据框或生成派生图片。

## 输出

- 每个 `rating ∈ {达标, 🟡, 不达标, 🔴}` 的问题写入 `evidenceImage`，其值必须与所属评测单元的 `details.screenshot` 解析后完全相同，并指向项目 `screenshots/` 下实际存在的原图。
- `stageC.evidenceImages` 返回所有被问题实际引用的原图绝对路径，按首次出现去重；没有问题时为空数组。
- 新结果不写 `evidenceScope`、`evidenceTargetElementId`、`evidenceTargetCoord` 或 `evidenceCrop`。
- 不写 `screenshots-out/evidence/`，不删除该目录中的历史证据图，也不改写任何原始截图。

## 事实源、校验与修复边界（阻断）

- **Phase2 是结构事实源，原图是证据资源：**如果 Phase3/4 暴露元素遗漏、卡片边界、业务归属或事实字段错误，必须回到 Phase2 修正 manifest 并重跑受影响阶段。Phase4 不能改评级、问题、坐标或结构事实。
- **校验器是闸门：**本阶段只消费已通过 `validate_eval_results.py` 的 Phase3 结果；完成后必须用 `--require-evidence` 复验。校验器确认每个问题的 `evidenceImage` 与所属 `details.screenshot` 相同、文件存在且位于 `screenshots/`。
- **不得伪造证据：**原图缺失、路径不一致或位于 `screenshots/` 外时，必须阻断并修复任务输入，不得改用旧红框图、Phase2 标注图、其他截图或临时复制品。
- **历史产物只读保留：**既有 `screenshots-out/evidence/` 和历史红框文件不删除、不覆盖，也不作为新 Phase4 的输出或回退来源。

## 执行规则

1. 仅处理 `rating` 为 `达标` / `🟡` / `不达标` / `🔴` 且已通过 Phase3 校验的问题；优秀项和无问题项不需要证据引用。
2. 同一评测单元内的所有问题都引用该单元同一张 `details.screenshot` 原图。不同截图不得混用。
3. Phase4 不读取坐标来生成视觉标记；`elementId`、`component`、`coord` 和问题描述继续由 Phase3/Phase2 契约负责。
4. 脚本会清除当前问题项中遗留的红框专用字段，再写入原图 `evidenceImage`；这只修改结果 JSON，不删除字段曾指向的历史文件。
5. 若 `评测结果校验_*.json` 中 `phase2ReviewRequired=true`，必须停止本阶段与报告阶段，先按正式流程完成 Phase2 复核并重跑 Phase3。
6. 执行后必须运行 `validate_eval_results.py --require-evidence`；任一问题未精确引用对应原图时不得交付 Phase5。

## 执行命令

```bash
python3 phase4-issue-evidence/scripts/generate_issue_evidence.py \
  --results <评测结果绝对路径> \
  --manifest <项目根>/screenshots-out/elements_<截图文件名>.json

python3 scripts/validate_eval_results.py \
  --manifest-audit <项目根>/screenshots-out/elements_<截图文件名>.audit.json \
  --results <评测结果绝对路径> \
  --audit <评测审计绝对路径> \
  --require-evidence
```

`--output-dir` 仅为旧调用兼容参数；即使传入也不会创建目录或写图片。
