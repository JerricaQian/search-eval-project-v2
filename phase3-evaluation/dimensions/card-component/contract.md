---
name: 组件卡片评测通用契约
description: phase3-card_or_component-eval 维度 8 个 eval skill 共享的"三档解释与证据展示契约"+"统一输入与执行契约"骨架。各 SKILL.md 只保留本文件覆盖不到的技能专属行，不得整段复制本文件内容。
---

# 组件卡片评测通用契约

本文件是 `skills/` 下 8 个 eval skill（eval-1-supply-completeness、eval-2-visual-order-alignment、eval-3-color-logic、eval-4-element-complexity、eval-5-info-hierarchy、eval-6-info-partitioning、eval-7-info-authenticity、eval-8-info-redundancy）的共享契约来源。

## 强制框架加载与固定流程

执行本维度任一 Skill 时，Phase3 统一入口必须将 [知识索引](../../common/references/knowledge-index.md)、本共享契约与当前 Skill 各一次冻结到 `MEITUAN_EVAL_TASK.requiredReads`；词级 Agent 按该列表各读一次。叶子 Skill 不得重复加载或覆盖本共享契约。知识索引中的卡片规范用于按已确认卡型/变体建立适用槽位、实体层和同类比较组；可选槽位或未确认字段不能由设计样板补写。`eval-2-visual-order-alignment` 是判断源例外：只直接读取当前原图逐组件判断，不读取 Phase2 JSON、卡型规范或脚本结果。

除 `eval-2` 外，其余 Skill 共用同一执行协议：1) **读取 Phase2 JSON，确定对象、语义与评测目标**；2) 按**先排除→再成立→最后例外**把每个组件、区域或比较组归入可评、排除或复核，三类必须互斥且覆盖当前 Skill 的目标全集；3) 按叶子 Skill 声明选择 JSON 或共享原图观察；4) 校验覆盖，复核项先停止对应单位评级，只要该单位可能改变 Tab 聚合结果就同时停止 Tab 正式评级；5) 按叶子 Skill 阈值评级并把非优秀问题行一对一投影为 issue。其他 Skill 的目标集合与覆盖分流直接从当前 Phase2 JSON 派生，不复制原清单、不另建第二份全量账本。`eval-2` 按叶子 Skill 的四步流程直接完整读图、逐组件判断并沿用现有评估字段，不建立比较组，不生成中间视觉 JSON；自然裁切卡因不能确定整卡行数而排除。

## 三档解释与证据展示契约

### 问题解释统一契约（必填，8 个 skill 逐字相同）

- 文案引用具体对象时：标准商卡用「商卡N」，N 为该卡在**标准商卡序列**中的出现顺序（不含异构模块，与内部 `id`/`listPosition` 无关，需重新计数）；异构模块用其描述性类型名称（如「运营聚合卡」），仅当同页面同类型异构模块出现多次时才加独立序号区分（如「运营聚合卡1」「运营聚合卡2」），该序号与商卡序号完全独立计数。禁止出现内部 ID、字段名或脚本文件名，完整黑名单见 `scripts/forbidden_copy_terms.json`。
- `assessmentRows` 是需要交给校验器和 Phase5 追溯的评测事实账本，不是 Phase2 JSON 副本；每个评级为“达标”或“不达标”的组件、区域或比较组问题行必须一对一生成一条 `issues`，优秀行不得进入问题项。
- `issues[].description` 是 Phase5 唯一问题描述来源，必须由对应问题行写清真实文案/样式/计数/关系、命中规则或阈值、评级原因及对扫读、比较、理解或决策的直接影响；不得使用空泛表述。
- `issues[].recommendation` 必须由同一问题行和本 Skill 既有规则生成，按“调整对象 + 具体动作 + 优秀档验收条件”书写；不同 issue 禁止复用同一句建议，不得补造截图外事实或新阈值。
- `applicabilityEvidence`、`visibleAbsenceEvidence`、`redundancyEvidence` 与可复现扫描数据继续保留在审计账本或专属证据中；Phase5 问题卡不复制这些技术字段。

### 简洁问题卡输出与示例（强制）

**【技能专属，SKILL.md 自行定义，不在本文件覆盖范围内】**
- `description` 和 `recommendation` 各给一句技能专属生成要求与一条真实示例。
- eval-3-color-logic、eval-4-element-complexity 必须在 `description` 中直接列出实际颜色/样式与计数，并在 `recommendation` 中引用本 Skill 已有优秀阈值，不得退化成通用建议。

**以下 1 条 8 个 skill 逐字相同：**

- 每个 Tab 的优秀、达标、不达标均须输出非空 `reason`，说明评级、覆盖范围及核心可见事实；优秀不得只写“无问题”。

**`assessmentRows` 覆盖要求——技能专属，按下表选择，不可混用：**

| 覆盖模式 | 适用 skill | 原文 |
|---|---|---|
| 仅保留问题行 | eval-1、eval-6 | 当 Tab 评级为达标或不达标时，`assessmentRows` 只记录评级为达标或不达标的问题组件；每行除既定字段外必须写出该组件的可见事实、命中规则和评级解释。优秀组件和优秀 Tab 不要求保留 `assessmentRows`。 |
| 覆盖全部评估组件/区域（不分评级） | eval-3、eval-4、eval-8 | 每个 Tab 必须输出覆盖全部评估组件或区域的 `assessmentRows`；每行保留 Phase3 的遍历/测量/候选/去重证据和评级解释，优秀也不得省略。 |
| 覆盖原图中全部可评独立组件 | eval-2 | 每个 Tab 无论评级为优秀、达标或不达标，都必须输出覆盖当前原图全部完整可见且适用的商品卡、酒店卡、商家卡（无下挂、文字下挂、图文下挂）的 `assessmentRows`。主点卡、异构卡、其他非适用卡型及自然裁切卡只能写入 `excludedUnits`，不参与 `overview.total` 或 Tab 聚合。每行只允许一个组件，并记录卡型、实际信息行数与当前卡型阈值；不得读取 Phase2 JSON、运行脚本或建立比较组。 |
| 覆盖全部完整可评测商卡（层级） | eval-5 | 每个 Tab 无论评级为优秀或不达标，都必须输出覆盖全部完整可评测商卡的 `assessmentRows`。每行必须写出该组件的 `sourceElements`（真实 elementId、原文、区域、视觉事实）、从高到低的 `weightSequence`、`tierTrace`（每个档位的成员及每次拆档/同档归并依据）、`levelCount` 和评级解释；不得用"头图/标题/基础信息/价格"等区域泛称替代实际元素与依据。任何一张卡缺少这些可复核事实时，当前 Tab 不得输出优秀，必须请求 Phase2 复核。 |
| 覆盖全部完整可评组件（关系） | eval-7 | 每个 Tab 无论评级为优秀或不达标，都必须输出覆盖全部完整可评组件的 `assessmentRows`。自然截断组件若已有双方完整可见的确认冲突，也必须额外输出问题行，但不得凭未显示区域输出优秀。每行必须列出 Phase3 枚举的主标题—图片/下挂候选对、真实 elementId、逐对语义终判、不适用原因、冲突数、评级和结论。 |

**以下 2 条 8 个 skill 逐字相同：**

- `details.evidenceMode`：可定位问题为 `annotated-region`；兼有局部与整体/关系结论为 `hybrid`；无唯一坐标的整体/关系结论为 `original-page`，且 `details.screenshot` 必须指向存在的原图。
- 优秀仅在评测详情保留 `reason` 解释，不得进入发现问题/治理项；达标、不达标才进入待优化项。

## 统一输入与执行契约

除 `eval-2` 外，黄金样本可由 `phase2.golden-normalized.v2 + phase2.golden-evidence.v2` 或 `phase2.atomic-manifest.v3` 进入 Phase3，普通任务仍读单图 manifest；这些输入必须经 `scripts/phase2_bundle_loader.py` 转为同一个只读事实视图。`eval-2` 的评测输入只有当前原图，既不调用 loader，也不从 JSON、卡型规范或脚本产物获取判断事实。

**以下 2 条 8 个 skill 逐字相同：**

- 除 `eval-2` 外，Phase2 清单中的每个最小独立元素是唯一评测原子；禁止合并、重拆，或将同一行多个独立标签、价格、评分字段视为一个元素。`eval-2` 只按原图中的独立结果组件/卡片评测，不拆分父卡内的下挂为新组件。
- 必须完整阅读当前 Skill 的全部标准，并且仅按本 Skill 定义的对象、排除项、阈值和 `aggregate` 评级；不得迁移其他 Skill 的标准。

**以下 1 条为参数化变体（骨架相同，评估单位名词按 skill 替换）：**

- 单一元素 Skill 必须逐元素执行自身规则；组件 Skill 必须逐组件 / 逐组件类型执行自身规则。组件 Skill 的 `overview.total` 必须等于实际评估组件数（或商卡数 / 区域数 / 组件类型数，视 skill 而定）。`eval-2` 的 `overview.total` 等于原图中实际完成评级的独立组件数；其他 Skill 的组件库存和计数继续从只读 Phase2 事实视图按当前 Skill 现场构造。

**以下 1 条 8 个 skill 逐字相同：**

- `issues` 必须引用当前清单中真实的 `elementId`、`coord` 与所属 `component`；原文从 `assessmentRows` 与 Phase2 清单追溯，不在 issue 重复保存。

**【技能专属，SKILL.md 自行定义，差异较大，不可归并】**
- **结果证据门槛**：每个 skill 对 `assessmentRows` 的必填字段、覆盖范围（是否含优秀）、`evidence.evaluatedUnitCount` 校验方式完全不同。eval-2 直接覆盖原图中全部可评独立组件；eval-5/eval-6 保留共享原图观察与 Phase2 对象覆盖，eval-3 保留 Phase2 JSON 颜色角色清单与组件色系并集，eval-4/eval-8 保留 JSON 全量遍历，eval-7 同时保留 JSON 语义核查和原图视觉关系核查，eval-1 保留独立双重证据门槛。
- **Phase2 基础事实优先**：除 eval-2 外，只点名本 Skill 依赖的原子边界/类型/归属/坐标、`render`/`textFacts`/`structure`/`visual` 等基础事实；候选组合、关系比较、样式去重与计数必须由 Phase3 完成。
- **判断源分工**：eval-2 直接完整读取当前原图并逐组件判断，不读取 JSON 或运行脚本；eval-5、eval-6 以及 eval-7 的视觉关系部分复用当前截图的一次共享原图观察；eval-3 只使用 Phase2 JSON 已确认的颜色角色，不读取原图或运行取色脚本；eval-1、eval-4、eval-8 与 eval-7 的文字/数值逻辑继续读取 JSON。任何原图判断都不得改变其他 Skill 使用的 Phase2 事实。
- eval-8 额外有"重建不等于重评""历史问题不默认失效""证据先于结论""商卡核查焦点与语义角色门槛"等专属治理规则，不适用于其他 skill。

## 评级与 Phase5 交接

1. Phase3 先按当前 Skill 的专属标准评级每个实际组件、区域或比较组，再按 `aggregate` 得出一个 Tab `rating`；问题项数等于达标与不达标问题行数，同一组件多个命中点不倍增。
2. `weight` 仅以键集合声明本 Skill 是二档还是三档，数值不参与结果、聚合或报告；Phase3 不输出分数字段，Phase5 不计算综合分或归一化分。
3. Phase5 只消费 `rating`、`reason`、`overview`、问题级 `description`、`recommendation` 和 Phase4 回写的 `evidenceImage`；治理优先级由 Phase5 按问题数量统一生成。

## 校验口径参考

机器可验证的部分由 `scripts/validate_eval_results.py` 统一实现，本文件是给 Skill 作者和评测 agent 看的契约文本，不是校验脚本本身。
