export const meta = {
  name: 'meituan-search-eval',
  description: '美团搜索结果页：按需截图、词级 Phase2/3/4，以及带失败重派和 Phase5 屏障的批次评测',
  phases: [
    { title: '① Screenshot Agent', detail: 'ADB现场截图，或只读发现已有截图' },
    { title: '② Phase3 评测官解析范围', detail: '按用户选择确定性解析完整19项、维度或自定义 eval skill' },
    { title: '③ Phase2+3+4 词级评测', detail: '单图本地识别→多维度评测→问题证据，三个阶段在同一子代理内顺序完成' },
    { title: '④ Manifest 质量侧审计', detail: '可选：单图元素清单 L1/L2/L3 合规率统计，仅记录不阻断' },
    { title: '⑤ 批次屏障与 Phase5', detail: '失败词最多三次隔离重派；全部预期词终态后生成唯一总报告' },
  ],
}

// ---------- 参数 ----------
let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
if (!A || typeof A !== 'object') A = {}
log('args=' + JSON.stringify(A))

// ---------- 批次入口：跨词调度、隔离重试、终态 Phase5 ----------
// 单词模式仍由下方原流程处理。批次模式接收 prepare-evaluate 已生成的初始 taskPath，
// 已选截图超过 3 张时，必须按搜索词下发 Evaluation Agent；每轮最多并发 3 个。
// batch_evaluate 是该词级调度入口；每个词最多派发 3 次且每次使用全新 runId。
if (A.mode === 'batch_evaluate') {
  if (!A.projectDir || typeof A.projectDir !== 'string') throw new Error('batch_evaluate 必须显式传入 projectDir')
  const batchProjectDir = A.projectDir.replace(/\/+$/, '')
  const batchPythonBin = typeof A.pythonBin === 'string' && A.pythonBin.trim() ? A.pythonBin.trim() : 'python3'
  const batchId = typeof A.batchId === 'string' ? A.batchId.trim() : ''
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(batchId)) throw new Error('batchId 格式非法')
  const initialTaskPaths = Array.isArray(A.taskPaths) ? A.taskPaths : []
  if (!initialTaskPaths.length || !initialTaskPaths.every(path => typeof path === 'string' && path.startsWith(batchProjectDir + '/') && !/[\r\n]/.test(path))) {
    throw new Error('taskPaths 必须是项目目录内的非空绝对路径数组')
  }
  if (new Set(initialTaskPaths).size !== initialTaskPaths.length) throw new Error('taskPaths 不得重复')
  const expectedBusinessTabs = Array.isArray(A.expectedBusinessTabs)
    ? A.expectedBusinessTabs.join(',')
    : (typeof A.expectedBusinessTabs === 'string' ? A.expectedBusinessTabs.trim() : '')
  // This is only an optional post-evaluation assertion. Phase5 derives the
  // actual business tabs from each accepted card's visible semantics and
  // fulfilment facts; never from a query or a task-time tab preset.
  const maxQueryAttempts = A.maxQueryAttempts == null ? 3 : A.maxQueryAttempts
  if (maxQueryAttempts !== 3) throw new Error('maxQueryAttempts 固定为 3；同一词最多派发 3 次')

  const shellArg = value => "'" + String(value).replace(/'/g, "'\"'\"'") + "'"
  const batchOptions = options => A.model ? { ...options, model: A.model } : options
  const CONTROL_SCHEMA = {
    type: 'object',
    properties: {
      ok: { type: 'boolean' }, batchId: { type: 'string' }, statePath: { type: 'string' },
      status: { type: 'string' }, dispatchTasks: { type: 'array', items: { type: 'string' } },
      completedQueries: { type: 'array', items: { type: 'string' } },
      retryQueries: { type: 'array', items: { type: 'string' } },
      failedQueries: { type: 'array', items: { type: 'string' } },
      subagentPolicy: { type: 'object' },
      readyForPhase5: { type: 'boolean' }, error: { type: 'string' },
    },
    required: ['ok'],
  }
  const RETRY_SCHEMA = {
    type: 'object',
    properties: {
      ok: { type: 'boolean' }, batchId: { type: 'string' }, query: { type: 'string' },
      attempt: { type: 'number' }, taskPath: { type: 'string' }, runId: { type: 'string' },
      statePath: { type: 'string' }, error: { type: 'string' },
    },
    required: ['ok'],
  }
  const DISPATCH_SCHEMA = {
    type: 'object',
    properties: {
      ok: { type: 'boolean' }, query: { type: 'string' }, taskPath: { type: 'string' },
      receiptPath: { type: 'string' }, status: { type: 'string' }, blockedAt: { type: 'string' }, error: { type: 'string' },
    },
    required: ['ok', 'query', 'taskPath', 'receiptPath', 'status', 'blockedAt', 'error'],
  }
  const PHASE5_SCHEMA = {
    type: 'object',
    properties: {
      ok: { type: 'boolean' }, batchId: { type: 'string' }, queries: { type: 'array' },
      plannedQueries: { type: 'array' }, skippedTasks: { type: 'array' }, reportPath: { type: 'string' },
      datasetPath: { type: 'string' }, reportOutlet: { type: 'string' }, phase5: { type: 'object' }, error: { type: 'string' },
    },
    required: ['ok'],
  }

  const runControlCommand = async (label, command, schema) => agent(
    `你是批次控制命令执行器。只运行下面这一条确定性命令；即使命令退出码非零，也要解析 stdout JSON 并原样按 schema 返回，不做评测、不修改返回字段：\n\n${command}`,
    batchOptions({ label, phase: '批次控制', schema }),
  )

  phase('批次初始化')
  const prepareCommand = [
    shellArg(batchPythonBin), shellArg(batchProjectDir + '/workflow/eval_cli.py'), 'prepare-batch',
    '--project-dir', shellArg(batchProjectDir), '--batch-id', shellArg(batchId),
    '--max-query-attempts', String(maxQueryAttempts),
    ...initialTaskPaths.flatMap(path => ['--task', shellArg(path)]),
  ]
  if (expectedBusinessTabs) prepareCommand.push('--expected-business-tabs', shellArg(expectedBusinessTabs))
  const prepared = await runControlCommand('冻结批次任务', prepareCommand.join(' '), CONTROL_SCHEMA)
  if (!prepared || prepared.ok !== true || !prepared.statePath || !Array.isArray(prepared.dispatchTasks)) {
    throw new Error('批次初始化失败: ' + (prepared && prepared.error ? prepared.error : '控制器无有效返回'))
  }

  let statePath = prepared.statePath
  let dispatchTasks = prepared.dispatchTasks
  const subagentPolicy = prepared.subagentPolicy || {}
  log('子代理阈值：已选截图 ' + (subagentPolicy.selectedScreenshotCount ?? '未知') + ' 张；'
    + (subagentPolicy.requiresQuerySubagents ? '必须按词级子代理调度' : '不因图片数本身强制下发')
    + '；单 Agent 单词，最多并发 ' + (subagentPolicy.maxParallelAgents || 3) + ' 个')
  let completedQueries = []
  let abandonedQueries = []
  for (let wave = 1; wave <= maxQueryAttempts; wave += 1) {
    phase('词级评测·第' + wave + '轮')
    log('第' + wave + '轮派发 ' + dispatchTasks.length + ' 个词级任务；每组最多 3 个并发')
    for (let offset = 0; offset < dispatchTasks.length; offset += 3) {
      const chunk = dispatchTasks.slice(offset, offset + 3)
      await parallel(chunk.map(taskPath => () => agent(
        `你是本轮全新的 Evaluation Agent。唯一输入是 taskPath：\n${taskPath}\n\n先读取 task JSON，确认 requiredCapabilities，再完整读取 contractFiles 与 requiredReads；严格执行 Phase2→Phase3→Phase4，将最终结果写入 resultPath，并执行 completionCommand。成功或阻断都必须产生 receipt.json。最后只返回本次任务的 query、taskPath、receiptPath、status、blockedAt、error；不得执行 Phase5。`,
        batchOptions({ label: 'Evaluation Agent:' + taskPath.split('/').slice(-2, -1)[0], phase: '词级评测', schema: DISPATCH_SCHEMA, agentType: 'evaluation-agent' }),
      )))
    }

    const advanceCommand = [
      shellArg(batchPythonBin), shellArg(batchProjectDir + '/workflow/eval_cli.py'), 'advance-batch', '--state', shellArg(statePath),
    ].join(' ')
    const advanced = await runControlCommand('核验第' + wave + '轮回执', advanceCommand, CONTROL_SCHEMA)
    if (!advanced || !advanced.statePath) throw new Error('批次回执核验失败: ' + (advanced && advanced.error ? advanced.error : '控制器无有效返回'))
    statePath = advanced.statePath
    completedQueries = advanced.completedQueries || []
    if (advanced.readyForPhase5 === true) {
      abandonedQueries = advanced.failedQueries || []
      dispatchTasks = []
      break
    }
    if (advanced.status === 'failed' || (advanced.failedQueries || []).length) {
      return {
        mode: 'batch_evaluate', status: 'failed', batchId, statePath,
        completedQueries, failedQueries: advanced.failedQueries || [], reportPath: '', datasetPath: '',
        error: '全部搜索词均连续失败 ' + maxQueryAttempts + ' 次；没有可用于 Phase5 的完成结果',
      }
    }

    dispatchTasks = []
    const retryQueries = advanced.retryQueries || []
    for (let index = 0; index < retryQueries.length; index += 1) {
      const query = retryQueries[index]
      const retryRunId = batchId.slice(0, 58) + '.a' + (wave + 1) + '.q' + (index + 1)
      const retryCommand = [
        shellArg(batchPythonBin), shellArg(batchProjectDir + '/workflow/eval_cli.py'), 'create-batch-retry',
        '--state', shellArg(statePath), '--query', shellArg(query), '--run-id', shellArg(retryRunId),
      ].join(' ')
      const retried = await runControlCommand('创建隔离重试:' + query, retryCommand, RETRY_SCHEMA)
      if (!retried || retried.ok !== true || !retried.taskPath || !retried.statePath) {
        throw new Error('无法为失败词创建隔离重试任务: ' + query + ' ' + (retried && retried.error ? retried.error : ''))
      }
      statePath = retried.statePath
      dispatchTasks.push(retried.taskPath)
    }
  }

  if (dispatchTasks.length) {
    return {
      mode: 'batch_evaluate', status: 'failed', batchId, statePath,
      completedQueries, failedQueries: [], reportPath: '', datasetPath: '',
      error: '达到词级派发上限；正式 Phase5 未生成',
    }
  }

  phase('Phase5 总报告')
  const finalizeCommand = [
    shellArg(batchPythonBin), shellArg(batchProjectDir + '/workflow/eval_cli.py'), 'finalize-batch',
    '--project-dir', shellArg(batchProjectDir), '--batch-id', shellArg(batchId), '--batch-state', shellArg(statePath),
  ]
  if (expectedBusinessTabs) finalizeCommand.push('--expected-business-tabs', shellArg(expectedBusinessTabs))
  const finalReport = await runControlCommand('Phase5 唯一总报告', finalizeCommand.join(' '), PHASE5_SCHEMA)
  if (!finalReport || finalReport.ok !== true) {
    throw new Error('Phase5 生成失败: ' + (finalReport && finalReport.error ? finalReport.error : '控制器无有效返回'))
  }
  return {
    mode: 'batch_evaluate', status: 'completed', batchId, statePath,
    completedQueries: finalReport.queries, failedQueries: abandonedQueries,
    skippedTasks: finalReport.skippedTasks || [],
    reportPath: finalReport.reportPath, datasetPath: finalReport.datasetPath,
    reportOutlet: finalReport.reportOutlet, phase5: finalReport.phase5,
  }
}

log('单词调度纪律：当前实例只处理 1 个搜索词；多词任务请使用 batch_evaluate。')

// 1.0 对外任务模式。未传 mode 时保留旧参数语义：skipScreenshot=false
// 表示截图后评测，其余旧调用仍按“复用已有截图后评测”执行。
const VALID_MODES = ['capture_only', 'evaluate_only', 'capture_and_evaluate']
const mode = A.mode || (A.skipScreenshot === false ? 'capture_and_evaluate' : 'evaluate_only')
if (!VALID_MODES.includes(mode)) {
  throw new Error('mode 只允许 ' + VALID_MODES.join('/') + '，收到: ' + mode)
}
const selectedScreenshots = A.selectedScreenshots || []
if (!Array.isArray(selectedScreenshots) || !selectedScreenshots.every(item => typeof item === 'string' && item.trim())) {
  throw new Error('selectedScreenshots 必须是非空绝对路径字符串数组；仅评测已有截图时由截图发现结果填入')
}
if (!A.projectDir) throw new Error('必须显式传入 projectDir（项目根绝对路径），不再提供兜底默认值')
const projectDir = A.projectDir
// 可移植任务由 eval_cli 注入实际解释器；旧 DSL 调用保留 python3 作为唯一兼容默认值。
const pythonBin = typeof A.pythonBin === 'string' && A.pythonBin.trim() ? A.pythonBin.trim() : 'python3'
const screenshotDir = (A.screenshotDir ? A.screenshotDir : projectDir + '/screenshots')
const externalScreenshotDir = typeof A.externalScreenshotDir === 'string' ? A.externalScreenshotDir.trim() : ''
if (externalScreenshotDir && mode !== 'evaluate_only') {
  throw new Error('externalScreenshotDir 只适用于 evaluate_only；现场截图请使用 capture_only 或 capture_and_evaluate')
}

function isProjectScreenshot(path) {
  const normalizedRoot = screenshotDir.replace(/\/+$/, '') + '/'
  return path.startsWith(normalizedRoot)
}
if (mode === 'evaluate_only' && selectedScreenshots.length && !selectedScreenshots.every(isProjectScreenshot)) {
  throw new Error('项目外截图必须先复制到项目 screenshots/，再通过发现结果选择；不直接评测项目外路径')
}

function inferQueryFromScreenshots(paths) {
  const queries = paths.map(path => {
    const filename = path.split('/').pop().replace(/\.[^.]+$/, '')
    const parts = filename.split('_')
    if (parts.length < 3 || !/^\d+$/.test(parts[parts.length - 1])) return ''
    return parts.slice(0, -2).join('_').trim()
  }).filter(Boolean)
  return queries.length && queries.every(value => value === queries[0]) ? queries[0] : ''
}

const suppliedIdentityMap = A.screenshotIdentityMap && typeof A.screenshotIdentityMap === 'object'
  ? A.screenshotIdentityMap : null

function inferQueryFromIdentityMap(paths, identityMap) {
  if (!identityMap || identityMap.contract !== 'screenshot.identity-map' || !Array.isArray(identityMap.entries)) return ''
  const selected = new Set(paths)
  const entries = identityMap.entries.filter(item => item && selected.has(item.sourcePath))
  const queries = entries.map(item => typeof item.query === 'string' ? item.query.trim() : '').filter(Boolean)
  return entries.length === paths.length && queries.length && queries.every(value => value === queries[0]) ? queries[0] : ''
}

let query = (typeof A.query === 'string' ? A.query.trim() : '')
if (!query && selectedScreenshots.length) query = inferQueryFromIdentityMap(selectedScreenshots, suppliedIdentityMap)
if (!query && selectedScreenshots.length) query = inferQueryFromScreenshots(selectedScreenshots)

const COPY_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    copied: { type: 'array' },
    alreadyPresent: { type: 'array' },
    renamed: { type: 'array' },
    error: { type: 'string' },
  },
  required: ['ok', 'copied', 'alreadyPresent', 'renamed', 'error'],
}

let copySummary = null
if (mode === 'evaluate_only' && externalScreenshotDir) {
  phase('复制外部截图')
  const copyPrompt = `你是 screenshot-agent。把用户指定的外部图片或目录直接复制到项目 screenshots；绝不修改、移动、删除或重命名源文件，也不生成 Intake manifest 或规范化副本名。

执行：
\`\`\`bash
"${pythonBin}" "${projectDir}/phase1-screenshot/scripts/ingest_external_screenshots.py" \\
  --source-dir "${externalScreenshotDir}" \\
  --screenshot-dir "${screenshotDir}"
\`\`\`

脚本按原文件名复制。若目标同名但字节不同，脚本追加递增的“副本”序号并在 renamed 中记录；不会覆盖或阻断。图片有效性、命名可解析性与分组由之后的发现阶段输出，不在复制阶段阻断。把 stdout 的 copied、alreadyPresent、renamed 数组原样填回 schema，不要自行挑选截图或评测。`
  const copyResult = await agent(copyPrompt, withRequestedModel({
    label: '复制外部截图',
    phase: '复制外部截图',
    agentType: 'screenshot-agent',
    schema: COPY_SCHEMA,
  }))
  if (!copyResult || !copyResult.ok) {
    throw new Error('外部截图复制失败: ' + (copyResult && copyResult.error ? copyResult.error : 'agent 无返回'))
  }
  copySummary = copyResult
}

// “仅评测已有截图”的第一轮调用不要求用户输入搜索词/Tab/屏数。调用方可先用
// discoveryOnly=true 获得可选分组，再将用户选中的 files 作为 selectedScreenshots 发起评测。
if (mode === 'evaluate_only' && (A.discoveryOnly === true || selectedScreenshots.length === 0)) {
  phase('发现已有截图')
  const discoveryPrompt = `你是 screenshot-agent。只读扫描已有截图，不连接设备、不修改任何文件。用 Bash 执行：
\`\`\`bash
"${pythonBin}" "${projectDir}/phase1-screenshot/scripts/discover_screenshot_groups.py" --screenshot-dir "${screenshotDir}"
\`\`\`
将 stdout JSON 原样映射到 schema 返回。`
  const discoveryResult = await agent(discoveryPrompt, withRequestedModel({
    label: '发现已有截图',
    phase: '发现已有截图',
    agentType: 'screenshot-agent',
    schema: {
      type: 'object',
      properties: {
        screenshotDir: { type: 'string' },
        groups: { type: 'array' },
        unlabeledGroups: { type: 'array' },
        unnamedFiles: { type: 'array' },
        invalidFiles: { type: 'array' },
        unparseableFiles: { type: 'array' },
        error: { type: 'string' },
      },
      required: ['screenshotDir', 'groups', 'unlabeledGroups', 'unnamedFiles', 'invalidFiles', 'unparseableFiles', 'error'],
    },
  }))
  const unlabeledGroups = (discoveryResult && discoveryResult.unlabeledGroups) || []
  const unnamedPaths = unlabeledGroups.flatMap(group => Array.isArray(group.files) ? group.files : [])
  let identityResult = null
  if (unnamedPaths.length && A.resolveUnnamedIdentities !== false) {
    const identityPrompt = `你是截图身份识别 Agent，只执行 Phase1 身份解析，不做 Phase2 事实标注或任何评分。逐张读取以下当前图片像素：
${unnamedPaths.map(path => '- ' + path).join('\n')}

对每张图提取当前搜索框/结果页可见的 query，并在可可靠判断时提取 Tab 和屏号；运行 shasum -a 256 获取当前文件哈希。文件名不得作为阻断条件。每张返回 sourcePath、sha256、query、tab、screen、identitySource="current_pixels"、confidence。只有当前像素确实无法确定 query 时放入 unresolved，并写原因；不得猜测或按视觉相似性合并。`
    identityResult = await agent(identityPrompt, withRequestedModel({
      label: '未命名截图身份识别',
      phase: '截图身份识别',
      agentType: 'screenshot-agent',
      schema: {
        type: 'object',
        properties: {
          ok: { type: 'boolean' },
          contract: { type: 'string' },
          entries: { type: 'array' },
          unresolved: { type: 'array' },
          error: { type: 'string' },
        },
        required: ['ok', 'contract', 'entries', 'unresolved', 'error'],
      },
    }))
  }
  const resolvedEntries = identityResult && Array.isArray(identityResult.entries) ? identityResult.entries : []
  const resolvedQueries = [...new Set(resolvedEntries.map(item => item && item.query).filter(Boolean))]
  return {
    mode,
    status: resolvedEntries.length ? 'ready_for_query_task_split' : (unnamedPaths.length ? 'awaiting_visual_identity_resolution' : 'awaiting_screenshot_selection'),
    discoveredGroups: (discoveryResult && discoveryResult.groups) || [],
    unlabeledGroups,
    unnamedFiles: (discoveryResult && discoveryResult.unnamedFiles) || [],
    screenshotIdentityMap: resolvedEntries.length ? { contract: 'screenshot.identity-map', entries: resolvedEntries } : null,
    resolvedQueries,
    unresolvedIdentities: (identityResult && identityResult.unresolved) || [],
    invalidFiles: (discoveryResult && discoveryResult.invalidFiles) || [],
    unparseableFiles: (discoveryResult && discoveryResult.unparseableFiles) || [],
    copy: copySummary,
    error: (discoveryResult && discoveryResult.error) || '',
  }
}
if (!query) {
  throw new Error(mode === 'evaluate_only'
    ? '无法从 selectedScreenshots 推导唯一搜索词；请先 discoveryOnly=true 发现截图并选择同一搜索词，或由调用方传入推导出的 query'
    : '自动化截图模式必须显式传入非空字符串 query')
}

// 模型名属于宿主 adapter，不属于评测协议。未传 model 时让宿主使用其默认的可读图模型；
// adapter 必须在实际派发前确认该模型能读图并能返回结构化 JSON。
function withRequestedModel(options) {
  return A.model ? { ...options, model: A.model } : options
}
// 批量编排铁律：外层调用方必须把搜索词切为单词任务；每批最多 3 个词级子代理，
// 必须等待本批完成再派下一批。当前工作流实例只接受并处理一个 query，绝不在内部混跑多词。
const MAX_QUERY_AGENTS_PER_BATCH = 3
const SINGLE_QUERY_PER_AGENT = true

// 此工作流是严格的单词执行单元。批量词必须由外层调度器切分为独立实例，
// 依次按每批最多 3 个实例运行并等待批次屏障；不得把 queries 直接注入本实例。
if (Array.isArray(A.queries)) {
  throw new Error('当前工作流只接受单个 query；请由外层调度器将 queries 切分为单词任务（每批最多 3 个，等待整批完成后再派下一批）')
}
const tabs = A.tabs ? A.tabs : ['全部', '外卖', '团购']
const screens = A.screens ? A.screens : ['1', '2', '3']
// capture_only 必定现场截图；仅评测已有截图必定禁止启动截图脚本。
// 截图+评测模式默认现场截图；旧调用未传 mode 时仍由上方 mode 推导保持原有语义。
const skipScreenshot = mode === 'evaluate_only' ? true : (mode === 'capture_only' ? false : A.skipScreenshot === true)
// Phase3 由评测官按用户选择路由。保留 dimensions 仅作旧调用兼容；新调用使用
// evaluationSelection: {mode: full_19|dimensions|custom_skills, ...}。
const CANONICAL_EVAL_DIMENSIONS = [
  'phase3-single_element-eval',
  'phase3-card_or_component-eval',
  'phase3-page_framework-eval',
]
const SELECTION_IDENTIFIER = /^[a-z0-9][a-z0-9_-]*$/
let legacyDimensions = A.dimensions ? A.dimensions : ['phase3-card_or_component-eval']
if (typeof legacyDimensions === 'string') legacyDimensions = [legacyDimensions]
if (!Array.isArray(legacyDimensions) || !legacyDimensions.every(value => typeof value === 'string' && SELECTION_IDENTIFIER.test(value))) {
  throw new Error('dimensions 必须是合法 phase3 维度目录名数组')
}
let evaluationSelection = A.evaluationSelection
if (typeof evaluationSelection === 'string') {
  try { evaluationSelection = JSON.parse(evaluationSelection) } catch (error) {
    throw new Error('evaluationSelection 字符串必须是合法 JSON：' + error.message)
  }
}
if (evaluationSelection == null) {
  throw new Error('evaluationSelection 必须在评测前由用户确认；不得使用默认维度')
}
const legacySelectionFallback = false
if (!evaluationSelection || typeof evaluationSelection !== 'object' || Array.isArray(evaluationSelection)) {
  throw new Error('evaluationSelection 必须是对象，mode 为 full_19、dimensions 或 custom_skills')
}
if (!['full_19', 'dimensions', 'custom_skills'].includes(evaluationSelection.mode)) {
  throw new Error('evaluationSelection.mode 只允许 full_19/dimensions/custom_skills')
}
if (evaluationSelection.mode === 'dimensions' && (!Array.isArray(evaluationSelection.dimensions) || !evaluationSelection.dimensions.length ||
    !evaluationSelection.dimensions.every(value => typeof value === 'string' && SELECTION_IDENTIFIER.test(value)))) {
  throw new Error('evaluationSelection.dimensions 必须是非空合法维度目录名数组')
}
if (evaluationSelection.mode === 'custom_skills' && (!Array.isArray(evaluationSelection.skills) || !evaluationSelection.skills.length ||
    !evaluationSelection.skills.every(item => item && typeof item === 'object' && typeof item.dimension === 'string' &&
      SELECTION_IDENTIFIER.test(item.dimension) && typeof item.skill === 'string' && SELECTION_IDENTIFIER.test(item.skill)))) {
  throw new Error('evaluationSelection.skills 必须是非空 {dimension,skill} 数组')
}
// 仅用于产物命名；真实 targets 由 resolver 在 Phase2b 确定性返回。
let dimensions = evaluationSelection.mode === 'full_19'
  ? [...CANONICAL_EVAL_DIMENSIONS]
  : evaluationSelection.mode === 'dimensions'
    ? [...evaluationSelection.dimensions]
    : [...new Set(evaluationSelection.skills.map(item => item.dimension))]
// Phase2 只允许轻量识别，并为每张截图产出一个独立 JSON。annotate=false 才显式跳过。
const annotate = A.annotate === false ? false : true
const skipAnnotation = !annotate
const phase2Mode = A.phase2Mode ? A.phase2Mode : 'lightweight'
if (phase2Mode !== 'lightweight') throw new Error('phase2Mode 当前只允许 lightweight；Phase2 不再生成整页标注图，收到: ' + phase2Mode)
const annotateScenes = A.annotateScenes ? A.annotateScenes : []
if (!Array.isArray(annotateScenes)) throw new Error('annotateScenes 必须是截图绝对路径数组')
if (annotateScenes.length) throw new Error('annotateScenes 已停用：Phase2 必须为本轮每张 screenshots 输入分别生成 manifest')
// granularity：Phase3 三个维度都以统一最小元素清单为单一事实源；合并后的 phase234-query-pipeline agent
// 固定按元素级契约（七键单图清单/regions/elements）执行，不再支持 component/region 颗粒度。
const granularity = A.granularity ? A.granularity : 'element'
if (granularity !== 'element') throw new Error('当前标准工作流只接受 granularity=element；组件/卡片与页面框架评测也必须消费同一份最小元素清单，再按各 Skill 聚合')
const enableAnnotationAudit = A.enableAnnotationAudit !== false
// reportOutlet 必须在评测前由用户确认；词级 Evaluation Agent 不生成报告。
const reportOutlet = typeof A.reportOutlet === 'string' ? A.reportOutlet.trim() : ''
if (!['none', 'local_html', 'nocode'].includes(reportOutlet)) {
  throw new Error('reportOutlet 必须由用户确认，只允许 none/local_html/nocode，收到: ' + (reportOutlet || 'missing'))
}
// 可移植前门会提供 runId，并把它复用为 batch/tag/rerun，保证同词并发不共用产物。
// 旧调用仍可不传 runId，但会保留旧目录语义并在日志中明确提示风险。
const runId = typeof A.runId === 'string' ? A.runId.trim() : ''
if (runId && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(runId)) {
  throw new Error('runId 只允许 1-80 位字母数字、点、下划线或连字符，且必须以字母数字开头')
}
if (!runId) log('未提供 runId：将使用旧版共享输出路径；并发或重试可能冲突。请通过 workflow/eval_cli.py prepare-evaluate 创建可移植任务。')
// tag：同一截图需要保留不同批次识别时作为单图 manifest 后缀；截图文件名本身用于区分多图。
const tag = A.tag ? A.tag : runId
const tagSuffix = tag ? '_' + tag : ''

// annotatedDir：Phase2 单图元素清单输出目录；Phase2 不生成整页标注 PNG。
const annotatedDir = (A.annotatedDir ? A.annotatedDir : projectDir + '/screenshots-out')
// 过程文件与最终 HTML 分离：报告目录只放交付物，评测原始结果和审计记录归档到易识别的过程文件目录。
// 过程产物只追加保留，禁止删除、unlink 或覆盖清理；无效/失败文件也必须保留并记录路径。
const evaluationArtifactDir = projectDir + '/.artifacts/过程文件-评测结果与审计'
const batchId = A.batchId ? A.batchId : (runId || '单词运行')
// rerunId 由调用方显式传入，以在同一批次多轮返工时保留独立审计；缺省时复用稳定 batchId，禁止依赖时间或随机数。
const rerunId = A.rerunId ? A.rerunId : (runId || batchId)
const batchArtifactDir = evaluationArtifactDir + '/' + batchId
const artifactRunDir = batchArtifactDir + '/' + query + tagSuffix
const dimSlug = dimensions.map(d => d.replace(/^phase3-/, '').replace(/-eval$/, '')).join('_')
const shotSkillDir = (A.shotSkillDir ? A.shotSkillDir : projectDir + '/phase1-screenshot')
const phase2SkillDir = (A.phase2SkillDir ? A.phase2SkillDir : projectDir + '/phase2-card-annotation')
const issueEvidenceSkillDir = (A.issueEvidenceSkillDir ? A.issueEvidenceSkillDir : projectDir + '/phase4-issue-evidence')
const phase3SkillDir = projectDir + '/phase3-evaluation'

// ---------- schemas ----------
const SHOT_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    screenshots: { type: 'array', items: { type: 'string' } },
    missing: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['ok', 'screenshots'],
}
const EVAL_TARGET_RESOLUTION_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    selection: { type: 'object' },
    legacyDimensionsFallback: { type: 'boolean' },
    dimensions: { type: 'array', items: { type: 'string' } },
    evalTargets: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          dimension: { type: 'string' },
          skill: { type: 'string' },
          title: { type: 'string' },
          weight: {
            type: 'object',
            properties: {
              '优秀': { type: 'number' },
              '达标': { type: 'number' },
              '不达标': { type: 'number' },
            },
            required: ['优秀', '不达标'],
          },
          aggregate: { type: 'string' },
          extra: { type: 'string' },
          skillPath: { type: 'string' },
          skillsDir: { type: 'string' },
          contractPath: { type: 'string' },
        },
        required: ['dimension', 'skill', 'title', 'weight', 'aggregate', 'extra', 'skillPath', 'skillsDir', 'contractPath'],
      },
    },
    coverage: {
      type: 'object',
      properties: {
        selectedCount: { type: 'number' },
        fullCount: { type: 'number' },
        isFull: { type: 'boolean' },
        label: { type: 'string' },
      },
      required: ['selectedCount', 'fullCount', 'isFull', 'label'],
    },
    error: { type: 'string' },
  },
  required: ['ok', 'selection', 'legacyDimensionsFallback', 'dimensions', 'evalTargets', 'coverage'],
}
// ANNOTATE_AUDIT_SCHEMA：仅用于 Phase2b 之外、纯 stdout 转录的辅助侧审计调用（L1/L2/L3 合规率统计）。
const ANNOTATE_AUDIT_SCHEMA = {
  type: 'object',
  properties: {
    stdout: { type: 'string' },
  },
  required: ['stdout'],
}
// PIPELINE_SCHEMA：phase234-query-pipeline 的统一输出契约。Stage D 只是空交接对象；
// Phase5 在全部词级结果通过本地回执后由批次控制器统一运行一次。
const PIPELINE_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    query: { type: 'string' },
    stageA: {
      type: 'object',
      properties: {
        phase2Attempts: { type: 'number' },
        retryPlans: { type: 'array' },
        elementListPaths: { type: 'array', items: { type: 'string' } },
        elementAuditPaths: { type: 'array', items: { type: 'string' } },
        elementCount: { type: 'number' },
        annotated: { type: 'array', items: { type: 'string' } },
      },
      required: ['phase2Attempts', 'retryPlans', 'elementListPaths', 'elementAuditPaths', 'elementCount', 'annotated'],
    },
    stageB: {
      type: 'object',
      properties: {
        measurementsIndex: { type: 'string' },
        evalResultFile: { type: 'string' },
        evalAuditFile: { type: 'string' },
        evalCount: { type: 'number' },
      },
      required: ['evalResultFile', 'evalAuditFile', 'evalCount'],
    },
    stageC: {
      type: 'object',
      properties: {
        evidenceImages: { type: 'array', description: '问题实际引用的 screenshots 原图去重集合', items: { type: 'string' } },
        skipped: { type: 'array' },
      },
      required: ['evidenceImages', 'skipped'],
    },
    stageD: {
      type: 'object',
      properties: {},
      additionalProperties: false,
    },
    blockedAt: { type: 'string' },
    error: { type: 'string' },
  },
  required: ['ok', 'query', 'stageA', 'stageB', 'stageC', 'stageD', 'blockedAt', 'error'],
}

// ---------- Screenshot Agent ----------
phase('截图')
log('工作流模式=' + mode + '；步骤：Screenshot Agent → 发现评测项 → Evaluation Agent(Phase2+3+4)')
log('Screenshot Agent: query=' + query + ' skip=' + skipScreenshot)

const shotPrompt = `你是美团搜索截图执行 Agent。任务：为搜索词「${query}」获取 ${tabs.join('/')} × 第${screens.join('/')}屏 截图，目录 ${screenshotDir}。

${mode === 'evaluate_only' && selectedScreenshots.length ? `## 已选择已有截图（禁止运行 run_scroll.sh）
用户已从截图发现结果选择以下文件：
${selectedScreenshots.map(path => '- ' + path).join('\n')}

对每个路径用 stat -f%z 校验存在且 >5000 字节；不要扫描、替换或删除其他文件。把有效绝对路径收集到 screenshots；缺失/过小文件写入 missing 和 error。只要至少一张有效图就 ok=true。` : skipScreenshot ? `## 跳过截图模式（用已有截图，禁止运行 run_scroll.sh）
用 Bash 执行：
  ls -la ${screenshotDir}/${query}_*.png 2>/dev/null
对每个 tab×屏 组合（tab∈{${tabs.join(',')}}，屏∈{${screens.join(',')}}）用 stat -f%z 校验文件存在且 >5000 字节。
- 命名格式 ${query}_{tab}_{屏}.png
- 把所有存在且 >5000 字节的文件绝对路径收集到 screenshots 数组返回，ok=true
- 若某个 tab 一个有效文件都没有，ok=false，error 列出缺失项
- 个别屏缺失（如缺第2/3屏但第1屏在）不影响 ok，只需在 error 字段备注哪些屏缺失，仍返回已有的路径
禁止覆盖或删除任何已有文件。` : `## 现场截图模式
设备：Android 手机，USB 连 Mac、USB调试开启、美团App已登录。
截图脚本会读取当前厂商/机型/系统版本和 \`wm size\`。返回使用系统返回键；搜索输入框与 Tab 必须由当前 UI XML 的 bounds 动态定位，滑动使用屏幕比例。若结果页 XML 连续为空、找不到 Tab 或点击后不可验证，返回当前词/Tab 的明确失败，不得使用固定坐标兜底。

⚠️ 关键守卫：设备离线时 run_scroll.sh 会写出 0 字节文件覆盖已有图。因此启动脚本前必须确认设备在线。

步骤（全部用 Bash 工具）：
1. 重连设备：循环最多15次 \`adb kill-server; adb start-server; sleep 1.5\` 直到 \`adb get-state\` 输出 device。
2. 设备在线守卫（必做）：\`adb get-state\` 必须输出 \`device\`。若仍不是 device，立即 ok=false 返回，error="设备离线，未运行截图脚本（避免覆盖）"，**不要执行后续步骤**。
3. 切输入法：\`adb shell ime set com.android.adbkeyboard/.AdbIME\`
4. 启动截图脚本（后台，用 OUT 环境变量指定输出到项目 screenshots 目录）：
   cd ${shotSkillDir} && OUT=${screenshotDir} nohup bash scripts/run_scroll.sh "${query}" "${tabs.join(',')}" "${screens.join(',')}" > /tmp/scroll_run.out 2>&1 &
   echo $! > /tmp/scroll.pid
5. 等待完成（单次 Bash 调用，timeout 设 600000ms）：
   until grep -q ALL_DONE /tmp/meituan_scroll.log 2>/dev/null; do sleep 10; done
6. 校验：\`ls -la ${screenshotDir}/${query}_*.png\`，只收集 >5000 字节的文件；0 字节文件不得删除。将其复制到 \`${artifactRunDir}/phase1/invalid-screenshots/\` 并在 error 字段记录原路径与原因，原文件也保留。
7. 返回 ok=true + 有效文件的绝对路径列表；检查 \`grep '!!' /tmp/meituan_scroll.log\` 有无跳过，有则在 error 备注。若某 tab 无任何有效文件，ok=false。`}

严格按 schema 输出。`

const shotResult = await agent(shotPrompt, withRequestedModel({ label: 'Screenshot Agent', phase: '截图', schema: SHOT_SCHEMA, agentType: 'screenshot-agent' }))
if (!shotResult || !shotResult.ok) {
  throw new Error('截图阶段失败: ' + (shotResult && shotResult.error ? shotResult.error : 'agent 无返回'))
}
const screenshots = shotResult.screenshots
log('Screenshot Agent 完成: ' + screenshots.length + ' 张截图')

if (mode === 'capture_only') {
  return {
    mode,
    status: 'completed',
    query,
    screenshots,
    screenshotsCount: screenshots.length,
    missing: shotResult.missing || [],
    error: shotResult.error || '',
  }
}

// 显式选择“截图+评测”时先落盘并等待用户确认评测维度和报告出口。旧调用（未传 mode）
// 仍可使用 skipScreenshot=false 一次性跑完，避免破坏既有自动化入口。
if (mode === 'capture_and_evaluate' && A.mode === 'capture_and_evaluate' && A.evaluationConfirmed !== true) {
  return {
    mode,
    status: 'awaiting_evaluation_config',
    query,
    screenshots,
    screenshotsCount: screenshots.length,
    nextRequired: ['evaluationSelection', 'reportOutlet'],
  }
}

// ---------- Phase2 固定产物路径：每张截图一个主 JSON，禁止多图合并 ----------
const phase2InputPaths = screenshots
const phase2Outputs = phase2InputPaths.map(p => {
  const stem = p.split('/').pop().replace(/\.[^.]+$/, '')
  const manifest = annotatedDir + '/elements_' + stem + tagSuffix + '.json'
  return {
    screenshot: p,
    manifest,
    audit: manifest.replace(/\.json$/, '.audit.json'),
    recognitionAudit: manifest.replace(/\.json$/, '.recognition-audit.json'),
    visualReview: manifest.replace(/\.json$/, '.visual-review.json'),
    candidateBundle: manifest.replace(/\.json$/, '.candidate-bundle.v2.json'),
    artifactsDir: artifactRunDir + '/phase2/' + stem + tagSuffix,
    attemptRoot: artifactRunDir + '/phase2/' + stem + tagSuffix + '/attempts',
  }
})
if (new Set(phase2Outputs.map(item => item.manifest)).size !== phase2Outputs.length) {
  throw new Error('screenshots 中存在同名文件，无法保证一图一 JSON；请先让截图文件名唯一')
}
const phase2RereviewAuditFile = annotatedDir + '/elements_' + query + tagSuffix + '.recognition-audit-rereview-' + rerunId + '.json'
const phase2RereviewValidationFile = evaluationArtifactDir + '/Phase2返工复核校验_' + query + tagSuffix + '_' + dimSlug + '.json'

// ---------- Phase 2b: 由统一 catalog 解析评测范围（确定性、不读图） ----------
phase('评测')
log('Phase 2b catalog 解析: dimensions=' + dimensions.join(',') + (legacySelectionFallback ? '（兼容旧 dimensions 参数）' : ''))

const selectionJson = JSON.stringify(evaluationSelection)
const resolutionPrompt = `你是 Phase3 统一入口的确定性范围解析执行器。禁止读取截图、禁止评分、禁止修改文件。只用 Bash 原样执行下列命令，并将 stdout JSON 原样映射到 schema：

\`\`\`bash
"${pythonBin}" "${projectDir}/phase3-evaluation/common/routing/resolve_eval_targets.py" --project-dir "${projectDir}" --selection-json '${selectionJson}'
\`\`\`

若命令失败，返回 error；不要自行扫描或补全未选 Skill。`
const resolution = await agent(resolutionPrompt, withRequestedModel({ label: 'Phase3入口:解析范围', phase: '评测', schema: EVAL_TARGET_RESOLUTION_SCHEMA }))
if (!resolution || resolution.ok !== true || !Array.isArray(resolution.evalTargets) || resolution.evalTargets.length === 0) {
  throw new Error('Phase3 入口未能解析合法评测范围: ' + (resolution && resolution.error ? resolution.error : '无目标 Skill'))
}
const resolvedTargets = resolution.evalTargets
const resolvedDimensions = resolution.dimensions
const evaluationScope = resolution.coverage
log('Phase3范围=' + evaluationScope.label + '；目标=' + resolvedTargets.map(item => item.dimension + '/' + item.skill).join(','))
// 目录由 resolver 从 catalog 返回；外部维度 ID 不再参与物理路径拼接。
const skillDirs = {}
resolvedTargets.forEach(target => { skillDirs[target.dimension] = projectDir + '/' + target.skillsDir })

// ---------- Evaluation Agent: Phase 2+3+4 ----------
// 原 phase2-annotator / phase4-issue-evidence 合并为一次 phase234-query-pipeline 调用：
// 同一子代理上下文内部顺序完成 Stage A(本地识别)→B(评测)→C(原图证据引用)→D(空交接)，
// 中间不返回调用方、不切换子代理。Phase5 在全部词级回执通过后由批次控制器运行一次。
// 所有阶段级契约细节（Phase2 当前图片校准、七键单图清单、FACT_GATES、共享契约优先、assessmentRows/issues 结构、
// 页面框架结论边界与批次报告交接等）已完整写入 workflow/contracts/phase234-query-pipeline.md，
// 本次调用只注入具体输入值，不在 JS 侧重复拼接任何阶段级 Prompt 文本。
const evalResultFile = artifactRunDir + '/results/评测原始结果_' + query + tagSuffix + '_' + dimSlug + '.json'
const evalAuditFile = artifactRunDir + '/results/评测结果校验_' + query + tagSuffix + '_' + dimSlug + '.json'
const phase2ReviewFile = artifactRunDir + '/results/待回退Phase2复核_' + query + tagSuffix + '_' + dimSlug + '.json'
// 兼容旧宿主的冻结字段；新 Phase4 不写该目录，直接引用 screenshots 原图。
const issueEvidenceDir = annotatedDir + '/evidence/' + query + tagSuffix
const measurementsDir = artifactRunDir + '/phase3/measurements'
const stagePaths = { measurementsDir, evalResultFile, evalAuditFile, phase2ReviewFile, issueEvidenceDir }

const mergedInputs = {
  query, tag, batchId, runId,
  projectDir,
  pythonBin,
  screenshots,
  screenshotIdentityMap: suppliedIdentityMap,
  tabs,
  artifactRunDir,
  // Phase2（本地识别）
  annotatedDir,
  phase2SkillDir,
  phase2Mode,
  phase2Outputs,
  phase2MaxAttempts: Number.isInteger(A.phase2MaxAttempts) ? A.phase2MaxAttempts : 3,
  skipAnnotation,
  // Phase3（评测）
  evalTargets: resolvedTargets,
  evaluationScope,
  phase3SkillDir,
  skillDirs,
  granularity,
  evalResultFile,
  evalAuditFile,
  phase2ReviewFile,
  phase2RereviewAuditFile,
  phase2RereviewValidationFile,
  // Phase4（问题原图引用；issueEvidenceDir 仅兼容旧任务）
  issueEvidenceSkillDir,
  issueEvidenceDir,
  stagePaths,
}

const mergedPrompt = `你正在以 Evaluation Agent 身份执行当前搜索词的唯一 Phase2→Phase3→Phase4 评测契约。先读取并严格遵守 workflow/contracts/phase234-query-pipeline.md。开始前确认宿主可读取当前图片像素；若不支持，返回 blockedAt=preflight、error=model_vision_not_supported，且不得进入 Phase2。本次调用只提供具体输入值，不重复给出规则文本。

## 本次调用输入（JSON，字段名与你的输入契约一一对应）
\`\`\`json
${JSON.stringify(mergedInputs, null, 2)}
\`\`\`
严格按你的输出 schema 一次性回传结果，不要提前中断或跳过阶段。`

const pipelineResult = await agent(mergedPrompt, withRequestedModel({ label: 'Evaluation Agent:' + query, phase: '评测', schema: PIPELINE_SCHEMA, agentType: 'evaluation-agent' }))
if (!pipelineResult || !pipelineResult.ok) {
  throw new Error('Phase2+3+4 词级子代理未通过：blockedAt=' + (pipelineResult && pipelineResult.blockedAt) + ' error=' + (pipelineResult && pipelineResult.error))
}
const stageA = pipelineResult.stageA
const stageB = pipelineResult.stageB
const stageC = pipelineResult.stageC
const stageD = pipelineResult.stageD
if (pipelineResult.query !== query || !stageA || !stageB || !stageC || !stageD ||
    !Array.isArray(stageA.elementListPaths) || !Array.isArray(stageA.elementAuditPaths) ||
    stageA.elementListPaths.length === 0 || stageA.elementListPaths.length !== stageA.elementAuditPaths.length ||
    typeof stageB.evalResultFile !== 'string' || !stageB.evalResultFile ||
    typeof stageB.evalAuditFile !== 'string' || !stageB.evalAuditFile ||
    !Array.isArray(stageC.evidenceImages) || Object.keys(stageD).length !== 0) {
  throw new Error('Evaluation Agent 返回 ok=true 但阶段产物不完整；拒绝将其标记为成功')
}
const elementListPaths = stageA.elementListPaths
const elementAuditPaths = stageA.elementAuditPaths
const elementCount = stageA.elementCount
const annotatedPaths = stageA.annotated
log('Phase2+3+4 完成: elementCount=' + elementCount + ' evalCount=' + (stageB.evalCount || 0) + ' referencedOriginals=' + ((stageC.evidenceImages || []).length) + '；等待批次级 Phase5')

// ---------- Phase2 manifest 质量侧审计（可选，仅记录 L1/L2/L3 合规率，不阻断） ----------
// phase3-标记权威白名单，仅供本侧审计脚本比对，不再注入合并子代理的 Prompt（Stage A 已在
// agent 定义文件内固化 L1/L2/L3 执行顺序与骨架约束）。
const PHASE3_CARD_TYPES = ['商品卡片', '商家卡片-图文下挂', '商家卡片-文字下挂', '酒店卡片', '度假/酒店套餐卡片', '演出/电影卡片', '主点卡片', '特殊广告卡']
const PHASE3_REGION_NAMES = ['头图区', '标题区', '基础信息区', '标签区', '价格区', '商家区', '下挂区', 'AI推荐理由']
let annotationAudit = null
if (elementListPaths.length === 1 && enableAnnotationAudit) {
  const elementListPath = elementListPaths[0]
  const recognitionAuditFile = phase2Outputs[0].recognitionAudit
  const auditPrompt = `用 Bash 跑下面命令，对元素清单做 phase3-标记自动验收（L1/L2/L3）：
\`\`\`bash
P=$(echo "${elementListPath}")
"${pythonBin}" - "$P" <<'PYEOF'
import json, os, sys

p = sys.argv[1]
ALLOWED_CARD_TYPES = set(${JSON.stringify(PHASE3_CARD_TYPES.concat(['宏观组件']))})
ALLOWED_REGION_NAMES = set(${JSON.stringify(PHASE3_REGION_NAMES)})
ALLOWED_ELEMENT_TYPES = {"文本", "图片", "标签"}
GENERIC_BAD = {
    "原文:商家名称", "原文:评分", "原文:评分 距离 人均", "原文:标签", "原文:基础信息",
    "原文:文字下挂促销", "原文:商品缩略图横滑", "原文:商品图", "原文:价格", "原文:内容未知"
}
CORE_REGIONS = {
    "商品卡片": {"头图区", "标题区", "基础信息区", "价格区", "商家区"},
    "商家卡片-图文下挂": {"头图区", "标题区", "基础信息区", "下挂区"},
    "商家卡片-文字下挂": {"头图区", "标题区", "基础信息区", "下挂区"},
    "酒店卡片": {"头图区", "标题区", "基础信息区"},
    "度假/酒店套餐卡片": {"头图区", "标题区", "基础信息区", "价格区"},
    "演出/电影卡片": {"标题区", "基础信息区", "价格区"},
    "主点卡片": {"标题区", "基础信息区"},
    "特殊广告卡": {"标题区"},
}

def valid_coord(v):
    return isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v)

if not os.path.exists(p):
    print("AUDIT_OK=0")
    print("AUDIT_ERR=file_not_found")
    sys.exit()

try:
    d = json.load(open(p))
    cards = d.get('cards', []) if isinstance(d, dict) else []

    total_cards = len(cards)
    total_regions = 0
    total_elements = 0
    non_excluded_elements = 0

    l1_valid = 0
    l2_name_valid = 0
    l3_type_valid = 0
    l3_coord_valid = 0
    l3_exclude_valid = 0
    l3_text_valid = 0

    seen_types = set()
    missing_core = []

    for c in cards:
        if not isinstance(c, dict):
            continue
        ctype = str(c.get('卡片类型', '')).strip()
        if ctype in ALLOWED_CARD_TYPES:
            l1_valid += 1
        seen_types.add(ctype)

        if ctype == '宏观组件':
            continue

        regions = c.get('regions', [])
        if not isinstance(regions, list):
            regions = []
        names = set()
        for r in regions:
            total_regions += 1
            if not isinstance(r, dict):
                continue
            rn = str(r.get('name', '')).strip()
            names.add(rn)
            if rn in ALLOWED_REGION_NAMES:
                l2_name_valid += 1

            elements = r.get('elements', [])
            if not isinstance(elements, list):
                elements = []
            for e in elements:
                total_elements += 1
                if not isinstance(e, dict):
                    continue
                et = str(e.get('元素类型', '')).strip()
                if et in ALLOWED_ELEMENT_TYPES:
                    l3_type_valid += 1
                if valid_coord(e.get('坐标')):
                    l3_coord_valid += 1

                ex = e.get('isExcluded')
                reason = e.get('excludeReason')
                if isinstance(ex, bool) and ((ex and isinstance(reason, str) and reason.strip()) or (not ex and reason in (None, ''))):
                    l3_exclude_valid += 1
                if isinstance(ex, bool) and not ex:
                    non_excluded_elements += 1
                    facts = e.get('textFacts') if isinstance(e.get('textFacts'), dict) else {}
                    txt = str(facts.get('rawText') or e.get('内容简述', '')).strip()
                    is_photo = et == '图片' or (isinstance(e.get('render'), dict) and e['render'].get('isPhoto') is True)
                    if is_photo or (txt and ('原文:' + txt if not txt.startswith('原文:') else txt) not in GENERIC_BAD):
                        l3_text_valid += 1

        core = CORE_REGIONS.get(ctype, set())
        if core:
            miss = sorted(list(core - names))
            if miss:
                missing_core.append(str(c.get('cardId', 'unknown')) + ':' + ','.join(miss))

    def rate(ok, total):
        return 1.0 if total == 0 else float(ok) / float(total)

    l1_rate = rate(l1_valid, total_cards)
    l2_rate = rate(l2_name_valid, total_regions)
    l3_type_rate = rate(l3_type_valid, total_elements)
    l3_coord_rate = rate(l3_coord_valid, total_elements)
    l3_exclude_rate = rate(l3_exclude_valid, total_elements)
    l3_text_rate = rate(l3_text_valid, non_excluded_elements)
    l3_rate = min(l3_type_rate, l3_coord_rate, l3_exclude_rate, l3_text_rate)

    print("AUDIT_OK=1")
    print("TOTAL_CARDS=" + str(total_cards))
    print("TOTAL_REGIONS=" + str(total_regions))
    print("TOTAL_ELEMENTS=" + str(total_elements))
    print("NON_EXCLUDED_ELEMENTS=" + str(non_excluded_elements))
    print("L1_CARD_TYPE_RATE=" + format(l1_rate, '.4f'))
    print("L2_REGION_NAME_RATE=" + format(l2_rate, '.4f'))
    print("L3_TYPE_RATE=" + format(l3_type_rate, '.4f'))
    print("L3_COORD_RATE=" + format(l3_coord_rate, '.4f'))
    print("L3_EXCLUDE_RATE=" + format(l3_exclude_rate, '.4f'))
    print("L3_TEXT_RATE=" + format(l3_text_rate, '.4f'))
    print("L3_OVERALL_RATE=" + format(l3_rate, '.4f'))
    print("USED_L1_TYPES=" + ('|'.join(sorted([x for x in seen_types if x])) if seen_types else 'NONE'))
    print("MISSING_CORE_REGIONS=" + (';'.join(missing_core) if missing_core else 'NONE'))
except Exception as ex:
    print("AUDIT_OK=0")
    print("AUDIT_ERR=" + str(ex)[:120])
PYEOF
\`\`\`
把 stdout 原样放进 schema 返回。`

  const auditResult = await agent(auditPrompt, withRequestedModel({ label: 'Manifest验收', phase: '评测', schema: ANNOTATE_AUDIT_SCHEMA }))
  const auditOut = (auditResult && auditResult.stdout) || ''
  const pickNum = (k) => {
    const mm = auditOut.match(new RegExp(k + '=(\\d+(?:\\.\\d+)?)'))
    return mm ? Number(mm[1]) : null
  }
  const pickStr = (k) => {
    const mm = auditOut.match(new RegExp(k + '=([^\n]*)'))
    return mm ? mm[1].trim() : ''
  }

  annotationAudit = {
    ok: pickNum('AUDIT_OK') === 1,
    recognitionAuditPath: recognitionAuditFile,
    totalCards: pickNum('TOTAL_CARDS'),
    totalRegions: pickNum('TOTAL_REGIONS'),
    totalElements: pickNum('TOTAL_ELEMENTS'),
    nonExcludedElements: pickNum('NON_EXCLUDED_ELEMENTS'),
    l1CardTypeRate: pickNum('L1_CARD_TYPE_RATE'),
    l2RegionNameRate: pickNum('L2_REGION_NAME_RATE'),
    l3TypeRate: pickNum('L3_TYPE_RATE'),
    l3CoordRate: pickNum('L3_COORD_RATE'),
    l3ExcludeRate: pickNum('L3_EXCLUDE_RATE'),
    l3TextRate: pickNum('L3_TEXT_RATE'),
    l3OverallRate: pickNum('L3_OVERALL_RATE'),
    usedL1Types: pickStr('USED_L1_TYPES'),
    missingCoreRegions: pickStr('MISSING_CORE_REGIONS'),
    error: pickStr('AUDIT_ERR'),
    raw: auditOut,
  }

  const l1 = annotationAudit.l1CardTypeRate == null ? 'NA' : Math.round(annotationAudit.l1CardTypeRate * 1000) / 10 + '%'
  const l2 = annotationAudit.l2RegionNameRate == null ? 'NA' : Math.round(annotationAudit.l2RegionNameRate * 1000) / 10 + '%'
  const l3 = annotationAudit.l3OverallRate == null ? 'NA' : Math.round(annotationAudit.l3OverallRate * 1000) / 10 + '%'
  log('Manifest质量侧审计: L1=' + l1 + ' L2=' + l2 + ' L3=' + l3 + (annotationAudit.ok ? '' : ' (audit failed)'))
}

log('词级评测完成：已交付 Phase2/3/4 可核验产物，报告由批次级 Phase5 统一生成')
return {
  mode: mode,
  status: 'completed',
  runId: runId,
  batchId: batchId,
  query: query,
  reportOutlet: reportOutlet,
  dimensions: resolvedDimensions,
  evaluationSelection: resolution.selection,
  evaluationScope: evaluationScope,
  screenshotsCount: screenshots.length,
  annotatedCount: annotatedPaths.length,
  evalSkillsCount: stageB.evalCount || 0,
  annotationAudit: annotationAudit,
  evaluationResult: pipelineResult,
  deterministicAudits: {
    manifests: elementAuditPaths,
    recognition: phase2Outputs.map(item => item.recognitionAudit),
    evaluations: elementListPaths.length ? evalAuditFile : '',
  },
}
