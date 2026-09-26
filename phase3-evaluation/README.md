# Phase3 评测

Phase3 把 19 项评测组织为一个入口、三个维度。评测官负责范围解析与事实边界，真正的评级规则仍由各叶子 `SKILL.md` 定义。

```text
phase3-evaluation/
├── SKILL.md                         统一执行入口
├── catalog.json                     维度 ID、目录和 Skill 顺序的唯一映射
├── common/                          三个维度共享的知识、路由与测量能力
└── dimensions/
    ├── single-element/              4 项单一元素评测
    ├── card-component/              8 项组件/卡片评测
    └── page-framework/              7 项页面框架评测
```

## 三层职责

| 层级 | 负责什么 | 不负责什么 |
|---|---|---|
| 统一入口 | 解析 `full_19`、维度或自定义 Skill；加载共同知识；传递覆盖范围 | 不新增第 20 个评测项 |
| 维度契约 | 定义评测单位、事实输入、证据和聚合的共用边界 | 不覆盖叶子 Skill 的专属阈值 |
| 叶子 Skill | 定义具体对象、测量、判定、权重和聚合 | 不越界评价其他层级 |

## 三类判断源

Phase3 不把所有规则都压成 Phase2 字段，也不为主观视觉判断新增中间 JSON：

- `Phase2 JSON 扫描`：适用于数量、存在性、语义一致性与跨卡字段比较。
- `共用原图观察`：同一 Evaluation Agent 在 Stage A 已读原图后，于 Stage B 一次观察同时完成视觉秩序、信息层级、信息分区和信息真实性中的视觉归属判断；各 Skill 只保存现有结果行。
- `Phase2 JSON 颜色角色`：适用于组件与页面色彩计数；只统计已确认 UI 元素的规范颜色角色，页面对组件色系集合取并集，不运行取色脚本。

判断源只改变证据取得方式，不增加评测项，也不改变 Phase2 清单结构。

## 固定外部 ID

以下 ID 已写入结果、校验器和报告契约，因此保持稳定；目录改名不改变输出：

- `phase3-single_element-eval`
- `phase3-card_or_component-eval`
- `phase3-page_framework-eval`

所有代码通过 [`catalog.json`](catalog.json) 解析这些 ID，不应再用 ID 拼接物理目录。

## 共享与专属脚本

- `common/routing/`：选择解析，只决定“运行哪些 Skill”。
- `common/scripts/`：多个维度共同使用的裁剪、颜色分类和范围处理。
- `dimensions/<dimension>/scripts/`：一个维度内多个 Skill 共享的确定性辅助器。
- `dimensions/<dimension>/skills/<skill>/scripts/`：只服务一个 Skill 的测量脚本。

新增或移动 Skill 时，先改 `catalog.json`，再运行范围解析和契约测试；不要新增另一份维度路径映射。

## Skill 与校验器兼容门禁

`prepare-dispatch` 在派发词级 Agent 前核对 `common/contracts/active_validation_contracts.v3.json`：
本次选中 Skill 的内容哈希、当前运行时校验器哈希和任务冻结的契约快照必须一致。
不一致返回 `blocked_contract_drift`，不读取截图、不重跑 Phase2，也不消耗该词的评测重试预算。
Stage B 运行期间如再次发现漂移，Agent 以 `error=contract_drift:<原因>` 保留已有结果；批次
状态停在 `contract_blocked`，不得按普通评测失败将词标为 abandoned。

修复时先确认旧新版本的统计对象、证据字段与评级阈值是否语义等价。等价迁移只在完整的
版本化副本上复验；统计范围或阈值改变时，须更新校验器和回归用例，再发布新的完整契约
快照文件，保留旧快照与旧产物。当前页面视觉秩序按结果卡及筛选栏前供给卡统一去重；页面
色彩按 V5.1 口径以 ≤5 色为优秀、≥6 色为不达标。
