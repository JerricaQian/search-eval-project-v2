---
name: 单一元素评测通用契约
description: phase3-single_element-eval 维度 4 个 eval skill（eval-1-supply-quality-scanner、eval-2-color-logic-single-element、eval-3-element-compliance-scanner、eval-4-info-authenticity-single-element）共享的"三档解释与证据展示契约"+"统一输入与执行契约"骨架。各 SKILL.md 只保留本文件覆盖不到的技能专属行，不得整段复制本文件内容。
---

# 单一元素评测通用契约

本文件是 `skills/` 下 4 个 eval skill 的共享契约来源。新增或修改本维度 Skill 时，通用部分改这里，技能专属部分改各自 `SKILL.md`。

## 强制框架加载与固定流程

执行本维度任一 Skill 时，Phase3 统一入口必须将 [知识索引](../../common/references/knowledge-index.md)、本共享契约与当前 Skill 各一次冻结到 `MEITUAN_EVAL_TASK.requiredReads`；词级 Agent 按该列表各读一次。叶子 Skill 不得重复加载或覆盖本共享契约。知识索引中的卡片规范只用于按已确认卡型/变体区分元素的服务对象和适用性，不能从设计样板推断当前元素存在或缺失。

所有 Skill 共用同一执行协议：1) **读取 Phase2 JSON，确定评测目标**；2) 按**先排除→再成立→最后例外**把每个原子归入可评、排除或复核，三类必须互斥且覆盖 Phase2 原子全集；3) 执行当前 Skill 的专属核查或测量；4) 校验覆盖，复核项先停止对应元素评级，只要该元素可能改变 Tab 聚合结果就同时停止 Tab 正式评级；5) 按叶子 Skill 阈值评级并把非优秀问题行一对一投影为 issue。目标集合与覆盖分流是执行时状态，**直接从当前 Phase2 JSON 派生，不复制原清单、不另建第二份全量账本**；只有问题行、复核项和当前 Skill 明确要求的测量/全覆盖证据需要进入输出。自然裁切等已明确排除对象不构成复核阻断。叶子 Skill 的“评审流程”只展开专属动作，不再复制本段通用文案。

## 三档解释与证据展示契约

### 问题解释统一契约（必填，4 个 skill 逐字相同）

- 文案引用具体对象时：标准商卡用「商卡N」，N 为该卡在**标准商卡序列**中的出现顺序（不含异构模块，与内部 `id`/`listPosition` 无关，需重新计数）；异构模块用其描述性类型名称（如「运营聚合卡」），仅当同页面同类型异构模块出现多次时才加独立序号区分（如「运营聚合卡1」「运营聚合卡2」），该序号与商卡序号完全独立计数。禁止出现内部 ID、字段名或脚本文件名，完整黑名单见 `scripts/forbidden_copy_terms.json`。
- `assessmentRows` 是需要交给校验器和 Phase5 追溯的评测事实账本，不是 Phase2 JSON 副本；每个评级为“达标”或“不达标”的问题行必须一对一生成一条 `issues`，优秀行不得进入问题项。
- `issues[].description` 是 Phase5 唯一问题描述来源，必须由对应问题行写清当前元素原文与可见事实、命中规则或阈值、评级原因及对扫读、比较、理解或决策的直接影响；不得使用“信息不清晰”“体验较差”“建议优化”等空泛表述。
- `issues[].recommendation` 必须由同一问题行和本 Skill 既有规则生成，按“调整对象 + 具体动作 + 优秀档验收条件”书写；不得引入新阈值、补造截图外事实或在不同 issue 复用同一句建议。
- `issues` 只保留 Phase4/5 真正消费的定位、描述、评级、建议和证据字段；原始清单定位、裁剪/扫描产物与专属判定依据继续保留在 `assessmentRows`，不能被问题文案取代。

### 简洁问题卡输出与示例（强制）

**【技能专属，SKILL.md 自行定义，不在本文件覆盖范围内】**
- `description` 和 `recommendation` 各给一句技能专属生成要求与一条真实示例。

**以下 4 条 4 个 skill 逐字相同：**

- 每个 Tab 的优秀、达标、不达标结论都必须输出非空 `reason`，说明评级、覆盖范围和核心可见事实；优秀不得只写“无问题”。
- 仅当 Tab 评级为达标或不达标时，才必须记录对应问题/待优化对象的 `assessmentRows`（元素 ID、适用检查项、可见事实、命中规则、评级）；优秀不要求保留 `assessmentRows`。
- `details.evidenceMode`：有可定位问题为 `annotated-region`；兼有局部与整体/关系结论为 `hybrid`；无唯一坐标的整体/关系结论为 `original-page`。`details.screenshot` 必须指向存在的原图。
- 优秀只在评测详情保留 `reason` 解释，不得进入发现问题/治理项；达标、不达标才进入待优化项。

## 统一输入与执行契约

普通单图 manifest、黄金 `normalized + evidence` 与 `phase2.atomic-manifest.v3` 必须经 `scripts/phase2_bundle_loader.py` 转为同一只读事实视图。loader 只展开元素引用与验证来源，不确定本 Skill 的适用元素、排除 mask、测量值或评级。待评候选、像素裁剪、排除与比较均由 Phase3 依据当前 Skill 现场提取；禁止为省略 Phase3 遍历而要求 Phase2 新增评测专用字段。

**以下 4 条 4 个 skill 逐字相同：**

- Phase2 清单中的每个最小独立元素是唯一评测原子；禁止合并、重拆，或将同一行多个独立标签、价格、评分字段视为一个元素。
- Phase2 的原子边界是候选边界，不是本 Skill 的适用性结论。Phase3 仍必须遍历全部原子，按本 Skill 的对象、排除项和可见状态确定实际评测集。
- 必须完整阅读当前 Skill 的全部标准，并且仅按本 Skill 定义的对象、排除项、阈值和 `aggregate` 评级；不得迁移其他 Skill 的标准。
- 单一元素 Skill 必须逐元素执行自身规则；`overview.total` 记录本 Skill 排除图片等不适用对象后的实际评测元素数。仅在当前 Skill 的测量或校验明确要求时，才额外记录清单原子总数 `sourceManifestTotal` 与 `evaluatedUnitCount`，两者不得混用。
- `issues` 必须引用当前清单中真实的 `elementId`、`coord` 和所属 `component`；原文从 `assessmentRows` 与 Phase2 清单追溯，不在 issue 重复保存。

**【技能专属，SKILL.md 自行定义】**
- "Phase2 事实优先"一句，点名本 Skill 依赖的具体 Phase2 字段。
- 如需确定性测量脚本（如 eval-2-color-logic-single-element 的 `scripts/count_element_colors.py`），额外补一条"确定性测量优先"说明。

## 评级与 Phase5 交接

1. Phase3 先按当前 Skill 的专属阈值为每个实际评测元素评级，再按 `aggregate` 汇为当前 Tab 的一个 `rating`；问题项数等于达标与不达标问题行数，不按同一元素的命中规则数倍增。
2. `weight` 仅以键集合声明本 Skill 是二档还是三档，数值不参与结果、聚合或报告；Phase3 不输出分数字段，Phase5 不计算综合分或归一化分。
3. Phase5 只消费 `rating`、`reason`、`overview`、问题级 `description`、`recommendation` 和 Phase4 回写的 `evidenceImage`；治理优先级由 Phase5 按问题数量统一生成。

## 校验口径参考

机器可验证的部分由 `scripts/validate_eval_results.py` 统一实现（评级合法性、账本与问题项一一对应、文案黑名单、建议动作与验收结果等），本文件是给 Skill 作者和评测 agent 看的契约文本，不是校验脚本本身。
