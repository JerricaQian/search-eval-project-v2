---
name: 页面框架评测通用契约
description: phase3-page_framework-eval 维度 7 个 eval skill 共享的"三档解释与页面级证据展示契约"骨架。各 SKILL.md 只保留本文件覆盖不到的技能专属行，不得整段复制本文件内容。"Phase2 事实输入契约"整节为技能专属，不纳入本共享文件。
---

# 页面框架评测通用契约

本文件是 `skills/` 下 7 个 eval skill（eval-1-supply-module-completeness、eval-2-visual-order-alignment、eval-3-page-color-logic、eval-4-static-component-complexity、eval-5-browsing-flow-smoothness、eval-6-info-comparability、eval-7-info-redundancy）的共享契约来源。Atomic v3 输入使用根目录 `scripts/phase2_bundle_loader.py` 的只读事实视图，由各 Skill 自行派生页面库存和测量事实；`overview.total` 仍固定为 1，不要求 legacy Phase2 门禁字段。

## 强制框架加载与固定流程

执行本维度任一 Skill 前，必须先完整读取 Phase3 [知识索引](../../common/references/knowledge-index.md)、本共享契约，再读当前 Skill。知识索引中的卡片规范用于辨别标准商卡、主点、酒店/套餐、演出/影院和异构子形态的功能边界；只有 Phase2 已确认的独立边界和功能可进入页面计数或比较组。

所有 Skill 共用同一执行协议：1) **读取 Phase2 JSON，确定页面区域、模块和评测目标**；2) 按**先排除→再成立→最后例外**归类，排除、可评与复核必须互斥且覆盖当前页面的区域、模块、列表位或比较组全集；3) 按叶子 Skill 声明选择 JSON、共享原图观察或组件像素结果汇总；4) 校验覆盖，页面级任一未决复核项均停止当前页面正式评级；5) 按叶子 Skill 阈值形成唯一页面结论，并把非优秀页面问题行一对一投影为 issue。目标集合与覆盖分流直接从当前 Phase2 JSON 派生，不复制原清单、不另建第二份全量账本；页面视觉观察直接进入现有评测行，不生成中间视觉 JSON。

## 三档解释与页面级证据展示契约

### 问题解释统一契约（必填，7 个 skill 逐字相同）

- 文案引用具体对象时：标准商卡用「商卡N」，N 为该卡在**标准商卡序列**中的出现顺序（不含异构模块，与内部 `id`/`listPosition` 无关，需重新计数）；异构模块用其描述性类型名称（如「运营聚合卡」），仅当同页面同类型异构模块出现多次时才加独立序号区分（如「运营聚合卡1」「运营聚合卡2」），该序号与商卡序号完全独立计数。禁止出现内部 ID、字段名或脚本文件名，完整黑名单见 `scripts/forbidden_copy_terms.json`。
- `details.evidence.assessmentRows` 是需要交给校验器和 Phase5 追溯的评测事实账本，不是 Phase2 JSON 副本；每条评级为“达标”或“不达标”的页面问题行必须一对一生成一条 `issues`，优秀行不生成 issue。
- `issues[].description` 是 Phase5 唯一问题描述来源，必须基于对应问题行写清页面区域、可见事实或计数、命中规则、评级理由及对扫读、比较、理解或决策的直接影响；不能用“信息不清晰”“体验较差”“建议优化”等笼统语替代，也不得超出截图可见证据。
- 每个待优化页面 issue 必须有独立且非空的 `recommendation`：由同一问题行和本 Skill 既有规则生成，按“调整对象 + 具体动作 + 优秀档验收条件”书写；不同 issue 禁止复用同一句建议，不得引入新阈值。
- 页面级问题只能使用 `pageArea`、`description`、`rating`、`recommendation` 表达；组件、元素、计数与测量等技术证据保留在 `assessmentRows`，禁止将组件或元素评级伪装成页面问题。

### 简洁问题卡输出与示例（强制）

**【技能专属，SKILL.md 自行定义，不在本文件覆盖范围内】**
- `description` 和 `recommendation` 各给一句技能专属生成要求与一条真实页面级问题卡示例。

**以下 1 条 7 个 skill 逐字相同：**

- 每个 Tab 的优秀、达标、不达标结论均必须输出非空 `reason`，说明评级与核心可见事实；优秀不得只写“无问题”。

**`assessmentRows` 要求——技能专属，按下表选择：**

| 模式 | 适用 skill | 原文 |
|---|---|---|
| 达标/不达标才需要 | eval-1、eval-2、eval-4、eval-5 | 达标或不达标结论的 `assessmentRows` 必须保留整页核查事实、命中规则及评级解释；优秀不要求保留 `assessmentRows`。 |
| 每个结论恰一条（含优秀） | eval-3、eval-6、eval-7 | 每个结论必须保留恰一条 `assessmentRows`，记录整页核查事实、命中规则及评级解释；优秀同样不得省略。 |

**以下 2 条 7 个 skill 逐字相同：**

- 页面框架的每条“达标”或“不达标” issue 都必须提供存在的 `evidenceImage`，报告必须直接渲染该图，不得只显示文字结论。有精确可标注的问题必须生成当前原图的红框/高亮证据图，并使用 `details.evidenceMode: annotated-region`；同时含精确问题与整页统计时使用 `hybrid`。整页统计、跨区域关系或无唯一坐标的问题使用 `original-page`，并把 `details.screenshot` 原图路径同时写入 issue 的 `evidenceImage`，不伪造红框、不写“待人工定位”。
- 优秀仅在评测详情展示 `reason` 及原图，不进入发现问题/治理项；达标和不达标才进入待优化项。

## Phase2 事实输入契约（整节技能专属，不共享）

普通单图 manifest、黄金 `normalized + evidence` 与 `phase2.atomic-manifest.v3` 必须经 `scripts/phase2_bundle_loader.py` 转为同一只读事实视图。Phase2 只提供页面模块、卡片、元素、归属、坐标和基础可见事实；视觉秩序由原图主判，页面色彩复用组件像素产物，其余候选遍历、比较、计数和评级属于 Phase3。禁止要求 Phase2 输出与某个页面评测 Skill 绑定的预计算结论。

7 个 skill 的"Phase2 事实输入契约"节各自点名不同的 Phase2 字段（`pageFacts.modules`、`cards[].structure`、`render`、`textFacts`、`relations` 等）和判定边界，内容完全不同，不构成共享骨架。各 SKILL.md 保留自己的该节全文，不引用本文件。

## 评级与 Phase5 交接

1. 页面框架每个 Skill 在一个 Tab 只有一条页面级结论，`overview.total` 固定为 1；区域、列表位和卡片比较只是这一结论的证据，不能分别落多个问题项。
2. `weight` 仅以键集合声明本 Skill 是二档还是三档，数值不参与结果、聚合或报告；Phase3 不输出分数字段，Phase5 不计算综合分或归一化分。
3. `weight` 不含“达标”键的页面 Skill 是二档制，不能为方便叙述创建中间评级；`aggregate` 只决定如何从页面事实得到 Tab 评级。
4. Phase5 只消费 `rating`、`reason`、`overview`、问题级 `description`、`recommendation` 和 Phase4 回写的 `evidenceImage`；治理优先级由 Phase5 按问题数量统一生成。

## 校验口径参考

机器可验证的部分由 `scripts/validate_eval_results.py` 统一实现，本文件是给 Skill 作者和评测 agent 看的契约文本，不是校验脚本本身。
