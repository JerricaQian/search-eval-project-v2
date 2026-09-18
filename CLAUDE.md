# 项目工作流声明（search-eval-project）

本仓库是美团搜索结果页标准化评测系统。对外由 **Workflow → Screenshot Agent / 词级 Evaluation Agent → 批次 Phase5** 编排：Screenshot Agent 负责 Phase1 的现场截图或已有截图发现；每个搜索词的 Evaluation Agent 在同一上下文内执行 **Phase2 轻量识别 → Phase3 多维度评测 → Phase4 问题证据**。失败词用新的 `runId` 和新的 Evaluation Agent 定向重派，最多三次；全批所有词进入 completed 或 abandoned 终态后，Phase5 只运行一次并只消费完成词，不在报告中呈现放弃词。若没有任何完成词，不生成空报告。完整参数与用法见 `README.md`。

## 1.0 任务模式与职责边界

- `capture_only`：只调用 Screenshot Agent；只向用户确认搜索词、Tab、屏数。
- `evaluate_only`：Screenshot Agent 只读发现 `screenshots/`；用户选择截图后才调用 Evaluation Agent，只确认评测范围（完整19项、维度或自定义 Skill）和报告出口，不要求用户重复搜索词、Tab、屏数或设备参数。
- `capture_and_evaluate`：先调用 Screenshot Agent；截图通过基本完整性检查后，返回 `awaiting_evaluation_config`，再确认评测范围和报告出口后调用 Evaluation Agent。
- Workflow 只做条件询问、模式路由和词级执行；外层宿主负责单词隔离、批次屏障、失败词重试和状态汇总。二者不得运行 OCR、评测、评分或证据业务逻辑；批次完成后只可调用 Phase5 的确定性生成器。
- 当前流程不依赖 Runtime Guard、自动反思或经验库。Phase2～4 的确定性校验器仍在 Evaluation Agent 内执行。

## 评测请求预检与路由门禁（铁律）

任何涉及本项目的截图、评测、已有报告复核、批量治理或能力咨询的用户请求，都必须先进入唯一入口 `workflow/meituan_eval_workflow.js` 的任务路由语义；不得把用户提供的图片直接当作人工点评对象。

### 执行前的必经预检

在识别截图内容、给出评级或运行任何阶段脚本前，当前会话必须：

1. 确认项目根目录，并完整读取根 `CLAUDE.md`、存在时的 `AGENTS.md`、根 `README.md`；
2. 识别用户意图与输入类型（单图、多图/目录、现场截图、已有结果复核或能力咨询）；
3. 定位并读取该意图所需的入口与阶段契约：评测任务读取 `.claude/skills/run-eval.md`、`workflow/meituan_eval_workflow.js` 及所选阶段的 `SKILL.md`；能力咨询仅读取这些说明文件，不运行评测；
4. 在执行前先向用户回告：识别出的任务模式、输入范围、下一步将调用的阶段、仍缺的最小输入，以及预期交付物；对任何包含评测的模式，必须明确询问并获得确认的 `evaluationSelection`（完整 19 项、维度或自定义 Skill）和 `reportOutlet`（不生成、`local_html` 或 `nocode`）。

未完成上述预检，不得开始目视判图、OCR、评级或输出“已完成评测”。人工视觉判断仅可作为已完成流水线后的复核意见，并必须标为“人工复核”，不能替代 Phase2～4 结果或批次级 Phase5。

### 用户请求路由

| 用户意图 | 路由与后续动作 | 首次回复要求 |
|---|---|---|
| 单张已有截图评测 | `evaluate_only`：先只读发现/校验截图，再由用户确认评测范围和报告出口后执行 Phase2～4 | 确认文件、任务模式和将产出的 manifest、评测结果与证据；单词任务不生成 HTML，不得先给人工分数 |
| 多张图片或目录评测 | `evaluate_only`：发现规范组；未命名有效图自动读当前像素形成身份映射并按 query 分组；同词图片作为一组进入流水线 | 返回规范组、有效未命名候选/身份映射和真正无效文件，并询问评测范围与是否生成报告（本地或 NoCode）；文件名不触发阻断 |
| 现场截图后评测 | `capture_and_evaluate`：先 Phase1，截图合格后再收集评测范围和报告出口 | 明确截图词、Tab、屏数，以及截图完成后会暂停确认评测配置 |
| 仅自动化截图 | `capture_only`：只执行 Phase1 | 明确只交付截图，不生成评测结论或报告 |
| 复核已有报告 | 读取其输入、单图 manifest、阶段结果、证据与校验记录；必要时回退并重跑受影响阶段 | 标明复核范围及是否会产生新批次产物；不得用新的人工评分覆盖旧结果 |
| 询问系统能力 | 只读取项目说明和已注册技能，回答支持的输入、维度、产物与限制 | 明确这是能力说明，未对任何截图运行评测 |

用户直接给出项目外图片路径时，先以不修改原文件的方式将图片直接复制到 `screenshots/`。复制保留原文件名，不生成 Intake manifest，也不做名称规范化；发现阶段只报告真正无效文件。文件名无法解析但图片可读取时进入 `unlabeledGroups`，由宿主读取当前像素生成 `screenshot.identity-map` 后继续，不得要求改名或把它列为错误。目标同名但字节不同则追加递增副本序号保留两份，绝不覆盖，并作为独立截图而非同一屏。

## 阶段与目录

| 阶段 | 目录 | 作用 |
|---|---|---|
| phase1 截图 | `phase1-screenshot/` | ADB 现场截图或复用已有图，产物写入项目根 `screenshots/` |
| phase2 轻量识别 | `phase2-card-annotation/` | 本地 CV/OCR、卡型契约、整页门控；每张截图输出一个独立元素清单 JSON |
| phase3 评测 | `phase3-evaluation/` | 统一入口下按单元素、组件/卡片、页面框架三个维度执行 19 项评测 |
| phase4 问题证据 | `phase4-issue-evidence/` | 将 phase3 已判定的问题直接绑定到对应 `screenshots/` 原图，不生成派生图片 |
| phase5 报告 | `phase5-report/` + `workflow/eval_cli.py finalize-batch` | 全部词进入 completed/abandoned 终态后，仅消费完成词的 manifest、结果与原图证据引用，生成一份本地 HTML 与治理数据集 |


## phase2 输入 / 输出（关键）

- **输入**：截图取自项目根 `screenshots/`（phase1 产物或手动放入）。
- **输出**：每张输入截图分别输出一个元素清单 JSON 到项目根 `screenshots-out/`；文件之间不合并页面事实。
- phase2 不再以 skill 内部的 `screenshots/`、`out/` 子目录作为输入输出根；统一以项目级 `screenshots/` → `screenshots-out/` 为准。

## phase3 与 phase2 的衔接

- phase3 评测读取原始截图 + 与该截图一一对应的 Phase2 元素清单 JSON。
- Phase2 清单是对象身份、语义、归属、边界和计数的唯一结构化事实源；原图是视觉秩序、层级、分区、视觉关系与像素颜色的判断源。只有 `recognition.phase3Ready=true` 的单图清单可消费，批量 `index.json` 仅是索引。

## 数据流向一览

```
screenshots/ ──phase2 轻量识别──▶ screenshots-out/ ──phase3 评测──▶ .artifacts/
   (原图)                         (每张截图一个元素清单)              (问题与原图引用)
      │                                                                  │
      └──────────────────────phase4 直接引用原图──────────────────────────┘
                                                                         │
                                                                         ▼
                                                                     reports/
                                                              (phase5 HTML + 治理数据集)
                                                                         │
                                                                         └──NoCode 线上看板（可选）
```

## phase5 本地与线上出口

- `phase5-report/SKILL.md` 负责整批本地 HTML；只在所有预期词进入终态后运行。仅 completed 词进入数据集和报告；连续三次失败的 abandoned 词仅保留在批次控制状态中。必须至少存在一个 completed 词；业务 Tab 只能由回执 manifest 中当前截图可见商卡的语义与履约标识推导，`expectedBusinessTabs` 如传入仅作事后精确断言，绝不能作为归属依据；再由确定性生成器生成唯一看板与数据集。
- `phase5-report/nocode-dashboard/SKILL.md` 负责将上述数据集导入 NoCode、发布 Phase4 引用的原始截图并部署线上看板。线上页必须沿用本地看板的信息架构、分数/计数口径、视觉令牌与交互语义；它不能读取开发机 `file://` 图片，原图证据需经 `public/evidence/` 受控资源发布。
- NoCode 数据库的每张批次明细表都以真实 `batch_id` 关联；浏览器匿名角色对看板表的只读权限是上线验收项。CLI 能读取记录不代表线上页面可读。

## 执行模式：显式 Workflow 与 Agent 任务编排

本项目的“工作流”指固定的 `phase1 → phase2 → phase3 → phase4 → phase5` 数据契约，而不是必须依赖某一种宿主工具。两种执行模式产物与验收口径必须完全一致：

| 模式 | 适用场景 | 执行入口 | 约束 |
|---|---|---|---|
| **显式 Workflow（优先）** | 当前会话提供 Workflow 工具时 | `workflow/meituan_eval_workflow.js` + args | 单词模式执行一个词的 Phase2～4；确认选中的截图总数超过 3 张时，必须按搜索词下发 Evaluation Agent；`batch_evaluate` 冻结全部 task、每批最多并发 3 个词、失败词隔离重派并在终态屏障后调用一次 Phase5。 |
| **Agent 任务编排（等价回退）** | Workflow 工具未注入、宿主运行时不可用，或用户明确要求逐阶段执行时 | Agent 以 TODO 依次派发子代理调用 | 不得跳过任何 phase 的事实源、确定性校验或报告契约；不得因为显式 Workflow 不可用而停止评测；子代理分派结构必须与显式 Workflow 一致（见下）。 |

两种模式共用同一套**子代理分派结构**，不是各自随意拆分：

- **Screenshot Agent 独立**：`capture_only` 时执行现场 ADB 截图；`evaluate_only` 时只读运行 `phase1-screenshot/scripts/discover_screenshot_groups.py` 发现、聚合和校验已有截图；不与其它 phase 混入同一上下文。
- **Evaluation Agent 独立**：对一个搜索词的已确认截图，内部把本地轻量识别（phase2）→ 全维度评测（phase3）→ 问题证据（phase4）按序完成。Phase2 的候选生成和校验仍只运行本地脚本，并为每张截图分别生成清单；当前图片校准可读取当前截图，但只能回写经审计的 Phase2 事实。词级 Agent 不读取 Phase5 Skill、不跨词汇总、不生成 HTML。
- **统一派发机制**：先用 `python3 workflow/eval_cli.py prepare-evaluate` 为每个词生成一个 `MEITUAN_EVAL_TASK` 任务文件，同批任务共享 `batchId` 且各自使用唯一 `runId`。Claude、Codex、Catpaw 与其他宿主统一运行 `prepare-dispatch --task <taskPath> --host <host>`，声明实际能力后只把返回的 `taskPath` 交给一个 Evaluation Agent；宿主差异只存在于如何启动该 Agent。Agent 必须完整读取 `workflow/contracts/phase234-query-pipeline.md`、task 的 `contractFiles` 与 `requiredReads`，执行 CV 候选、当前图复核、发布与有界纠错，再进入 Phase3/4。结果写入 `resultPath` 后运行 `completionCommand` 生成本地回执。历史任务仍可通过 `.claude/agents/phase234-query-pipeline.md` 薄兼容入口读取正式契约；历史产物保持不变。
- **FACT_GATES 与 Phase2 返工复核内嵌在这一次调用内部**：Phase2 前置事实校验，以及校验失败触发的 Phase2 本地返工（按 `reprocessTargets` 重跑失败卡/失败行、更新对应单图清单、重跑受影响 skill），都必须在这同一个子代理的同一次执行内部完成闭环。Phase3 可按叶子 Skill 使用当前原图判断视觉体验，但不得据此补写 Phase2 的对象、语义、归属或边界事实；主 Agent 只根据这一次调用最终返回的 `ok`/`blockedAt`/`error` 决定是否继续 phase5 之后的 NoCode 出口或整体重跑。
- Phase3 统一入口与维度契约：先读 `phase3-evaluation/SKILL.md` 及共同知识索引，再根据 `phase3-evaluation/catalog.json` 读取对应维度的 `contract.md`，最后只读用户选中的叶子 Skill；评级仍以叶子 Skill 为准。

Agent 任务编排先要求用户选择 `capture_only`、`evaluate_only` 或 `capture_and_evaluate`，再按模式询问必要参数。仅评测已有截图时先发现截图组，不询问搜索词、Tab、屏数；截图+评测时必须在截图成功后才询问评测范围与报告出口。Phase2 默认 lightweight，不作为额外确认项。

Agent 任务编排的固定顺序：① Screenshot Agent 截图或发现/校验已有截图；② 每个搜索词一个 Evaluation Agent 调用（内部复用 `phase234-query-pipeline`）完成 Phase2～4并写回执；③ 失败词以全新 `runId` 和新的 Evaluation Agent 定向重派，最多三次，之后标记 abandoned；④ 所有词终态后只调用一次 `workflow/eval_cli.py finalize-batch`，仅消费 completed 词的产物。至少一个词成功时生成唯一 HTML 与治理数据集；abandoned 词不进入报告，全部 abandoned 时不生成空报告。

### 批量子代理调度纪律（铁律）

- **下发阈值按图计，不按词计**：确认的 `selectedScreenshots` 总数超过 **3 张** 时，宿主必须使用词级 Evaluation Agent 调度。该计数发生在截图发现和未命名图身份映射完成之后；3 张及以下的任务不因图片数量本身强制下发子代理。进入批量调度后，仍按下列单词边界和并发上限执行。
- **模型能力按阶段隔离**：Phase2 的候选提取、卡型契约和校验器必须运行本地 CV/OCR 与确定性 hooks；当前图片校准可由具备读图能力的模型依据当前像素回写 Phase2 manifest，但不得注入黄金字段或语言猜写。Phase3/4 只消费已验收 manifest 中的结构化事实；视觉类 Skill 可复用同一 Agent 已读取的当前原图，但不能借视觉判断改写 Phase2。模型名由宿主 adapter 选择，adapter 必须确认其具备读图和结构化 JSON 输出能力。
- 批量搜索词执行时，**一个子代理只处理一个搜索词**（该词所需的 Phase2/Phase3/Phase4 连续工作）；不得把多个词、多个截图词或“剩余若干词”合并下发给同一子代理。
- 每批并发最多 **3 个子代理 / 3 个搜索词**；必须等待本批全部成功、失败或明确介入完成后，才可启动下一批。不得为了追吞吐提前投放下一批。
- 子代理要处理的当前搜索词、批次序号、输入截图和输出目录必须冻结在 `MEITUAN_EVAL_TASK` 中；派发 prompt 只传 `taskPath`，不得再复制一份可能漂移的输入。失败只重试该词，不影响同批其他词和已完成批次。
- 维度内的 skill 可在该词子代理上下文中顺序执行；禁止以“每个 skill 一个子代理”的方式突破上述 3 个词并发上限。

### 过程文件与图片保留纪律（铁律）

- 评测、标注、截图、裁剪、扫描、审计、失败重试等过程中产生的文件和图片**一律不得删除**，包括 0 字节截图、临时裁剪图、scan 输出、旧证据图和失败中间产物。
- 需要从工作目录隔离的中间产物，必须写入 `.artifacts/过程文件-评测结果与审计/` 下按 `query/批次/阶段` 分组的目录；不得通过 `rm`、`unlink`、覆盖删除或清理脚本回收。
- `.artifacts/`、`screenshots-out/`、`reports/` 默认只作为用户本地产物保存，禁止 `git add`、`git add -f`、提交、推送或以其他方式上传；只有用户明确声明要上传这些产物时才可执行。运行评测、生成证据或生成报告本身不构成上传授权。
- 子代理 prompt 必须同样声明本纪律：只新增或保留文件；发现无效、重复或失败产物时记录原因与路径供审计，不得删除。

phase2 默认开启轻量识别；仅 `annotate=false` 显式跳过。`phase2Mode` 作为兼容参数固定为 `lightweight`；phase2 skill 目录由 `phase2SkillDir` 指定（默认 `projectDir/phase2-card-annotation`）。

---

## 控制体系（让任何人得到一致、准确输出）

本项目用 7 类控制手段叠加，覆盖「全局→按需→隔离→确定性→临时」全链路：

| 手段 | 位置 | 作用 | 生效时机 |
|---|---|---|---|
| CLAUDE.md（本文件） | 项目根 | 声明阶段/数据流/规范/契约 | Claude Code 全局、每会话 |
| AGENTS.md | 项目根 | 为 Codex 等通用 Agent 声明同一入口门禁与可移植前置入口 | 支持 AGENTS.md 的宿主、每会话 |
| Rules | `.claude/rules/*.md` | 按文件类型约束（SKILL.md 契约、命名/路径规范） | 按需：碰对应文件才加载，不碰不占 token |
| Subagents | `.claude/agents/*.md` | Screenshot Agent 负责截图/发现；Evaluation Agent 负责词级 Phase2～4，内部保留阶段职责定义 | 按任务模式和单词边界执行 |
| Hooks | `.claude/settings.json` | SKILL.md 编辑后自动校验 frontmatter（确定性） | 每次 Edit/Write SKILL.md 后 |
| Output Styles | `.claude/output-styles/eval-strict.md` | 评测模式人设，强制评级/计数/输出一致性 | 切到 eval-strict 模式时 |
| Skills | 项目 `phase*/SKILL.md` | 每个截图、识别、评测、报告与 NoCode 部署步骤的口径手册 | 工作流按路径读，或交互调用 |
| System Prompt Append | CLI `--append-system-prompt` | 一次性临时指令 | 单次调用 |

### 已落地
- **Rules**：`.claude/rules/skill-frontmatter.md`（SKILL.md frontmatter 契约）、`.claude/rules/project-conventions.md`（命名+路径+评级规范）。
- **Subagents**：`.claude/agents/screenshot-agent.md`（截图/外部图片复制/已有截图发现与未命名图身份解析）与 `.claude/agents/evaluation-agent.md`（Claude 薄绑定）；Claude、Codex、Catpaw 均复用唯一 `workflow/contracts/phase234-query-pipeline.md`（单词单实例、Phase2 候选→当前图复核→发布/定向纠错→Phase3～4）。Phase5 不是子 Agent，由批次屏障后的确定性脚本运行一次。Phase2 的候选提取只运行本地 CV；其受审计的当前像素校准可由多模态模型核对整图或有界裁图，但只能确认可见边界、类型、归属和原文，不能补写 OCR、注入黄金字段或做任何评测判断。
- **Hooks**：`.claude/settings.json` + `.claude/hooks/validate_skill_frontmatter.py`（编辑 SKILL.md 后自动校验四键，非阻断）。
- **Output Style**：`.claude/output-styles/eval-strict.md`。
- **运行入口**：`.claude/skills/run-eval.md`，以保守默认参数调用工作流。

### 已落地的运行前入口
- `workflow/eval_cli.py`：在没有 Workflow DSL 宿主的环境中完成外部截图直接复制、发现、唯一 run 任务生成与最终产物验收；它不伪装为可执行 LLM 评测器。接入方式见 `workflow/HOST_ADAPTER.md`。
- `phase1-screenshot/scripts/ingest_external_screenshots.py`：外部截图直接复制工具；保留原文件名，冲突不覆盖。

### 职责边界（不可由 LLM 替代）
- `phase2-card-annotation/scripts/validate_element_manifest.py` 是 Phase2 清单的确定性验收入口；Phase2 agent 只负责识别和产出清单，校验失败必须阻断 Phase3。
- `scripts/validate_eval_results.py` 是 Phase3 结果及 Phase4 证据的确定性验收入口；Phase3/Phase4 agent 不得以主观判断豁免缺失字段、计数冲突或证据缺失。
- 批次并发上限、单词隔离、同批屏障和失败重试由 Workflow/宿主编排强制保证；不得新增或依赖“批量调度 agent”自行协调。

---

## 命名与路径规范（铁律，详见 `.claude/rules/project-conventions.md`）

- 阶段目录一律 `phaseN-<role>`，不带 `-skill` 后缀：`phase1-screenshot`、`phase2-card-annotation`、`phase3-*-eval`、`phase4-issue-evidence`、`phase5-report`。
- 数据流：`screenshots/`（phase1 出/phase2 入，同时作为 Phase4 问题证据原图）→ `screenshots-out/`（phase2 清单；可选全量 PNG）→ `.artifacts/`（phase3 结果与 Phase4 原图引用）→ `reports/`（phase5 HTML；批量看板同时输出 `.governance_dataset_<批次>.json`）→ NoCode 线上看板（可选）。Phase4 不再写 `screenshots-out/evidence/`；**不得**用 `screenshots/annotated/` 或 skill 内部 `out/`。
- 场景脚本输入/输出必须用项目级绝对路径，不得写独立的 `Desktop/<旧名>/` 或 `meituan_search_screenshots_v2/`。
- 旧名 `screenshot-skill` / `report-skill` / 非前缀维度名已废弃，见到即视为待替换。

## SKILL.md frontmatter 契约（铁律，详见 `.claude/rules/skill-frontmatter.md`）

每个 `eval-*/SKILL.md` 必须含 `name/title/weight/aggregate` 四键（缺一则工作流发现/计分失败）：
- `weight` 键只能是 `优秀/达标/不达标`；两档制写 `{ "优秀": n, "不达标": n }`（省 `达标`），三档制三键齐全。**不得**用高线/中线/低线等别名。
- `aggregate` 必须写清：原始颗粒度如何评级 + 如何聚合到 Tab 级（取最差/求和/阈值）。
- `name` 用 kebab-case 且与目录名一致。
- 编辑 SKILL.md 后，`.claude/hooks/validate_skill_frontmatter.py` 钩子会自动校验四键。

## 评级分档

- 多数 eval skill 已两档（优秀/不达标，任一问题即不达标）；少数三档。两种都合法，由 `weight` 声明，工作流 schema 兼容（`达标` 可选）。
- 新增评测项默认两档，除非确需中间档。

## 一致性铁律（评测 phase 必守）

1. 每张截图对应的 Phase2 清单是对象库存、身份、语义、归属和计数的唯一结构化事实源；原图只负责叶子 Skill 明确声明的视觉判断或像素测量。`overview.total` 由各单图清单确定性计数后汇总，禁止各 skill 自行拆分、重数或跨图合并事实。
2. 评级只认 skill 的 weight 分档，不自创中间档。
3. 只评可见内容，截图外信息（落地页真实性、提示条准确性）不计入评级。
4. 逐组件给独立评级，不整屏笼统打分。

## 新增评测项 checklist

1. 在 `phase3-evaluation/dimensions/<dimension>/skills/eval-X-<name>/` 建 `SKILL.md`，frontmatter 四键齐全（参考 `.claude/rules/skill-frontmatter.md`），并登记到 `phase3-evaluation/catalog.json`。
2. 评级口径写在正文 + `aggregate`；两档制 `weight={ "优秀":n, "不达标":n }`。
3. 保存后看钩子输出 `[skill-frontmatter] OK`；若 FAIL 补齐再继续。
4. 工作流下次运行会从 catalog 发现，无需改 JS。
