# 美团搜索结果页标准化评测 Agent

这是一个面向美团搜索结果页的可复用评测系统。它把截图采集、页面事实识别、多维度评测、问题证据和 HTML 报告串成一条可追溯的流程。

```text
截图分组 → 每词 Phase2 事实清单 → Phase3 评测 → Phase4 问题证据 → 整批一次 Phase5 HTML 报告
```

系统将截图采集与评测分开处理：已有截图可以稍后再评测；只想采集截图时也不会生成评测结论。

## 如何发起任务

| 目标 | 可以这样说 | 交付物 |
|---|---|---|
| 评测一张已有图 | “评测这张截图：`<绝对路径>`” | 单图事实清单、评测结果和问题证据；单词任务不生成 HTML |
| 评测多张图或一个目录 | “评测这个目录中的截图：`<绝对路径>`” | 先返回截图分组；确认评测范围及是否生成报告（本地/NoCode）后按组评测 |
| 截图后评测 | “搜索 `<词>`，截图 `<Tab>` 第 `<屏>` 屏后评测” | 截图通过检查后，再确认评测范围与报告出口 |
| 只截图 | “只截图，不评测：搜索 `<词>`，`<Tab>`，第 `<屏>` 屏” | 可复用截图写入 `screenshots/` |
| 复核已有报告 | “复核报告 `<路径>`” | 复核其输入、事实清单、结果和证据；必要时新建批次重跑 |
| 了解能力 | “这个项目能评什么？” | 输入、评测范围和产物说明；不会运行评测 |

系统不会把用户提供的图片直接当作人工点评对象。它会先确认任务模式、输入范围和必要参数；任何评测都必须在开始前确认评测范围，以及是否生成报告（不生成、本地 HTML 或 NoCode），再进入对应流程。

## 快速开始

在项目根目录执行：

```bash
# 使用已有截图
bash setup.sh

# 需要现场截图时，额外检查设备环境
bash setup.sh --with-device
```

### 评测项目外的已有截图

先将原图以副本方式接入项目，再选择要评测的截图组：

```bash
python3 workflow/eval_cli.py prepare-evaluate \
  --project-dir "$(pwd)" \
  --source-dir "/path/to/external/screenshots"
```

该命令不修改源文件，会把图片以原文件名复制到 `screenshots/`。同名但内容不同的图片会自动保留为独立副本，不会覆盖旧文件。

若文件名符合 `<搜索词>_<Tab>_<屏>`，已确定搜索词后可追加 `--query <搜索词>`。对于 `IMG_0001.png` 等未命名但可读取的图片，发现结果会将每张图列为独立有效未命名组并返回 `awaiting_visual_identity_resolution`。宿主读取当前图片像素，生成 `screenshot.identity-map` 后显式选择；不修改文件名，也不要求用户补写文件身份：

```bash
python3 workflow/eval_cli.py prepare-evaluate \
  --project-dir "$(pwd)" \
  --source-dir "/path/to/external/screenshots" \
  --identity-map "/path/to/screenshot-identity-map.json" \
  --selected-screenshot "$(pwd)/screenshots/IMG_0001.png"
```

身份映射记录当前文件 SHA-256、query、Tab、屏号、识别来源和置信度；CLI 会再次核验路径和字节。未命名图不会被自动合并；多个不同搜索词按身份映射分别创建任务。命令会生成可交给宿主执行环境的任务文件；具体交接方式见 [HOST_ADAPTER.md](workflow/HOST_ADAPTER.md)。

### 批量评测与最终报告

同一份报告中的搜索词使用相同 `batchId`，每个搜索词使用独立 `runId`，分别创建一个最终契约任务：

```bash
python3 workflow/eval_cli.py prepare-evaluate \
  --project-dir "$(pwd)" \
  --source-dir "/path/to/external/screenshots" \
  --query "咖啡" \
  --run-id "batch-20260903-coffee" \
  --batch-id "batch-20260903" \
  --evaluation-selection '{"mode":"full_19"}' \
  --report-outlet local_html
```

对每个搜索词重复执行一次，只替换 `--query` 和 `--run-id`。确认选中的截图总数超过 3 张时，必须用 `prepare-batch` 冻结全部预期 task，并按搜索词下发 Evaluation Agent；一个 Agent 处理一个词的全部截图。`meituan_eval_workflow.js` 的 `batch_evaluate` 模式每批最多并发 3 个词，并保存每轮状态快照。3 张及以下不因图片数本身强制使用子代理。

每个词完成后都要执行任务 JSON 中自带的 `completionCommand`。只有产生 `status=completed` 的本地回执，才算成功。失败词使用新的隔离 `runId/taskPath` 和新的 Evaluation Agent 定向重派；每词最多三个任务，第三次仍失败则标记 `abandoned`，不重跑其他成功词。

Claude、Codex、Catpaw 和其他宿主使用同一个派发入口。声明当前宿主实际具备的能力后，命令返回统一的 `MEITUAN_AGENT_DISPATCH` 信封；所有宿主都只向 Evaluation Agent 传递 `taskPath`：

```bash
python3 workflow/eval_cli.py prepare-dispatch \
  --task "<taskPath>" --host codex \
  --capability readImagePixels --capability readFiles \
  --capability runCommands --capability writeJson
```

将 `--host` 换成 `claude`、`catpaw` 或 `generic`，任务内容、能力门禁、结果路径和完成命令均不变化。Claude 可继续使用 `.claude/agents/evaluation-agent.md` 的原生名称绑定；其他宿主使用自身的子 Agent API。

没有 Workflow DSL 的宿主先冻结批次，再依据返回的 `statePath` 执行派发、`advance-batch` 核验和 `create-batch-retry` 隔离重试：

```bash
python3 workflow/eval_cli.py prepare-batch \
  --project-dir "$(pwd)" \
  --batch-id "batch-20260903" \
  --task "<咖啡初始 taskPath>" \
  --task "<火锅初始 taskPath>" \
  --max-query-attempts 3
```

支持 Workflow DSL 时，直接把相同的初始 `taskPaths`、`batchId` 传给 `meituan_eval_workflow.js` 的 `batch_evaluate` 模式；它只是上述统一任务协议的 DSL 适配器。Phase5 的业务 Tab 由当前截图中已验收商卡的可见语义与履约标识推导，不能由搜索词或预设 Tab 猜定。全部预期词进入 `completed` 或 `abandoned` 终态后，统一执行一次 Phase5：

```bash
python3 workflow/eval_cli.py finalize-batch \
  --project-dir "$(pwd)" \
  --batch-id "batch-20260903" \
  --batch-state "<advance-batch 返回的最新 statePath>"
```

推荐传入批次控制器最后生成的 `--batch-state`；`finalize-batch` 会拒绝 pending、尚可重试的失败词，以及没有批次状态佐证的提前部分报告。它只把 completed 回执列出的精确 manifest 和结果交给 Phase5；abandoned 词仅保留在批次状态中，不进入报告。输出：

- `reports/meituan_search_experience_dashboard_<batchId>.html`
- `reports/.governance_dataset_<batchId>.json`

Phase5 不调用模型，不重新评测截图，也不会把总报告写回各词回执。只要至少一个词完成即可在终态屏障后生成唯一报告；若全部词 abandoned，则不生成空报告。报告可覆盖任意用户确认的评测范围，并显式提供预期业务 `businessCode` 集合。

## 用户任务模式与批次执行模式

| 模式 | 适用场景 | 需要提供的信息 |
|---|---|---|
| `capture_only` | 只采集截图 | 搜索词、Tab、屏数 |
| `evaluate_only` | 评测已有截图 | 截图范围、评测范围、报告出口 |
| `capture_and_evaluate` | 先截图再评测 | 先提供搜索词、Tab、屏数；截图完成后再确认评测范围和报告出口 |
| `batch_evaluate` | 内部批次执行入口 | 初始 `taskPaths`、`batchId`；可选 `expectedBusinessTabs` 仅作事后断言，不作为归属依据 |

评测已有截图时，系统会先发现并分组 `screenshots/` 内的文件。规范名称从 `<搜索词>_<Tab>_<屏>.<ext>` 推导；未命名图由宿主读取当前像素生成身份映射。两条路径都不要求重命名原图。

## 输入、输出与数据流

| 阶段 | 输入 | 主要输出 |
|---|---|---|
| Phase1 截图/发现 | 设备或已有截图 | `screenshots/` |
| Phase2 事实识别 | 单张截图 | `screenshots-out/` 内一图一份事实清单 |
| Phase3 评测 | 原始截图和对应事实清单 | `.artifacts/过程文件-评测结果与审计/`；视觉项共用一次原图观察，色彩项共用一份像素统计产物 |
| Phase4 证据 | 已确认的问题定位 | `screenshots-out/evidence/` |
| Phase5 报告 | 本批 completed 词已验收的结果、manifest 和证据 | `reports/` 内唯一批量 HTML 和治理数据集；不呈现 abandoned 词 |

每张截图都有独立事实清单，Phase3 只消费已通过 Phase2 校验的清单。批量索引只用于定位文件，不能替代单图事实。Phase3 不要求 Phase2 为主观视觉判断新增字段：结构、数量和语义类规则扫描事实清单；视觉秩序、信息层级、信息分区等感知类规则由同一 Evaluation Agent 复用已读取的原图上下文统一判断；卡片与页面色彩复用同一份原图像素测量结果。

### 词级 Agent 交付契约

Evaluation Agent 只完成 Phase2～4，并返回可核验的文件路径。它不写报告正文，也不生成单词 HTML：

```json
{
  "ok": true,
  "query": "当前搜索词",
  "stageA": {
    "phase2Attempts": 1,
    "retryPlans": ["<phase2 retry plan path>"],
    "elementListPaths": [],
    "elementAuditPaths": [],
    "elementCount": 0,
    "annotated": []
  },
  "stageB": {
    "measurementsIndex": "",
    "evalResultFile": "",
    "evalAuditFile": "",
    "evalCount": 0
  },
  "stageC": {
    "evidenceImages": [],
    "skipped": []
  },
  "stageD": {},
  "blockedAt": "",
  "error": ""
}
```

这些产物与 Phase5 的关系是：

| 子 Agent 产物 | Phase5 用途 |
|---|---|
| `elementListPaths` | 获取搜索词、原图、卡片/元素 ID、卡型、业务归属与可见语义 |
| `elementAuditPaths` | 证明每份 Phase2 manifest 已通过确定性验收 |
| `evalResultFile` | 获取维度、Skill、Tab、评级、问题描述和独立建议 |
| `evalAuditFile` | 证明 Phase3 结果和 Phase4 证据引用已通过确定性验收 |
| `evidenceImages` | 验证问题证据文件真实存在；HTML 使用结果中回写的 `evidenceImage` |
| `stageD` | 固定为空交接对象；最终报告只在批次级 Phase5 生成 |

同一搜索词可以包含多张截图。Phase5 按原图路径隔离 manifest，因此不同截图中重复出现的 `C1`、`E1` 等局部 ID 不会相互覆盖或被错误去重。

## 评测范围

系统提供 19 个评测项，分为三个维度：

| 维度 | 内容 | 数量 |
|---|---|---:|
| 卡片/组件 | 供给、视觉秩序、色彩、元素复杂度、信息层级、分区、真实性、冗余 | 8 |
| 单元素 | 供给质量、色彩逻辑、元素规范、信息真实性 | 4 |
| 页面框架 | 模块完整性、视觉秩序、页面色彩、静态组件复杂度、浏览流畅度、信息可比性、信息冗余 | 7 |

可以选择完整 19 项、一个或多个维度，或指定具体评测项。只要用户选择生成报告，任意已确认范围的批次均可进入治理看板，并在看板中明确“已选 X/19 项”；报告只呈现评级与问题项数，不计算综合分。

## 工作方式

```text
Workflow
├─ Screenshot Agent：截图或发现已有截图
├─ 每个搜索词一个 Evaluation Agent：Phase2 → Phase3 → Phase4
└─ 全部词进入 completed/abandoned 终态后：一次 Phase5 批量报告
```

已确认截图超过 3 张时，Workflow 必须按词级子代理执行；每个子代理处理一个搜索词的全部截图，每批最多 3 个子代理并发。`batch_evaluate` 负责批次状态快照、失败词隔离重派和终态屏障。评级和事实判断仍由词级评测流程完成。Phase5 只读取 completed 词的精确产物；连续三次失败的 abandoned 词不进入报告，全部失败时不生成报告。

任务只使用 `MEITUAN_EVAL_TASK`、`MEITUAN_AGENT_DISPATCH`、`workflow/contracts/phase234-query-pipeline.md` 和 `evaluation-result.schema.json`。流程先产出不可发布的本地 CV 候选，再由具备读图能力的宿主完成当前像素复核；门禁失败在同一任务内按卡片定向修正并重新发布，只有耗尽重试预算后才阻断。Phase3 按所选 Skill 运行必要的确定性像素测量，Phase4 生成并校验证据。历史版本契约已备份并移出当前入口，已有本地产物保持不变。

## 目录速览

```text
phase1-screenshot/                 截图与已有截图发现
phase2-card-annotation/            单图事实识别与校验
phase3-evaluation/                Phase3 统一入口、共同知识与 19 项评测
phase4-issue-evidence/             问题证据图
phase5-report/                     本地报告与可选线上看板
workflow/                          任务路由与宿主交接
screenshots/                       截图输入
screenshots-out/                   Phase2 清单与问题证据
.artifacts/过程文件-评测结果与审计/ 过程结果与审计
reports/                           最终本地报告
```

## 深入文档

| 需要了解的内容 | 入口 |
|---|---|
| 任务模式、参数和调用顺序 | [.claude/skills/run-eval.md](.claude/skills/run-eval.md) |
| 项目阶段、数据流和执行约束 | [CLAUDE.md](CLAUDE.md) |
| 项目外截图接入与宿主交接 | [workflow/HOST_ADAPTER.md](workflow/HOST_ADAPTER.md) |
| 截图规则 | [phase1-screenshot/SKILL.md](phase1-screenshot/SKILL.md) |
| Phase2 事实清单与校验 | [phase2-card-annotation/SKILL.md](phase2-card-annotation/SKILL.md) |
| Phase3 范围、维度与 19 项 Skill | [phase3-evaluation/README.md](phase3-evaluation/README.md) |
| 本地报告与治理看板 | [phase5-report/SKILL.md](phase5-report/SKILL.md) |

## 本地产物与 Git 边界

`.artifacts/`、`screenshots-out/` 和 `reports/` 是用户本地运行产物。除非明确要求上传，不应将它们加入 Git、提交或推送。
