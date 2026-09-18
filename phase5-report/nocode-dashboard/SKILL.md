---
name: report-nocode-dashboard
description: >-
  美团搜索结果页治理看板的 NoCode 数据导入、页面同步、Phase4 证据发布与线上部署 Skill。
  用于发布或更新 phase5 跨词治理看板；必须以本地 .governance_dataset_<批次>.json
  和 phase5-report/SKILL.md 的 GOVERNANCE_DASHBOARD_V2 为事实源，复刻本地看板的
  吸顶业务 Tab、综合统计卡、证据卡、优先级和批次切换布局。
metadata:
  author: qianjing16
  version: "2.1"
  domain: 美团搜索结果页综合质量评估
---

# NoCode 治理看板部署

## 1. 定位与边界

本 Skill 是 phase5 的线上展示层，只将已验收的本地治理数据集导入 NoCode 并以固定模板展示；不执行 phase3 评测、phase4 标注，不从 HTML 反向取数，不创建第二套评分或优先级算法。

| 范围 | 唯一入口 | 产物 |
|---|---|---|
| 本地 HTML 与治理数据集 | `../SKILL.md` + `../scripts/build_experience_dashboard.py` | `reports/*.html`、`.governance_dataset_<批次>.json` |
| NoCode 数据、页面、证据资源、部署 | 本 Skill | 数据库记录、`public/evidence/`、线上看板 |

- 待优化问题唯一口径为 `rating ∈ {达标, 不达标, 🟡, 🔴}`；优秀不进入问题列表。
- 本地数据集是唯一事实源。线上只能改变读取介质与 React 实现，问题文案、建议、优先级、评级、问题项数、业务归属和证据图必须与同批本地报告一致。
- 不得修改受保护的 NoCode 工程文件：`vite.config.js`、`src/main.jsx/tsx`、NoCodeProvider、`tsconfig/jsonconfig` 或目录结构；只能改 `src/pages/**`、业务组件和 `public/evidence/**`。
- 后续批次必须复用最终应用 `w9t3s72kfesal1ma`，不得因更新数据新建风格不同的页面或项目。当前线上地址为 `https://fuduka.mynocode.host`。

## 2. 优先级数据契约（阻断）

优先级由本地生成器在“同一 **业务线 + 维度 + 指标**”统计单元内确定性计算；卡型不拆分独立票池。令 `F=不达标票数`，`P=达标票数`，优秀不计票，按以下顺序判定：

```text
F >= 4 或 P >= 6  → P0
否则，F >= 2 或 P >= 4 → P1
否则，1 <= P <= 3 → P2
否则，F = 1 且 P = 0 → P2（剩余低频问题兜底，priorityReason 必须注明）
否则               → 不产生问题
```

- P0、P1、P2 的展示顺序固定为 **P0 → P1 → P2**。
- 一个统计单元下的所有 `groups[].evidence[]` 必须继承该单元同一个 `priority` 和 `priorityReason`；NoCode 不得按单条问题主观重判。
- 导入映射固定为：`P0 → severity=high, priority=0`；`P1 → medium, 1`；`P2 → low, 2`。
- 概览、业务卡、业务摘要和问题列表的 P0/P1/P2 数量均统计当前 batch 的问题级 `issue_attribution` 记录；不能用指标组数量、问题率或前端猜测替代。

## 3. 固定页面模板：GOVERNANCE_DASHBOARD_V2

线上页必须以最终已发布应用 `w9t3s72kfesal1ma` 为视觉基准，并与本地 `dashboard_renderer.py` 保持同构；不得回退至旧版“汇总表 + 桑基图 + 逐词详情”的管理台。页面顺序固定为：

```text
标题/范围/批次选择区
→ 一级业务 Tab（概览 + 本批业务）
→ 概览 Panel 或单业务 Panel
→ 单业务内的“问题明细”二级 Tab（按问题 / 按搜索词 / 按指标）
```

不得额外展示：业务汇总表、桑基图、典型证据折叠开关、逐词审计首页、评测规则首页、数据来源页脚、高频问题跨词覆盖或第二套首页模块。

### 3.1 画布、标题与一级业务 Tab

- 页面不显示顶部白色导航栏；背景固定 `#F7F8FA`，主内容宽 `1400px`，内边距 `40px 32px 48px`，白色卡片圆角 `12px`、阴影 `0 2px 8px rgba(16, 24, 40, .06)`。
- 标题为“**大搜结果页体验评测看板**”，`28px/36px`、600、`#182230`；副行显示评测日期、范围和详情链接。右上保留 `280px` 批次选择器，以真实 `batch_id` 为 value；批次切换后重新加载该批全部数据并回到概览。
- 一级 Tab 位于标题区下方并吸顶，顺序为“概览”后接当前批次确认的业务线。背景与画布一致，激活态为 `#2563EB`、600 字重和 `2px` 下划线。
- 业务线使用最终基准的稳定顺序“服务零售、酒店旅行、到餐、闪购、医药健康、餐饮外卖、猫眼、小象超市”，仅显示当前批次实际有汇总行的业务；不得混入平台、未知、零可见或历史业务线。

### 3.2 概览与单业务 Panel

- 概览和业务页都先展示一张无单独标题的白色综合统计卡：`12px` 圆角、无边框、`0 2px 8px rgba(16,24,40,.06)` 阴影。
- 综合卡左侧使用固定 `520px` 的累计问题、本月新增、累计解决、解决率（累计解决 ÷ 累计问题）四列区（每列 `112px`、列间距 `24px`），中间和右侧分别使用固定 `300px` 的 P0/P1/P2 与 TOP3 + 其他问题圆环区，不使用 KPI 弹性宽度；解决率数值中的 `%` 固定为 `13px`、灰色、400 字重。圆环中心不显示总数，图例与悬停提示均展示数量及占比，分段连续无白色间隙并保留圆角端点。
- 概览在综合卡后以“业务明细”为标题展示四列业务卡。卡片展示业务名、新增数、累计问题、累计解决、解决率以及 P0/P1/P2 灰色胶囊标签；数字在上、灰色标题在下，压缩双方行高后保留真实 `2px` 间距；点击进入对应业务 Panel。
- 单业务页顺序固定为综合问题统计卡 → 问题明细 → “按问题等级 / 按搜索词 / 按指标”二级 Tab，默认“按问题等级”。不显示人工复核提示、人工复核记录入口或展开区域。

### 3.3 问题明细

- 三种视图均使用左侧固定 `240px` 宽的 Phase4 证据、右侧问题文案的布局；证据高度按整页原图比例自然延伸且不裁切，小屏改为单列。
- 按问题等级默认展示全部问题，并提供“全部 / P0 / P1 / P2”二级筛选；按搜索词按搜索词分组，并显示“全部 Tab”范围胶囊；按指标按指标分组并默认展示首个指标下的逐条问题。
- 每条问题展示中性灰 P0/P1/P2 胶囊、指标标题、右侧维度标签、所属搜索词（按搜索词视图除外）、问题描述和问题级 recommendation。不得展示对象定位、坐标、层级字段或人工复核记录。问题描述只消费该问题的 `description`，建议只消费对应问题的 `recommendation`，不得退化为组级通用文案。
- 维度标签文案色固定：单一元素 `#2563EB`、组件/卡片 `#0E9384`、页面框架 `#667085`；优先级圆环保留 P0/P1/P2 红色系。
- 没有证据时显示明确空态；不得用原图、其它搜索词图片或旧批次同名图替代。

## 4. 数据模型与导入

### 4.1 表职责

| 表 | 数据集来源 | 用途 |
|---|---|---|
| `evaluation_batches` | `batch/generatedAt/queryCount` | 批次选择、日期和评测范围 |
| `business_summary` | `businesses[]` | 每业务一行的问题项数、问题率与覆盖卡数 |
| `issue_attribution` | `groups[].evidence[]` | **每条问题证据一行**，支撑概览计数和两种问题视图 |
| `business_metric_relations` | `groups[]` | 保留可追溯关联数据；当前模板不展示桑基图 |
| `word_evaluation_details` | `queryDetails[]` | 保留完整逐词审计数据；当前首页不展示 |
| `evaluation_rules` | 指标去重 | 保留方法追溯数据；当前首页不展示 |

### 4.2 导入规则

执行：

```bash
python3 phase5-report/scripts/import_to_nocode.py <dataset-json> <chat-id>
```

- 每次导入必须新建 `evaluation_batches` 并使用数据库返回的真实 `batch_id` 写入所有明细表；不得复用或硬编码历史 batch_id。
- `issue_attribution` 必须是问题级写入：一个 `groups[].evidence[]` 对应一行，`issue_desc` 为问题级 `description`，`suggestion` 为问题级 `recommendation`，`severity/priority` 由数据集已算好的聚合 priority 映射。
- 重复同名批次可存在，选择器必须以 id 和词数后缀区分。不得删除历史批次或过程产物。
- 导入前必须验证：`queryCount == queryDetails` 数量；每个已评测词有原图；证据所属搜索词属于本批；业务 Tab 与同批本地 Phase5 语义聚合结果完全一致。
- 导入后必须核验新 batch 的业务汇总、67 等实际问题行数、关系、逐词详情和规则行均使用同一个 batch_id；CLI 可读不代表浏览器 anon 可读，必须验证 RLS 只读权限。

## 5. Phase4 原图证据资源发布

线上浏览器不能读取本地 `file://`。必须将当前数据集使用的图片上传到 `public/evidence/`。

1. 只提取当前数据集实际引用的 `groups[].evidence[].evidenceImage` 和逐词审计需要的 `queryDetails[].screenshot`；不得混入历史批次资源。
2. 上传前说明图片数量、绝对路径范围和用途，取得用户同意；每次 `nocode send --images` 最多 5 张。
3. 发布副本必须以 `{搜索词}__{原文件名}` 重命名，例如 `西瓜__西瓜_全部_1.png`，防止不同目录或搜索词的同名原图覆盖；本地 `screenshots/` 原文件不得重命名或改写。
4. 页面通过 `import.meta.env.BASE_URL + 'evidence/' + filename` 引用，不得使用 `file://`、base64、开发机绝对路径或外部不受控 URL。
5. 图片缺失只能显示明确空态；不得回退到旧批次同名图、历史红框图、其他截图或自造图片。缩略图与大图均指向 Phase4 引用的同一张原始截图发布副本，点击新标签打开。

## 6. 后续批次标准流程

1. 以当前批次隔离 artifact 运行 `phase5-report/scripts/build_experience_dashboard.py`，由当前截图中已验收商卡的可见语义与履约标识推导业务 Tab，同时生成本地 HTML 和 `.governance_dataset_<批次>.json`。可选 `--expected-business-tabs` 只能作为事后断言，不能作为归属依据。
2. 由生成器按第 2 节优先级算法写入 group/evidence 的 `priority` 与 `priorityReason`；禁止手改 HTML 或 NoCode 数字来改优先级。
3. 对新数据集校验业务集合、问题级 description/recommendation、Phase4 `evidenceImage` 与所属原图一致，以及 P0/P1/P2 票数。
4. 若新增或变化原图证据，先取得授权，上传发布副本到 `public/evidence/` 并核验文件存在。
5. 用 `phase5-report/scripts/import_to_nocode.py` 新建批次并导入；核验返回的真实 batch_id 贯穿所有明细。
6. 页面默认加载按 `batch_date DESC, id DESC` 排在第一的完整批次；截图核验标题/范围/批次选择器、吸顶一级 Tab、单综合统计卡及两个圆环、四列业务卡、单业务三级明细 Tab、`240px` 自然高度证据布局、默认“全部”问题筛选和 P0/P1/P2 计数；确认页面不显示人工复核提示或记录栏。
7. 截图通过后执行 `nocode deploy <chatId> --skillId 2981`。部署成功后只能交付 NoCode 对话页或部署 URL，不得给 sandbox render URL。

## 7. 验收清单

### 数据

- [ ] 当前 batch 的 6 张表 batch_id 一致，anon 只读可用。
- [ ] 每条 NoCode 问题记录与本地 `groups[].evidence[]` 一一对应：描述、建议、优先级、搜索词和证据文件一致。
- [ ] P0/P1/P2 遵循第 2 节固定阈值，页面按 P0→P1→P2 排序。
- [ ] 业务线仅为当前 Phase5 基于商卡语义与履约表确认的业务，且不计算或反推分数。

### 布局与视觉

- [ ] 不存在顶部白色导航栏；标题、副行、详情链接和右上批次选择器存在，不得出现“数据来源”脚注、人工复核提示或人工复核记录栏。
- [ ] 一级 Tab 吸顶，激活态为蓝色下划线；概览与业务页均有单张综合问题统计卡和四列业务卡。
- [ ] 综合统计卡包含固定 `520px` 的四列指标区及两个无中心数字的圆环图。
- [ ] 单业务默认“按问题等级”；问题视图默认“全部”，按搜索词和按指标均使用左 `240px` 自然高度证据、右侧问题文案布局。
- [ ] 页面保持 `#F7F8FA` 画布、白色 `12px` 圆角卡片、柔和阴影和 `#2563EB` 交互语言。

### 资源与部署

- [ ] `public/evidence/` 中的图片使用 `{query}__` 前缀且与数据集映射一致。
- [ ] 缩略图可显示、可点击打开同一张大图；缺图显示明确空态。
- [ ] 已通过 `nocode screenshot <chatId>` 核验；若渲染或部署报平台异常，停止自动重试并联系 NoCode 研发。

## 当前应用

- chatId：`w9t3s72kfesal1ma`
- 对话页：`https://nocode.sankuai.com/#/chat?pageId=w9t3s72kfesal1ma`
- 部署地址：`https://fuduka.mynocode.host`
