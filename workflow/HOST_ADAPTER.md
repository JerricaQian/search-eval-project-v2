# 跨 Harness 最小接入

`workflow/meituan_eval_workflow.js` 是支持其 DSL 的宿主 adapter，不是通用执行器。
Claude Code、Codex、Catpaw 或其他 Harness 都使用同一个 `MEITUAN_EVAL_TASK` 和
`MEITUAN_AGENT_DISPATCH`，避免复制整段 Phase2～4 prompt。正式业务契约位于
`workflow/contracts/phase234-query-pipeline.md`；`.claude/agents/` 只保留 Claude
按名称加载的薄绑定。

## 1. 创建不可变任务

```bash
<pythonBin> workflow/eval_cli.py prepare-evaluate \
  --project-dir "<项目绝对路径>" \
  --source-dir "<外部截图目录>" \
  --query "<已确认的搜索词>" \
  --run-id "<本词唯一 runId>" \
  --batch-id "<本批共享 batchId>"
```

`<pythonBin>` 是当前 Harness 用于启动 CLI 的解释器；它会被写入 `workflowArgs.pythonBin`。

文件名不含搜索词、Tab、屏号时仍保留原名。无 `--query` 首次运行会返回 `awaiting_visual_identity_resolution` 和候选路径；宿主必须直接读取这些当前图片像素，生成 `screenshot.identity-map`，再把映射交回 CLI。文件名不得阻断，也不得要求用户先改名：

```bash
<pythonBin> workflow/eval_cli.py prepare-evaluate \
  --project-dir "<项目绝对路径>" \
  --source-dir "<外部截图目录>" \
  --identity-map "<宿主生成的身份映射 JSON>" \
  --selected-screenshot "<项目 screenshots/ 下的未命名文件绝对路径>"
```

身份映射遵守 `workflow/screenshot-identity.schema.json`，每项必须含 `sourcePath/sha256/query/tab/screen/identitySource/confidence`，其中自动识别使用 `identitySource=current_pixels`。CLI 会核验路径属于本次导入、当前字节 SHA 一致；一个映射含多个 query 时返回 `ready_for_query_task_split`，外层按词各建一个任务。若用户已经明确确认 query，也可以继续使用 `--query` + `--selected-screenshot`，该路径不依赖文件名。

必须在评测前通过 `--evaluation-selection` 显式冻结用户确认的评测范围，并通过 `--report-outlet` 明确用户是否要报告（`none`、`local_html` 或 `nocode`）；支持完整 19 项、按维度或自定义 Skill。例如：

```bash
<pythonBin> workflow/eval_cli.py prepare-evaluate \
  --project-dir "<项目绝对路径>" \
  --source-dir "<外部截图目录>" \
  --query "<已确认的搜索词>" \
  --evaluation-selection '{"mode":"custom_skills","skills":[{"dimension":"phase3-card_or_component-eval","skill":"eval-7-info-authenticity"}]}' \
  --report-outlet local_html
```

只要用户选择报告，任何已确认范围的批次都可生成治理报告；报告与数据集必须明确显示已执行范围，不能暗示完成完整 19 项。

输出中的 `portableTask.taskPath` 是唯一要交给 Harness 的任务入口；其中已有唯一
`runId`、隔离后的 `batchId/tag/rerunId`、截图路径、契约路径和回执命令。可用
`--run-id <稳定标识>` 复现一次指定运行；已存在的 run id 会失败而不会覆盖历史产物。
`workflowArgs.pythonBin` 是创建任务时实际运行 CLI 的解释器；Harness 必须原样传入并用它
执行所有 Python 脚本，不假定项目 `.venv`、`python3` 别名或 macOS 工具存在。

## 2. 统一生成派发信封

所有宿主在启动 Agent 前运行同一条命令，并只声明自己实际具备的能力：

```bash
<pythonBin> workflow/eval_cli.py prepare-dispatch \
  --task "<taskPath>" --host <claude|codex|catpaw|generic> \
  --capability readImagePixels --capability readFiles \
  --capability runCommands --capability writeJson
```

输出固定为 `MEITUAN_AGENT_DISPATCH`，其中 `input.mode=task_path_only`。Claude
输出中的 `binding.mode=native_agent_definition` 允许继续使用
`.claude/agents/evaluation-agent.md`；Codex、Catpaw 和 generic 使用
`binding.mode=portable_task`，由各自宿主的子 Agent API 启动。除这个启动动作外，
三者收到相同的 taskPath、prompt、能力门禁、resultPath 和 completionCommand。

不传 `--capability` 时只返回 `awaiting_capability_confirmation`，不宣称可以执行；
只声明部分能力时返回 `blocked_preflight` 和 `missingCapabilities`。能力齐全后还会
读取 `active_validation_contracts.v3.json`，核验选中 Skill 与当前校验器的版本化
快照；不匹配时返回 `blocked_contract_drift` 和 `contractPreflight.errors`，不得派发
Agent、重跑截图或消耗词级评测重试次数。适配器不得把未实际具备的能力写入命令。

## 3. Harness 只做一件事

先确认宿主实际具备读图、读文件、运行命令和写 JSON 权限。新建 `MEITUAN_EVAL_TASK` 的 `requiredCapabilities` 是强制预检；无法读取图像像素时写 `blockedAt=preflight`、`error=model_vision_not_supported`，不要派发 Phase2。任务还冻结 Phase2 发布所用的 Skill、卡型/归属契约与关键脚本哈希；`prepare-dispatch` 和正式清单提升都会复核这些哈希。并发期间共享逻辑变动时应保留旧尝试，待版本稳定后创建新隔离任务，不得让同一任务混用两个判定版本。

`prepare-dispatch` 返回 `ready_for_dispatch` 后，让一个 Evaluation Agent：

1. 读取 `<taskPath>`，再读取其中 `contractFiles`；
2. 对 `workflowArgs.query` 完整执行 Phase2 → Phase3 → Phase4；Stage D 只返回空交接对象；
3. 把最终 JSON 写到 `resultPath`，不把长契约复制进新的子 Agent prompt；
4. 执行 task 中的 `completionCommand`。

若 Harness 能执行 Workflow DSL，可直接把 `workflowArgs` 传给
`workflow/meituan_eval_workflow.js`，并将返回对象中的 `evaluationResult` 写到 `resultPath` 后执行
同一条 completion command。

## 4. 只认可本地回执

`finalize-evaluate` 会拒绝：缺失 Stage A～D、`ok=true` 但 Phase2～4 产物不完整、审计 JSON
不是 `valid=true`、空文件、项目外路径或重复的成功写入。成功时创建一次性的
`runs/<runId>/receipt.json`；阻断结果也会有可追溯回执。若同一任务在完成返工后由
`blocked` 变为 `completed`，工具会将旧回执保留为 `receipt.blocked-<stage>.json`，再写入
新的成功回执；已完成回执绝不覆盖。

这层不做 OCR 或视觉判断。批次重试由 `prepare-batch`、`advance-batch` 和 `create-batch-retry` 保存为追加式状态快照；每次重试都有新的 `runId/taskPath`，不会覆盖失败产物。

若评测完成后需要规范名称，运行 `workflow/materialize_screenshot_aliases.py`，同时传入 completed `receipt.json`，把身份映射物化为独立规范副本和 `screenshot.canonical-alias-map`。脚本在没有完成回执时拒绝运行，且永不移动、覆盖或删除原始 `IMG_*.PNG`；Tab/屏号仍不确定的条目保持原名并记录 skipped，不猜写。

## 5. 全部词终态后统一生成 Phase5

当确认选中的截图总数超过 3 张时，先用 `prepare-batch` 冻结所有预期 task，并按搜索词下发 Evaluation Agent。阈值按身份映射完成后的 `selectedScreenshots` 总数计算；一个 Agent 处理一个词的全部截图，最多并发 3 个。3 张及以下不因图片数量本身强制下发子代理。先让全部初次任务按并发上限完成派发并取得终态回执，再用 `advance-batch` 统一核验；未派发、运行中或尚无回执的任务保持 `pending/awaiting_receipts`，不计失败且不消耗隔离重试次数。只有词级任务写回明确的非 completed 终态回执，才通过 `create-batch-retry` 生成新的隔离任务并交给新的 Evaluation Agent，最多三次；第三次仍失败标记 abandoned。所有词进入 completed/abandoned 后执行一次：

```bash
<pythonBin> workflow/eval_cli.py finalize-batch \
  --project-dir "<项目绝对路径>" \
  --batch-id "<本批共享 batchId>" \
  --batch-state "<advance-batch 返回的最新 statePath>"
```

该命令重新核验每份最终契约结果及本地回执，只把 completed 回执中的精确 manifest 和评测结果交给确定性生成器。Phase5 仅依据当前截图可见商卡的语义与履约标识推导业务 Tab，不读取搜索词或任务时预设 Tab；可选 `--expected-business-tabs` 只可作为最终集合断言。随后生成一份批量 HTML 与一份治理数据集。abandoned 词仅保留在批次状态中，不进入报告；尚未终态会阻断，全部 abandoned 也不会生成空报告。
