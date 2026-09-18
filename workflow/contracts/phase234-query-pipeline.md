---
name: phase234-query-pipeline
description: 单搜索词 Phase2→Phase3→Phase4 最终流水线；统一卡型契约、有界纠错、按需确定性测量和问题证据交付。
---

# Evaluation Agent 契约

本文件只服务 `MEITUAN_EVAL_TASK`。任务 Agent 必须先完整读取 task JSON、全部 `contractFiles` 与 `requiredReads`。一个 Agent 只处理一个已经通过截图身份映射确定的 query，在同一执行中完成 Stage A→B→C，`stageD={}`，写入 `resultPath`，最后执行 `completionCommand`。

截图文件名不参与可评测性判断。`IMG_*.PNG` 等未命名但可读取的图片，只要 task 已提供不可变的 `screenshotIdentityMap` 与 `selectedScreenshots`，必须正常执行；不得要求改名。原图永不重命名或覆盖，规范名称只能作为评测成功后的独立副本或映射。

## 派发前能力预检

宿主必须逐项满足 task.requiredCapabilities：读取当前 PNG/JPEG 像素、读文件、运行本地脚本、写 JSON。不能读当前像素时，写 `ok=false`、`blockedAt="preflight"` 和明确错误；不得开始 Phase2，也不得以 OCR、黄金样本、搜索词或历史产物代替当前读图。

## Stage A：Phase2 候选、当前像素复核、发布与有界纠错

每个 `phase2Outputs[]` 与一张 screenshot 一一对应，不合并 manifest。每张图最多执行 `phase2MaxAttempts` 次；一次门禁失败是下一次修正义务，不是任务终止。每次尝试写入 `output.attemptRoot/attempt-<n>/`，保留 candidate、visual review、manifest、recognition audit、manifest audit 和 retry plan，不覆盖历史尝试。

### A1 候选（不读图、不发布）

```bash
"${pythonBin}" "${phase2SkillDir}/scripts/run_phase2_recognition.py" \
  --stage candidate --query "${query}" --screenshot "<output.screenshot>" \
  --output "<attempt.candidateBundle>" --artifacts-dir "<attempt.artifactsDir>"
```

候选 bundle 只含本地 CV 几何/图片候选和截图 SHA-256，固定 `phase3Ready=false`；它不是 manifest，不能交给 Phase3。

### A2 当前像素复核（必须读当前图）

首次尝试读取每张完整截图一次，再读 candidate bundle 与过程候选；必要时最多读取 11 张唯一局部裁图。视觉复核必须写入截图路径、`completeCurrentPixelReview:true`、唯一 `localReviewPaths`，以及全部可见结果卡的 cardId、coord、cardTypeCandidate、topology 和新增/替换字段。不得复制黄金文字、猜写屏外内容或手改审计。

后续尝试读取 retry plan，只对 `targets[]` 指定卡片写 `cardOverrides`，但仍须重新运行完整 candidate→review→publish→validate；不得把 retry plan 当成失败证据后停止。

卡型使用 `card-type-registry.v1.json` 的全部十种正式类型及各自结构。三种商家卡互斥：

- 商家头图 + 商家信息 + 带独立坐标的文字 `attachedItems`，且无商品图：`商家卡片_文字下挂`。
- 商家头图 + 商家信息 + 带 CV 图片锚点的商品 `attachedItems`：`商家卡片_图文下挂`。
- 商家头图 + 商家信息 + 无 `attachedItems`：`商家卡片_无下挂`。

无下挂商家卡不得回退为异构卡；异构卡只在全部已知卡型均不满足时使用。所有字段必须保持原子化，一个字段不得捆绑多个独立语义。

### A3 发布、校验和返工

```bash
"${pythonBin}" "${phase2SkillDir}/scripts/run_phase2_recognition.py" \
  --stage publish --query "${query}" --screenshot "<output.screenshot>" \
  --candidate-bundle "<attempt.candidateBundle>" --visual-review "<attempt.visualReview>" \
  --output "<attempt.manifest>" --recognition-audit "<attempt.recognitionAudit>" \
  --artifacts-dir "<attempt.artifactsDir>"

"${pythonBin}" "${projectDir}/phase2-card-annotation/scripts/validate_element_manifest.py" \
  "<attempt.manifest>" --audit "<attempt.audit>" \
  --recognition-audit "<attempt.recognitionAudit>" --require-current-image-calibration

"${pythonBin}" "${projectDir}/phase2-card-annotation/scripts/build_phase2_retry_plan.py" \
  --recognition-gate "<attempt.artifactsDir>/recognition-gate.json" \
  --manifest-audit "<attempt.audit>" --manifest "<attempt.manifest>" \
  --attempt "<n>" --max-attempts "${phase2MaxAttempts}" --output "<attempt.retryPlan>"
```

候选与当前截图的路径/SHA 不匹配、复核不完整、结构/schema/recognition/manifest 审计失败时，均不得进入 Stage B。只有 `status=confirmed`、`phase3Ready=true`、`wholePageGate=true`、recognition audit 合法且 manifest audit `valid=true` 的尝试可以成为最终 manifest。

`retryRequired=true` 时必须按 target cardId 修正并实际生成下一次完整尝试。成功结果的最后一个 plan 必须 `retryRequired=false` 且 `errors=[]`；只有耗尽 `phase2MaxAttempts` 后仍失败才允许 `blockedAt="stageA"`。`stageA.phase2Attempts` 和 `stageA.retryPlans` 必须记录完整连续历史。

成功尝试通过全部门禁后，使用一次性发布脚本把胜出 manifest/audit 固定到 task 的 `output.manifest/output.audit/output.recognitionAudit`，Stage A 只能返回这些冻结路径：

```bash
"${pythonBin}" "${projectDir}/workflow/promote_phase2_attempt.py" \
  --screenshot "<output.screenshot>" --manifest "<attempt.manifest>" \
  --manifest-audit "<attempt.audit>" --recognition-audit "<attempt.recognitionAudit>" \
  --output-manifest "<output.manifest>" --output-audit "<output.audit>" \
  --output-recognition-audit "<output.recognitionAudit>"
```

## Stage B：Phase3 按需测量、评测与返工

历史 Phase3 结果或账本不是当前任务的输入。它们与当前 manifest 的原子 ID、边界或计数不一致时只保留审计价值；不得复用，也不得因此阻断。当前任务必须仅从已发布 manifest 生成完整的 `task.evalTargets` 评测结果。

当前 Evaluation Agent 本身就是 Phase3 判断执行器：按已读取的 leaf Skill 对当前 manifest 逐项判断并写入结果，不存在也不需要另一个“结果生成脚本”。缺少这类脚本、工作量尚未完成或需要继续撰写结果都不是 `blockedAt=stageB` 的理由；必须继续到全部目标及 Phase4 验证完成。

所有最终 Stage A manifest 发布后，逐一读取 task.requiredReads 中的共同知识、维度 contract 和选中 leaf skills。`task.evalTargets` 是唯一可评测集合；所有 skill 通过 `phase2_bundle_loader.py` 只读正式 manifest。

Phase2 A2 已在当前同一 Agent 中读取过每张完整原图。进入 Phase3 后，对所选视觉类 Skill 复用这份当前图上下文，按截图完成一次共享视觉判断轮次，再把同一轮观察分别写入各叶子 Skill 的既有 `assessmentRows`；不得为此新建视觉中间 JSON。长图或局部不确定时可以复看有界区域，但不得把视觉判断倒灌为 Phase2 事实。

先对全部最终 manifest 一次性运行按需确定性测量准备：

```bash
"${pythonBin}" "${projectDir}/workflow/prepare_phase3_measurements.py" \
  --task "<task.json>" \
  --manifest "<final.manifest-1>" --manifest "<final.manifest-2>" \
  --output-dir "<stagePaths.measurementsDir>"
```

只有 `phase3_measurement_requirements.json` 为已选 skill 声明的确定性脚本可以读原图像素。脚本测量不得倒灌 Phase2；JSON 类 Skill 禁止回看截图补写结构化事实。视觉类 Skill 的感知判断由当前 Evaluation Agent 完成，不登记为测量脚本。缺少未注册的精确测量时写明确 review 项，不能伪造数值，也不能因此阻断其他可评 skill。

按每个 leaf skill 生成完整 `assessmentRows`/issues 后，写入 `<stagePaths.evalResultFile>`，再运行：

```bash
"${pythonBin}" "${projectDir}/scripts/validate_eval_results.py" \
  "<stagePaths.evalResultFile>" --audit "<stagePaths.evalAuditFile>"
```

可修复的覆盖、字段、计数或引用错误必须在本任务内修正并重跑 validator。只有确实无法取得可信 Phase2 原子事实时才允许 `blockedAt="stageB"`。

## Stage C：Phase4 问题证据引用与交付

仅在 Stage B audit `valid=true` 后读取 `phase4-issue-evidence/SKILL.md`。只为 Phase3 已确认的问题回写其所属 `details.screenshot` 原图引用，不增加业务判断，不绘制红框，也不创建任何派生图片。`stageC.evidenceImages` 必须是问题实际引用的 `screenshots/` 原图去重集合；无问题时为空数组。完成后用同一 validator 的 `--require-evidence` 模式复验最终结果并更新 `<stagePaths.evalAuditFile>`。

最终按 `evaluation-result.schema.json` 写 `resultPath`：Stage A 提供最终 manifest/audit 与完整重试历史，Stage B 提供评测结果/audit/测量索引，Stage C 提供证据，Stage D 固定 `{}`。不生成单词 HTML，不执行 Phase5，不删除或覆盖任何截图及过程产物。
