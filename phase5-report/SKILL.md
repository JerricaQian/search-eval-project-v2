---
name: report-local-html
description: >-
  美团搜索结果页批次 HTML 报告渲染层。用于所有词级 Phase2～4 产物验收完成后，从当前隔离批次生成一份跨词治理看板。
  批量看板必须调用确定性生成器，不能由 Agent 自由编写或补造数据。
metadata:
  author: qianjing16
  version: "4.2"
  domain: 美团搜索结果页综合质量评估
---

# Phase5 本地报告

## 职责与边界

Phase5 由外层批次控制器运行一次，只渲染已有 completed 回执的 Phase2、Phase3、Phase4 事实：不重新评测、不计算分数、不改写评级、业务归属、问题数、坐标、证据或建议。它只能在全部预期词进入终态后运行：仅 completed 词进入数据集和 HTML；连续三个隔离任务失败后标记为 abandoned 的词只保留在批次控制状态中，报告不得提及。至少要有一个 completed 词；全部 abandoned 时不得生成空报告。词级任务不读取本 Skill，也不生成单词 HTML。

- 待优化问题仅为 `rating ∈ {达标, 不达标}`；优秀不作为问题展示。
- 每个待优化问题必须使用 Phase4 回写的原始 `screenshots/` 路径作为 `evidenceImage`，且必须与所属评测单元的 `screenshot` 一致。不得生成或回退到红框图、裁剪图、Phase2 标注图或其他截图。
- 任何元素清单、评测结果或事实字段校验失败，停止渲染并回退上游修复。

## 唯一模板

任意数量（含单个）已完成搜索词的当前隔离批次只使用 `GOVERNANCE_DASHBOARD_V2`，并且只运行 `phase5-report/scripts/build_experience_dashboard.py`。不要创建第二份单词 HTML 生成器、旧版样式文件或并行渲染入口。

## `GOVERNANCE_DASHBOARD_V2`

### 唯一入口与命令

生产入口只有两层：

1. `phase5-report/scripts/build_experience_dashboard.py:collect()` / `validate_dataset()` 采集并阻断校验；`render()` 仅委派给渲染器。
2. `phase5-report/dashboard_renderer.py:render_dashboard()` 是唯一 HTML 渲染器。

批量看板必须使用下面的完整命令；所有路径只指向本轮隔离批次，禁止扫描全局历史产物。

```bash
"${pythonBin}" "${projectDir}/phase5-report/scripts/build_experience_dashboard.py" \
  --project-dir "${projectDir}" --artifact-dir "${batchArtifactDir}" \
  --batch-name "${batchId}" --output "${reportPath}" \
  --dataset-output "${reportDir}/.governance_dataset_${batchId}.json" \
  --expected-query "<query-1>" --expected-query "<query-2>" \
  --manifest "<accepted-manifest-1>" --manifest "<accepted-manifest-2>" \
  --result "<accepted-result-1>" --result "<accepted-result-2>"
```

业务 Tab 必须由本批当前截图中、已验收商卡的可见语义与履约标识推导；搜索词、任务时 UI Tab、历史批次和控制器默认值都不能参与归属。`--expected-business-tabs` 是可选的逗号分隔标准 `businessCode` 事后断言；如提供，实际聚合的 Tab 缺失或多出任一项必须退出失败，不能以空卡、历史数据或默认 Tab 补齐。

由 `workflow/eval_cli.py finalize-batch --batch-state <最新状态>` 触发时，abandoned 搜索词只用于验证终态屏障，不传给报告生成器。pending、retry_required 或尚未达到三次上限的失败词会阻断 Phase5，不能提前生成部分报告。

`--expected-query`、`--manifest`、`--result` 均来自本批 V3 词级任务及其 completed 回执，且只覆盖本次报告的成功子集与每张对应的 manifest；禁止从全局 `screenshots-out/` 或历史批次按更新时间猜选输入。同一搜索词多张截图的卡片/元素 ID 可能重复，生成器必须以原图路径隔离后再聚合。

### 数据与业务归属门槛

- 只消费当前批次已通过 `validate_element_manifest.py` 与 `validate_eval_results.py` 的产物；每个已评测词有原图，带坐标的待优化问题有 Phase4 证据，所有问题级 `description` 与 `recommendation` 完整。
- 可用业务仅为：`dine_in`、`food_delivery`、`flash_delivery`、`service_retail`、`healthcare`、`hotel_travel`、`xiaoxiang`、`maoyan`。平台组件不进入业务 Tab。
- `ownershipScope=business` / `businessCode` 只是 Phase2 审计提示，不能优先于当前卡片事实；只有它与重新从可见语义、履约标识得到的归属一致时才可保留为置信度信息。冲突、未知或不支持的显式 code 都为 `unknown` 并阻断。
- 当前卡片的可见商家/商品语义与履约事实是唯一归属依据：专属业态（医药、旅行、猫眼、小象）优先；服务零售次之；配送场景须同时具备餐饮或闪购品类事实；无配送的餐饮语义归到餐。卡片容器、搜索词、任务预设 Tab、历史批次和 HTML 补丁都不能作为归属事实。
- 任何商卡证据不足即记录 `unknown` 并停止正式业务看板；先回到 Phase2 补充当前可见事实。

### 固定信息架构与视觉

最终视觉基准为已发布的 NoCode 治理看板（`w9t3s72kfesal1ma`，线上 `https://fuduka.mynocode.host`）。本地 `dashboard_renderer.py` 和后续 NoCode 页面都必须复刻这套信息架构、视觉令牌和交互语义；基准中的批次数据不是模板的一部分，后续批次只替换已验证数据。

看板采用浅色治理布局：`#F7F8FA` 画布、`1400px` 内容宽、白色表面、`#2563EB` 单一主交互色、`12px` 圆角和 `0 2px 8px rgba(16,24,40,.06)` 低阴影。字体固定为系统中文无衬线栈。`dashboard_renderer.py` 内联唯一一套 CSS；不使用 CSS 叠加、历史样式块或同名覆盖。

固定结构：

1. 无顶部白色导航栏；标题区展示评测日期、搜索词数量、已执行维度和当前批次选择器。
2. 一级业务 Tab 吸顶，顺序为概览 + 本批次实际确认业务；业务按最终 NoCode 稳定顺序“服务零售、酒店旅行、到餐、闪购、医药健康、餐饮外卖、猫眼、小象超市”排列，不按当前问题数重排；激活项使用蓝色 `2px` 下划线。
3. 概览与业务页均使用一张无单独标题的综合统计卡：左侧为固定 `520px` 的四列统计区（每列 `112px`、列间距 `24px`），展示累计问题、本月新增、累计解决、解决率（累计解决 ÷ 累计问题）；中间和右侧分别为固定 `300px` 的 P0/P1/P2 与 TOP3 + 其他问题占比圆环区。三部分不使用 KPI 弹性宽度，并由白卡分配充足组间距。解决率数值中的 `%` 固定为 `13px`、灰色、400 字重；圆环中心不显示总数，悬停展示数量与占比。
4. 概览在统计卡后以“业务明细”为标题展示四列业务卡；业务卡显示新增数，以及数字在上、灰色标题在下的累计问题、累计解决、解决率；数字值和小标题均使用紧凑行高，中间保留真实 `2px` 间距，并保留灰色 P0/P1/P2 标签；点击进入对应业务明细。业务页标题仍为“问题明细”。
5. 业务明细使用“按问题等级 / 按搜索词 / 按指标”三级明细，默认“按问题等级”。“按问题等级”固定提供“全部、P0、P1、P2”二级筛选，默认全部并展示所有问题；“按指标”仅把当前业务实际存在问题的指标列为二级筛选，默认第一个指标；“按搜索词”以 query 分组标题表达搜索词，显示“全部 Tab”范围胶囊，卡内不再重复展示“所属搜索词”。
6. 每条问题标题右侧直接展示所属维度；正文按单栏纵向展示“所属搜索词、问题描述、独立建议”，删除单独的“层级”和“对象定位”栏，不展示坐标。问题描述直接渲染 Phase3 的 `issues[].description`，Phase5 不拼接或改写事实、规则、评级原因与影响；证据宽度固定为 `240px`，高度按整页原图比例自然延伸且不设上限，确保不裁切或缩窄页面全貌，懒加载并可新标签打开。
7. 明细中的 P0/P1/P2 统一使用灰色 `#F2F4F7` 胶囊、`#EAECF0` 边框和 `#475467` 文案，避免与问题正文争夺焦点；优先级圆环仍按 P0/P1/P2 使用 `#FF3131`、`#FF8282`、`#FFAFAF`。TOP1/TOP2/TOP3/其他问题环形图依次使用 `#ECB5C4`、`#C8D8F9`、`#D8BFF2`、`#D9D9D9`。环形分段连续无白色间隙，并保留圆角端点；“单一元素维度 / 组件/卡片维度 / 页面框架维度”标签对应使用 `#2563EB`、`#0E9384`、`#667085` 文案色。
8. “按问题等级 / 按搜索词 / 按指标”仅保留文字 Tab，不显示圆形 `i` 说明角标、人工复核提示条或人工复核记录面板。人工复核排除若经授权存在，只能作为线上展示层的内部过滤规则，不得改写 Phase2～4 事实、治理数据集或在页面上暴露记录。

优先级固定阈值：P0 为同类问题不达标≥4或达标≥6；P1 为不达标≥2或达标≥4；P2 为达标1至3。若仅有1票不达标且0票达标，为避免问题从报告中丢失，作为未命中显式阈值的剩余低频问题收纳为P2，并在 `priorityReason` 中明确标注。

小屏下业务卡由四列降为两列再降为一列，问题图文改为单列；焦点态清晰，避免横向溢出。

明确禁止：Sankey 图和相关函数、页面级瀑布流/额外摘要区、重复问题证据、深色旧皮肤、CSS 分层覆盖、`render_v7_structured` 或任何未被 `render()` 调用的历史渲染器。

### 问题文案与排序

- 待优化项必须把正向评测指标转换为问题名称后写入 `metricName`，例如“信息无冗余 + 不达标”显示为“信息冗余”，“信息可比性 + 不达标”显示为“信息不可比”；禁止直接把正向指标名作为问题标题。
- 复杂度问题名称统一使用简短口径：组件/卡片维度的 `eval-4-element-complexity` 显示为“元素复杂”，页面框架维度的 `eval-4-static-component-complexity` 显示为“组件复杂”；历史长名称只用于兼容读取，不得继续写入新治理数据集。
- 色彩问题按维度使用独立名称：单一元素维度的 `eval-2-color-logic-single-element` 显示为“单一元素色彩复杂”，组件/卡片维度的 `eval-3-color-logic` 显示为“组件色彩复杂”，页面框架维度的 `eval-3-page-color-logic` 显示为“页面色彩复杂”；历史“色彩运用问题”名称只用于兼容读取。
- `issues[].description` 是问题描述的唯一来源，文案主体固定为“问题出现位置 → 可见事实、命中规则、评级原因与直接影响 → 指标评级”；元素 ID 和坐标不在问题明细重复堆砌。
- Phase3 必须在 `description` 中写好用户可读的位置主语；Phase5 只去除坐标，不再补写或去重文案。
- `recommendation` 必须是问题级的：明确对象、动作和可验收结果；缺失时阻断，不能使用通用模板代替。
- 分组优先级由生成器按“业务线 + 维度 + 指标”统计，并按 P0 → P1 → P2 排序；渲染器只消费结果，不再计算。
- 同一截图的证据可在该截图的多个问题间复用；不同截图不得混用。

### 批量交付校验

生成后确认：

- HTML 与 `.governance_dataset_<batchId>.json` 均存在且非空；
- 数据集中的搜索词集合与全部 completed 词级任务完全一致；
- HTML 包含 `business-tab`、`business-panel`、`detail-tab`、`detail-pane`、`activateBusiness`；
- HTML 不包含 `sankey-link`、“高频问题跨词覆盖”或“典型问题证据库”；
- 业务 Tab 与当前卡片可见事实推导结果精确一致；若提供 `--expected-business-tabs`，还须与该断言精确一致。

## 出口

本 Skill 只生成本地 `reports/` HTML 与批量数据集。NoCode、线上发布或数据库导入，须转交 `phase5-report/nocode-dashboard/SKILL.md`，并沿用同一份已验证数据集。
