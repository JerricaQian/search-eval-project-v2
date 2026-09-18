---
name: run-eval
description: 使用美团搜索评测最终 Workflow：仅截图、仅评测已有截图，或截图后确认评测的全流程。
---

# 运行评测工作流

用户请求截图、评测已有截图、现场截图后评测或生成报告时使用本技能。入口为：

维护者概览见同目录 `README.md`；执行时仍以本文件和 task 冻结的契约为准。

```text
workflow/meituan_eval_workflow.js
```

该 Workflow 依赖宿主注入的 `args`、`agent`、`parallel`、`phase`、`log`，不能直接使用 Node 运行。

## 先做请求预检，再回复用户

在读取截图像素、做人工判断或调用 Workflow 前，必须完成下列动作：

1. 完整读取项目根 `CLAUDE.md`、存在时的 `AGENTS.md`、根 `README.md`；
2. 识别请求属于单图、多图/目录、现场截图、已有报告复核还是能力咨询；
3. 对评测任务读取本文件、`workflow/meituan_eval_workflow.js`，并定位所选阶段的 `SKILL.md`；
4. 先回复用户：已识别的任务类型、输入范围、下一步阶段、缺失输入和最终产物；任何评测必须询问并获得确认的评测范围，以及是否生成报告（不生成、本地 HTML 或 NoCode）。

这一步是门禁：未完成时不得对截图打分、罗列 UI 问题，或宣称已评测。人工视觉判断只能作为流水线结束后的“人工复核”，不能代替 Phase2～4 与批次级 Phase5。

### 请求路由与首次回复

| 用户表达 | 路由 | 首次回复必须包含 |
|---|---|---|
| 一张图片/一个图片路径 | `evaluate_only`；先发现、校验并选择该图 | 文件路径、任务模式、待确认的维度，以及 manifest→评测结果→证据产物；单词任务不生成 HTML |
| 多张图片或目录 | `evaluate_only`；先发现，未命名图自动读当前像素生成身份映射，再按搜索词分组 | 规范分组、有效未命名候选/身份映射和真正无效项；不对任何单图先行点评 |
| “帮我截图后评测” | `capture_and_evaluate` | 需要的搜索词、Tab、屏数；说明截图成功后才会确认评测配置 |
| “只帮我截图” | `capture_only` | 需要的搜索词、Tab、屏数；明确不会生成评测报告 |
| “这份报告为什么有问题” | 复核既有 Phase2～5 产物；必要时重跑受影响阶段 | 复核对象、证据/manifest 范围和新批次产物策略 |
| “你能评什么” | 只读取项目说明与技能 | 支持的输入、评测维度、产物和限制；明确尚未执行评测 |

项目外的用户图片必须以不改动原件的方式进入项目级 `screenshots/` 输入集，再按发现流程处理；不能直接根据外部路径进行手工评判。

### 项目外截图的直接复制（必经）

用户给出项目外目录时，先用可移植前置入口导入；不要要求用户手工改名，也不要将外部路径直接写入 `selectedScreenshots`：

```bash
python3 workflow/eval_cli.py prepare-evaluate \
  --project-dir <项目绝对路径> \
  --source-dir <外部截图目录>
```

该命令保留源文件，并将图片按原文件名直接复制到 `screenshots/`，不生成 Intake
manifest，也不重命名。无 `--query` 时返回可供用户选择的截图组与独立的未命名图；带 `--query` 时除
`MEITUAN_EVAL_HANDOFF.workflowArgs` 外，还生成 `MEITUAN_EVAL_TASK` 的
`portableTask.taskPath`。所有宿主统一运行 `prepare-dispatch --task <taskPath> --host <claude|codex|catpaw|generic>` 并声明实际具备的 `requiredCapabilities`；不能读图时写 `blockedAt=preflight` 而不派发。通过后只把该路径交给一个 Evaluation Agent，完成后执行
任务中的 `completionCommand`；正式 Agent 契约为 `workflow/contracts/phase234-query-pipeline.md`，不要把 Phase2～4 的长契约重新粘贴进 prompt。详见
`workflow/HOST_ADAPTER.md`。
发现阶段只把损坏、过小或不可读取的图片报告为无效。无法从文件名解析身份但可读取的图片以一图一组的 `unlabeledGroups` 返回，不得放入错误列表或要求先改名。宿主随后读取每张当前截图，生成带路径、SHA-256、query、Tab、屏号、来源和置信度的 `screenshot.identity-map`；多个搜索词按映射拆成词级任务，不能按视觉相似性自动合并。同名不同字节时自动追加递增副本序号并保留两份。

## 先确认任务模式

先让用户选择一项：

1. **仅自动化截图**
2. **仅评测已有截图**
3. **自动化截图 + 评测**

只询问当前模式需要的参数，不能提前追问无关项目。任何包含评测的模式在 Phase2 前都必须明确确认 `evaluationSelection` 和 `reportOutlet`；`reportOutlet` 为 `none`、`local_html` 或 `nocode`，不得默认为 `local_html`。

| 模式 | 询问 | 不询问 |
|---|---|---|
| 仅自动化截图 | 搜索词、Tab、屏数 | 评测维度、报告出口 |
| 仅评测已有截图 | 截图范围、评测维度、报告出口 | 搜索词、Tab、屏数、设备参数 |
| 截图 + 评测 | 先问搜索词、Tab、屏数；截图成功后再问维度、报告出口 | — |

## 调用方式

所有调用必须显式传入 `projectDir`。

### 1. 仅自动化截图

```json
{
  "mode": "capture_only",
  "projectDir": "<项目绝对路径>",
  "query": "库迪",
  "tabs": ["全部", "外卖"],
  "screens": ["1", "2"]
}
```

Workflow 只调用 Screenshot Agent，返回 `screenshots/` 中本次有效图片的路径。

### 2. 仅评测已有截图

第一轮只发现截图，不输入搜索词：

```json
{
  "mode": "evaluate_only",
  "projectDir": "<项目绝对路径>",
  "externalScreenshotDir": "<项目外截图目录>",
  "discoveryOnly": true
}
```

Workflow 返回规范截图组；对 `IMG_*.PNG` 等未命名图会自动读取当前像素并返回 `screenshotIdentityMap`。外层按映射中的 query 拆成词级任务后再调用，不要求用户重复输入或改名：

```json
{
  "mode": "evaluate_only",
  "projectDir": "<项目绝对路径>",
  "selectedScreenshots": ["<截图绝对路径>"],
  "screenshotIdentityMap": {"contract": "screenshot.identity-map", "entries": []},
  "evaluationSelection": { "mode": "dimensions", "dimensions": ["phase3-card_or_component-eval"] },
  "reportOutlet": "local_html",
  "phase2Mode": "lightweight"
}
```

规范文件名可解析为 `<搜索词>_<Tab>_<屏>.<ext>`。外部原件不重命名，尾部 `_副本`、`_副本N`、`_副本(N)` 或 `_copyN` 解析为独立副本实例而不是搜索词的一部分；无法解析时以当前像素身份映射为准。评测成功后如需规范文件名，只生成独立副本或映射，不覆盖原图。

### 3. 自动化截图 + 评测

第一轮只执行截图：

```json
{
  "mode": "capture_and_evaluate",
  "projectDir": "<项目绝对路径>",
  "query": "库迪",
  "tabs": ["全部", "外卖", "团购"],
  "screens": ["1", "2", "3"]
}
```

它返回 `awaiting_evaluation_config` 及截图路径。截图成功后，再询问用户评测维度和报告出口，并使用返回的路径发起第二轮：

```json
{
  "mode": "evaluate_only",
  "projectDir": "<项目绝对路径>",
  "selectedScreenshots": ["<第一轮返回的截图绝对路径>"],
  "evaluationSelection": { "mode": "full_19" },
  "reportOutlet": "local_html",
  "phase2Mode": "lightweight"
}
```

`reportOutlet` 必须在评测前确认：`none` 表示不生成报告；`local_html` 表示整批完成后生成本地 HTML 与数据集；`nocode` 表示先生成本地 HTML 与数据集，再按 `phase5-report/nocode-dashboard/SKILL.md` 获得用户授权后处理线上出口。任意已确认的评测范围都可以生成报告，且报告必须标注“已选 X/19 项”；词级子 Agent 始终不生成 HTML。

### Phase3 评测范围选择

新调用使用 `evaluationSelection`，由 `phase3-evaluation` 统一入口根据 `catalog.json` 确定性解析当前 19 项 Skill：

```json
{ "mode": "full_19" }
```

```json
{ "mode": "dimensions", "dimensions": ["phase3-single_element-eval"] }
```

```json
{
  "mode": "custom_skills",
  "skills": [
    { "dimension": "phase3-card_or_component-eval", "skill": "eval-7-info-authenticity" },
    { "dimension": "phase3-card_or_component-eval", "skill": "eval-8-info-redundancy" }
  ]
}
```

未传 `evaluationSelection` 时，保留 `dimensions` 的兼容行为。创建词级任务时，控制器会立刻把选择解析成不可变的 `evaluationScope.evalTargets` 和 `requiredReads`：子 Agent 必须逐一读取共同知识、每个已选维度契约与叶子 Skill，且不得读取或评级未选 Skill。所有报告只呈现已执行范围的评级与问题项数，不计算综合分。

## Evaluation Agent 的固定约束

每个搜索词的 Evaluation Agent 在同一上下文内执行 Phase2 → Phase3 → Phase4：

- 每张截图一个独立 manifest；
- Phase2 默认本地轻量识别，必须通过 `validate_element_manifest.py`；
- Phase3/4 必须通过 `validate_eval_results.py`，Phase4 使用 `--require-evidence` 校验每个问题精确引用所属 `screenshots/` 原图；
- 成功结果的 `stageD={}`，不写报告内容或报告路径；
- 不删除或覆盖截图、过程文件、证据或历史报告。

确认选中的截图总数超过 3 张时，必须先按搜索词冻结全部预期 task，再按统一 `MEITUAN_AGENT_DISPATCH` 下发词级子代理；每个子代理处理一个词的全部截图，每批最多派发 3 个。该阈值以截图发现和身份映射后的 `selectedScreenshots` 总数计算，而非搜索词数量；3 张及以下不因图片数本身强制下发子代理。支持 Workflow DSL 时，`meituan_eval_workflow.js` 的 `batch_evaluate` 只是同一协议的宿主适配器。Phase2 内部纠错耗尽后，外层为该词创建新的隔离 `runId/taskPath` 并交给新的 Evaluation Agent，最多三个词级任务；第三次仍失败则标记 abandoned。只有所有词进入 completed/abandoned 终态后才执行一次 `finalize-batch --batch-state`；Phase5 仅消费 completed 词，abandoned 词不进入报告。全部 abandoned 时不生成空报告。

```json
{
  "mode": "batch_evaluate",
  "projectDir": "<项目绝对路径>",
  "batchId": "<本批唯一 ID>",
  "taskPaths": ["<query-1 初始 taskPath>", "<query-2 初始 taskPath>"],
  "expectedBusinessTabs": ["dine_in", "food_delivery"],
  "maxQueryAttempts": 3
}
```
