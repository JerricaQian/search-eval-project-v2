---
name: phase2-card-annotation
description: "对搜索结果页截图执行 Phase2 当前图片校准：以本地 CV/OCR、黄金结构范例、当前像素视觉复核、卡型契约和确定性门控，为每张截图分别生成可供 Phase3 消费的完整事实 JSON；不复制黄金字段、不合并多图，也不输出评测结论。"
---

# Phase2 轻量识别

## 1. 目标、边界与产物

Phase2 只采集事实：当前截图中的页面模块、结果卡、最小元素、坐标、可见原文与视觉规格。它为 Phase3 提供唯一事实源。

## 两条流程、一个元素契约（硬约束）

必须明确区分两条流程：

1. **黄金样本校准流（离线）**：在已经确认的截图/卡片边界内使用 PaddleOCR，并用模型视觉能力逐像素复核标题、元素语义归属和分组。当前仓库以 `golden-atomic-2.1/` 为最新黄金 JSON；`golden-atomic-2.0/` 仅作不可变回滚基线。旧 `golden-sample-results/**/*.elements.json` 已外部归档，仅在显式恢复后用于迁移重建，绝不能被生产入口导入。
2. **用户截图 Phase2 当前图片校准流**：采用同类证据链——本地 CV/OCR 生成候选，黄金样本提供结构范例，模型只读取当前整图/局部裁图以复核字面、视觉原子边界和归属。黄金字段值、坐标、数量与顺序不得注入；仍不满足契约就阻断。完整规则见 `references/current_image_calibration.v1.md`。

两条流程允许的证据不同，但输出必须遵循同一个元素级契约：

- 完整且已知卡型的卡片必须有位于 `标题区` 的主标题元素。履约标签、配送时长、影院属性等不能代替标题。商家卡、商品卡、酒店卡、演出/电影卡都适用。
- 下挂按可见供给逐项分组：`items[0]` 只拥有下挂1的 `imageElements`、`textElements`、`priceElements`、`auxiliaryElements`，`items[1]` 只拥有下挂2；禁止把多项图片、文字、价格平铺到一个 region 后丢失归属。文字下挂未渲染图片时 `imageElements=[]`，不得伪造图片。
- `基础信息区`、`商家信息区`、`标签区` 必须按独立语义字段/独立视觉 chip 拆分；例如 `15-25m²｜2人｜双床` 是面积、人数、床型三个元素。不得按整行合并，也不得按单字切分。
- 元素边界以独立视觉实体为准，不以 OCR 返回的一行文字为准。同行但颜色、间距、容器、图形辅助或交互含义不同的标签必须分别建元素；参照“面部清洁”黄金样本中“美丽荟西子医疗美容”的三个标签。
- 怀疑一行包含多个实体时，Paddle/Tesseract 仍返回同一整行只能证明文字可重复，不能证明它是一个元素，也不能作为拆分依据。必须取得两个以上有独立边界的视觉/OCR observation，或使用已复核的逐像素拆分；否则保持未确认并阻断发布。
- 文字/标签不得无上下文地成为单字符元素；`起`、`¥` 等后缀或符号必须与所属价格合并。**合法尺码例外：**当元素位于商品规格/尺码位，且标题或同卡字段明确给出 `S/M/L/XL/XXL` 尺码体系时，独立 `S`、`M`、`L` 是完整可读的尺码信息，必须保留并归入 `size_info`，不得判为乱码或元素缺失。图片元素可使用空 `visibleText`。
- 任何一条不满足，黄金校准不得标记完成，生产识别不得设置 `phase3Ready=true`。
- **结构完整不等于文字正确。** 每个 `status=confirmed` 的标题和下挂文字/价格必须有同一原图范围内的完整可见像素证据。仅通过 schema、字段非空或卡片数量检查，不得宣称黄金样本正确。
- 标题、文字下挂、常规图文下挂、异构下挂的长期识别规则采用“已校准黄金样本的结构范例 + 当前截图像素证据”，不用某张图的坐标、槽位宽高、列数或字段值充当规则。具体范例与 JSON 骨架见 `references/golden_structure_exemplars.v1.md`。
- 黄金样本只在文档明确标注的结构范围内作为范例。例如引用“茶山季（合生汇店）”是为了说明异构下挂和常规图文下挂的表达方式，不代表复制该卡的文字、位置、数量、顺序或其他区域标注。
- 黄金校准明确要求 PaddleOCR 时，实际后端不是 `paddleocr` 必须立即失败；禁止静默回退 Tesseract 后仍把产物标成 Paddle 证据。
- 黄金发布 JSON 的文字事实只保留元素级 `visibleText`；`boundedEvidence` 仅保留像素坐标溯源，不重复发布 observation `text`，也不发布 `ocrConfidence`。OCR 原文与置信度只允许存在于离线过程证据目录，不能成为黄金或 Phase2 最终 JSON 的消费字段。
- 图片内部的包装字、品牌字和装饰字属于图片像素，不另建 UI 文本或标签元素；只有与图片分离、承担界面语义的可见文字才拆成元素。
- 同一可见像素实体在一张卡内只能有一个规范所有者。下挂名称、价格、折扣、销量等归具体下挂项，不得同时复制到泛化 `标签区`；价格区中的价格不得同时保留在信息区。相同原文且相同坐标，或相同原文、同实体类型且一个框高度覆盖另一个框的嵌套标注，均视为重复所有权并阻断黄金发布。
- 元素语义类型、渲染类型与 Phase3 遮罩必须一致：`图片/头图/主图/海报/视频` 类元素必须为 `visual.entityKind=image`、`render.isPhoto=true`、`render.isSystemUi=false`，且不得携带 `textFacts`。禁止因类型别名缺失把照片当文本，导致 Phase3 把图片纹理计入 UI 颜色或 icon。
- `naturally_cropped` 表示可见像素已确认但被视口自然截断，不等于 OCR/视觉事实不确定。结果流尾卡的下挂完全未露出时，可继承同组上一张已确认卡型，但只发布已看见的卡头与信息，不补造屏外图片 ID、下挂内容或 `itemGroups`，不可见缺口不触发反复返工；生成 Phase3 投影时保留自然裁切状态，并只对可见部分评测。真正的 `uncertain` 或完整可见卡的复核拓扑/最终卡型冲突仍阻断依赖该事实的流程。

### 结构参照法（优先于坐标模板和 OCR 行形状）

识别顺序必须是：**判断卡型 → 判断区域 → 按可见边界枚举每个下挂项 → 为每项选择最接近的黄金结构范例 → 在当前截图中定位该项的实际语义元素 → 使用当前流程允许的 OCR/模型证据复核可见原文**。OCR 是读取已经定位的元素，不负责凭文字行形状创造卡片结构。

使用黄金范例时遵守四条原则：

1. **学习结构，不复制答案。** 范例规定字段怎样归属、哪些元素可选、异构如何表达；当前截图独立决定文字、坐标、数量、顺序和裁切状态。
2. **按项判断，不按区域套一种模板。** 同一下挂区域中的每个可见项分别选择结构；一个项与范例匹配，不构成停止识别其余可见项的条件。
3. **语义角色不是固定槽位。** 商品/服务文字、现价、价格折扣、原价、销量等由视觉关系和语义决定，可换行、移位或缺省；它们没有跨截图固定的像素宽高或相对偏移。
4. **只记录可见事实。** 页面边缘项按当前可见内容建立同样的元素结构并标记裁切，不补造屏外文字；证据不足则 `uncertain`，不得用范例字段值填空。
5. **先分视觉实体，再读实体文字。** OCR 合并框只是候选；当前截图中独立的颜色段、容器、间隔或功能单元具有更高的分元素优先级。多个 OCR 后端冲突时，选择与独立视觉实体边界一致且覆盖完整字形的证据，不选择“文本更长”的合并框。同一容器内的图形辅助与文字必须是一个标签原子：例如“红色闪电+神价”、“神券+立减/满减金额”、“黄色闪电+闪购”各自只建一个 `tag` 元素，图形写入 `visual.graphicAssist`，不再另建 `icon`。只有脱离标签容器、可独立表意和点击的图形才建 `icon`。
6. **特殊字体价格标签字面归一。**当价格旁的红色闪电与双字价格权益文字处在同一容器中时，该组合的规范原文为“神价”。OCR 因特殊字体输出“礼价”时，必须在当前像素确认红色闪电+同容器后归一为“神价”，并在校准审计中保留 OCR 变体和归一理由。不得脱离该视觉上下文对普通“礼价”文案做全局替换。
7. **神券下挂先看区域、再看语义。**只有同时满足以下条件，才把当前结构识别为神券下挂：位于 `下挂商品区`、`文字下挂区`、`下挂区` 或 `服务下挂`；位于所属下挂项可见内容的最左侧；文案表达明确的折扣优惠或使用门槛（如“¥13 满38可用”），并同时出现引导用户“领取”或“使用”的提示。不得仅凭“神券/神劵”、红色文字、金额或相邻位置单独成立。发布 JSON 时沿用现有分区、坐标、`items[]` 归属和 `semanticRole: promotion`：共同表达同一优惠的金额、门槛与“领取/使用”须归入同一个下挂项，不复制到泛化 `标签区`，也不得拆成多个独立优惠下挂。

遇到新布局时，先在 `references/golden_structure_exemplars.v1.md` 中寻找同层级结构；只有视觉结构确实不同才新增异构结构及对应黄金范例。实现层的坐标扩框、卡片底边裁剪和遍历控制只是保障上述原则的手段，不能反过来定义业务规则。

### 规则沉淀层级

从错误案例更新规则时，按 **根因 → 可迁移的结构原则 → 具名黄金样本及 JSON 正例 → 适用边界 → 实现防回归** 记录。主 Skill 和结构范例描述前四层；像素阈值、裁剪扩框、循环退出条件等只进入算法实现或测试。除非数值本身属于输出协议，不把单张截图的像素经验提升为长期业务规则。

只做：**每张截图 → 本地 CV/OCR 候选 → 当前图片全量视觉复核 → 卡型/元素识别 → 整页门控 → 该图独立元素清单 JSON → 枚举、schema 与校准审计校验**。

不做：整页画框 PNG、外部设计稿操作、体验评级、问题结论、人工复核任务、跨截图坐标复用，以及用黄金样本补造当前截图事实。

每张截图必须独立生成且只生成一个主 JSON；不同截图不得合并进同一个识别 JSON。该截图的唯一 Phase3 输入是：

- `screenshots-out/elements_<截图文件名>[_<tag>].json`：只包含对应截图的页面模块、卡片、最小元素、视觉事实、关系及 `recognition` 整页门控状态。

同名 `.audit.json`、可选 `.recognition-audit.json` 和 `.artifacts/.../phase2/` 只用于调试、回归与追踪来源，不是 Phase3 的第二事实源。门控失败仍必须写出主 JSON，但其中 `recognition.phase3Ready=false`，Phase3 必须拒绝消费。

批量黄金回归产生的 `index.json` 只索引每张截图自己的 `canonicalManifest` 并汇总指标；它不包含、替代或合并各截图的完整识别事实，永远不是 Phase3 输入。

`uncertain` 只表示当前证据不足；绝不表示缺失、错误、不达标、优秀或待创建的人工任务。

## 2. 当前规则与数据源

| 用途 | 唯一来源 |
| --- | --- |
| 页面模块与结果流顺序 | `references/search_result_page_taxonomy.v1.json` |
| 卡型、分区与元素候选 | `references/search_card_taxonomy.v1.json` |
| 卡型边界与最小证据 | `references/card_recognition_contracts.v1.json` |
| 酒店单列/双列/民宿与混排细则 | `references/hotel_card_algorithm.v1.md` 与 `references/hotel_card_element_contract.v1.json` |
| 当前图片全量校准与审计 | `references/current_image_calibration.v1.md`；整图一次、冲突处局部复核、逐元素交叉校验 |
| 标题、文字下挂、图文下挂与异构下挂结构范例 | `references/golden_structure_exemplars.v1.md`；只学习结构，当前截图独立取证 |
| 已逐像素复核的黄金标签拆分 | `references/golden_tag_split_reviews.v1.json`；只供离线黄金校准与回归，不向生产注入字段值 |
| UI/图标检测、OCR 与颜色事实融合 | `references/screen_parser_backend.v1.md`；处理非文本 UI、图标漏检或评估 OmniParser 时读取 |
| 黄金样本聚合几何经验 | `references/learned_card_geometry_profiles.v1.json`；只作软证据 |
| OCR 文本角色候选 | `references/search_page_semantic_rules.v1.json` |
| 清单及审计 schema | `phase2-card-annotation/scripts/validate_element_manifest.py` |
| 黄金样本回归 | `golden-samples/` 截图与 `golden-atomic-2.1/` 最新 JSON；`golden-atomic-2.0/` 仅供回滚；不得外推到新截图 |

`extract_product_card_elements.py` 仅用于已登记文件名的黄金回归，不能用于新截图。新截图只能消费本次 CV/OCR、卡型候选和本地像素/拓扑证据。

## 3. 执行流程

对每张截图串行运行；所有路径由 `projectDir`、`batch`、`query`、`tag` 推导，禁止写死搜索词或历史目录。

生产入口只有一套契约，分为候选、当前像素复核、发布校验和有界纠错。候选命令只保留本地 CV 几何/图片事实，不能产出可供 Phase3 使用的 manifest；发布命令必须消费同一截图的候选 bundle 与当前像素复核。`<pythonBin>` 由调用方注入；可移植任务使用 `workflowArgs.pythonBin`，不得假定项目 `.venv` 或 `python3` 别名。

```bash
<pythonBin> phase2-card-annotation/scripts/run_phase2_recognition.py \
  --stage candidate --query <query> --screenshot <screenshot> --output <candidate-bundle.json> \
  --artifacts-dir <this-batch-artifacts-dir>
```

候选 bundle 固定为 `phase3Ready=false`。模型完成整图一次、全元素核对后，将新增/替换观察和 `completeCurrentPixelReview:true` 写入 `--visual-review` JSON，再运行发布命令：

```bash
<pythonBin> phase2-card-annotation/scripts/run_phase2_recognition.py \
  --stage publish --query <query> --screenshot <screenshot> \
  --candidate-bundle <candidate-bundle.json> --visual-review <visual-review.json> \
  --output <elements.json> --recognition-audit <elements.recognition-audit.json> \
  --artifacts-dir <this-batch-artifacts-dir>
```

发布命令从最终 manifest 自动生成校准审计；禁止手改 audit 或 `phase3Ready` 解锁。记录格式和读图上限见 `references/current_image_calibration.v1.md`。

发布和 manifest 校验后必须运行 `scripts/build_phase2_retry_plan.py`。`retryRequired=true` 时按 `targets[].cardId` 写下一次 visual review 的 `cardOverrides`，并重新执行完整 candidate→review→publish→validate；不得保留一份失败证据就结束任务。只有达到任务的 `phase2MaxAttempts` 后仍失败才允许阻断 Stage A。

以下是该入口内部的可审计展开流程；只用于诊断或替换某一识别步骤：

```bash
bash phase2-card-annotation/scripts/run_cv_facts.sh <screenshot> --output <facts.json>
<pythonBin> phase2-card-annotation/scripts/build_search_page_structure.py <facts.json> --output <structure.json>
<pythonBin> phase2-card-annotation/scripts/build_search_result_candidates.py <facts.json> <structure.json> --output <candidates.json>
<pythonBin> phase2-card-annotation/scripts/map_result_card_semantics.py <facts.json> <candidates.json> --output <card-semantics.json>
<pythonBin> phase2-card-annotation/scripts/map_search_page_semantics.py <facts.json> <structure.json> --output <text-semantics.json>
<pythonBin> phase2-card-annotation/scripts/validate_phase2_recognition.py \
  --facts <facts.json> --result-candidates <candidates.json> \
  --card-semantics <card-semantics.json> --text-semantics <text-semantics.json> \
  --output <recognition-gate.json>
# 仅当上一步阻断：主入口自动执行一次以下卡内定向重识别，随后重建全部下游候选并再次整页门控
<pythonBin> phase2-card-annotation/scripts/reprocess_bounded_cards.py \
  --screenshot <screenshot> --facts <facts.json> \
  --result-candidates <candidates.json> --card-semantics <card-semantics.json> \
  --recognition-gate <recognition-gate.json> --output <facts.retry.json> \
  --report <bounded-card-reprocess.json>
<pythonBin> phase2-card-annotation/scripts/build_phase2_manifest.py \
  --query <query> --facts <facts.json> --result-candidates <candidates.json> \
  --card-semantics <card-semantics.json> --text-semantics <text-semantics.json> \
  --recognition-gate <recognition-gate.json> --output <elements.json>
<pythonBin> phase2-card-annotation/scripts/validate_element_manifest.py <elements.json> \
  --audit <elements.audit.json>
```

前五个文件是**过程候选 JSON**：保留 OCR/CV 原始坐标、双版面 OCR 一致性、颜色像素提示和未决项，便于重新识别；不使用或发布 OCR 置信度。其中每个文字/图片候选直接携带可转写为 Phase3 的 `render`、`textFacts`/`visual` 像素事实。`build_phase2_manifest.py` 只把同一次识别结果写入统一 JSON，不制造新事实。已确认元素进入 `cards[].regions[].elements[]`；未确认项进入主 JSON 的 `recognition.semanticHookFindings/reprocessTargets` 与 `pageFactInventory.uncertainElementIds`，绝不被误当作“页面没有”。

固定顺序：**本地 CV 页面/模块/图片候选 → 当前截图 LLM 视觉复核（文字、卡片和模块清单）→ 复核卡片拓扑合并 → 结果卡候选 → 卡型最小契约 → 卡内分区/文本角色 → 整页门控 → 更新最小元素/所有权/关系 → 全量当前像素审计 → 枚举与 schema 校验**。任一卡失败即整页阻断；禁止部分页面进入 Phase3。模型复核覆盖全部已发布元素和漏标扫描，不只处理 OCR 失败字段。

### 当前图片复核与发布门禁（2026-08-20 补充）

- 初次 OCR 前排除系统状态栏、调试覆盖层等非页面画布；这些区域不得进入文字或图片候选集。
- 有界重识别的来源框若完全位于正文列左侧或与正文列不相交，必须作为图片内文字/非正文证据拒绝或重分配；禁止把正文列硬设为左边界并生成 1px 或其他退化裁剪。回归必须覆盖 `source=[124,1582,76,25]`、`textColumn=322`。
- 发生 OCR 垃圾文本、卡边界错误或卡型回退时，门控只负责定位失败点；必须继续执行定向重识别、结构重建和当前图片局部复核，直到通过全部发布校验或明确报告仍未解决的事实缺口。不得把“已拦截”当作交付完成。
- 主会话的当前图片局部复核可以作为显式证据源，但每个修订字段必须记录 screenshot、卡片裁剪、字段坐标、readId 和来源 `main_session_local_visual_read`；被替代的 OCR 候选保留为 rejected 审计事实，不能泄漏进发布元素。
- `validate_phase2_recognition.py`、`validate_element_manifest.py` 和 itemGroups/枚举审计必须全部为真，才可写 `recognition.phase3Ready=true`。任一后置 schema 或所有权校验失败都必须回写 `phase3Ready=false`，不得仅因 OCR 门控通过而放行。
- 每次当前图复核都必须将选定卡型与 `golden_structure_exemplars.v1.md` 做**结构差距审计**：审计须逐卡给出范例章节、当前缺口、涉及候选 ID 和下一步局部复核/重建动作。黄金只决定“应如何分区、逐项归属、哪些可见原子必须验证”，不得提供当前文字、坐标、数量或顺序。已正确排除的图片内包装字记录为非阻断提示；未拆分的 chip、缺失的下挂项锚点、未确认的商品名/价格则必须阻断发布。

生产入口的强制顺序是：CV 页面/组件/图片候选 → **当前图 LLM 视觉复核**（`--visual-review`）→ **结构/卡型/定位门禁** → **卡型、元素、itemGroups、枚举、schema、审计门禁** → Phase3。视觉复核必须逐卡声明 `cardTypeCandidate`、区域拓扑（头图区/商家信息区/权益区/下挂区）及图文下挂项与图片、标题、价格的归属；横向或底部仅子项可见时，将子项标为 `naturally_cropped`，不得把整张已完整可见的卡降为不完整。`--visual-review` 缺失、复核不完整或任一最终校验失败时，主 JSON 必须保持 `phase3Ready=false`。

### CV + LLM 生产模式

`run_phase2_recognition.py` 固定运行 `cv_llm`：关闭 Tesseract 与 Paddle，仅保留本地 CV 的模块、卡片和图片候选；文字、语义原子、卡片拓扑和归属必须来自带 `completeCurrentPixelReview:true` 的 `--visual-review`。缺少该记录、类型注册表不一致、结构/枚举/schema/审计任一门禁失败，都必须阻断。运行目录仍必须保留，以复核卡数、元素数、标题/价格/标签完整性及门禁结果。

卡型标识与展示名称只读取仓库根目录 `card-type-registry.v1.json`。详细的 Phase2 区域契约位于 `references/search_card_taxonomy.v1.json`，Phase3 解释位于 `phase3-evaluation/common/references/card-taxonomy.md`；三者通过同一 id 对齐，禁止在任一说明中手写另一套名称。

Tesseract 默认用 `PSM 6` 与 `PSM 11` 两种独立布局识别。主输出不得按置信度切换；核心语义须通过 `ocr_consensus` hook：结构化数字要求数值锚一致，自然文本只允许确定性的包含或高相似关系。价格行可在相同数值锚下选择脚本连贯性更好的独立布局文本；疑似价格可做少量有界遮罩复读，但都必须保留原文、独立布局和接受理由，禁止无锚纠错。行内相邻的汉字碎片先按空间合并，明显分隔的标签、价格和标题保持独立。

照片检测除多色轮廓外，允许以“大面积 + 高像素方差 + 足够彩色像素 + 非细长几何”补充低色相商品/商家照片；该规则不检测圆角容器，不按业务词推断图片。

当前生产入口不调用 PaddleOCR 或 Tesseract，也不接受任何 OCR 运行参数。门控失败时先保留 CV 过程事实，使用当前截图复核和有界结构重建；不能把旧 OCR 参数、环境检查或回退后端作为发布通道。

跨机器不能假定 `git clone` 已带 Paddle 能力：运行时包和模型均不进入 Git。首次准备必须用实际执行 Phase2 的同一个 Python 运行 `phase2-card-annotation/scripts/setup_phase2_ocr.py --all`；该入口安装 PaddlePaddle/PaddleOCR、从 Paddle 官方 BOS 源下载锁定模型、校验 SHA-256 并执行本地推理冒烟测试。`phase2-card-annotation/scripts/setup_phase2_ocr.py --check` 或 `bash setup.sh --with-ocr` 只检查不安装；未通过检查不得声称环境具备 Paddle 能力。

非文本 UI/图标候选与 OCR 分工按 `references/screen_parser_backend.v1.md` 执行。OmniParser 只可作为可选的本地候选检测后端：它提供图标/交互区域框及可选语义描述，不能替代 PaddleOCR、卡型契约、逐元素颜色测量或最终语义归属。依赖、权重或许可条件未满足时不得宣称已启用，也不得让其缺失阻断现有确定性 CV/OCR 流程。

## 4. 事实源、校验与参数化纪律（阻断）

1. 元素、模块/卡片边界、履约事实、原文、渲染或视觉事实有误，必须修正 Phase2 manifest；不得在 Phase3/4 结果中打补丁。Phase2 不判定餐饮外卖、闪购等业务线归属；“外卖/配送”等只作为履约事实，不能单独推导业务。
2. 每次新建、复用或修订 manifest 后都必须校验；`valid != true` 时不得进入 Phase3。
3. 收到 Phase3 回退请求时，保留旧 manifest/audit/过程候选，按新证据重建 Phase2，再重跑受影响的 Phase3；不得只改下游结论。
4. 禁止固定搜索词、机器路径、历史 `/tmp` 或场景脚本输出作为生产入口。
5. `validate_phase2_recognition.py` 是本地候选门控：OCR 碎片比例超限、异常文字、无结果卡、卡内可用事实不足、卡型未确认或未通过卡型最小契约时，必须写出 blocked JSON 并重跑本地 CV/OCR。随后当前图片校准仍须复核全部发布元素；模型只能按当前像素修正事实，不能用语言知识改写原文。
6. 门控 hooks 按顺序执行：字段文法、字符/脚本连贯性、双布局 OCR 一致性、同行碎片、语义原子性、卡型语义契约。hook 只报告异常和阻断，不按语言模型/词典改写 `rawText`。有界重识别只允许两种可追踪更新：保留被第二裁剪证明的原 OCR 字面子串，或以卡内 Paddle 直接识别替换明显混合脚本失败行；两者都必须保留原文、裁剪和接受理由。
7. 结果流最后一张重复卡自然触底时，若上一张卡已确认具体已知卡型且本卡无明确广告证据，可继承上一张卡型；只豁免因截断不可见的必需字段与语义锚点。当前屏幕已显示文字的乱码、OCR 分歧和字段文法错误仍阻断整页。
8. 中文语言纠错器只能作为可选异常检测 hook：检测到疑似形近字/不通顺时返回失败行和候选原因，随后重跑原图裁剪；不得把纠错器生成的句子直接写入 manifest。未安装本地模型时不得伪装成已完成语义校验。
9. 黄金 JSON 的字段值/坐标不能成为当前截图答案。`golden-atomic-2.1/` 可作为生产识别的只读结构范例，但禁止传入识别脚本或复制文字、坐标、数量、顺序；`golden-atomic-2.0/` 只用于回滚审计。旧格式迁移只有在显式提供外部归档的 `--legacy-source-root` 时才可运行；仓库内不得重新持久化旧 `elements.json`。

   黄金文本发布以结构范例和当前卡片的完整像素证据共同门控：标题与下挂不能由预设槽位生成；文字元素非空并不代表正确，必须能追溯到同卡、同元素且覆盖完整可见字形的 bounded observation；校准命令指定 `--require-backend paddleocr` 时任何后端降级均阻断。已有非空标题也必须按标题结构重新核验。

Phase3 通过 `scripts/phase2_bundle_loader.py` 读取 atomic v3，完成枚举、契约版本和 publication 门禁后只在内存中建立兼容视图。taxonomy SHA-256 仅供溯源，不作为门禁。禁止持久化 Phase3 派生投影。

`phase2.atomic-manifest.v3` 是页面可重建的原子结构投影，也是当前黄金源。34 份离线黄金
统一保存在 `golden-atomic-2.1/`。`scripts/build_atomic_manifest_v3_goldens.py` 默认以这 34 份
atomic v3 为输入，重新执行枚举、截图哈希和结构校验，保持坐标与原子事实不变，并重建
汇总索引；不再依赖旧 `elements.json`。仅建模块若没有可靠外框则省略 `bounds`，不得按
屏幕比例、固定高度或相邻模块均分补框。审计摘要只保留在批量
`index.json`，不再生成逐 manifest audit sidecar；索引必须保持 34 图、135 卡的回归基线。

所有 Phase2 JSON 在写出前必须加载 `references/search_card_taxonomy.v1.json` 执行枚举校验；
输出必须记录该枚举文件的 `contractVersion` 与相对路径；可选记录 SHA-256 供溯源。枚举文件缺失、版本或
卡型不在枚举内、封闭枚举槽位出现非法值时一律阻断发布；taxonomy SHA-256 不一致仅记录为溯源差异，禁止使用脚本内
硬编码近义词集合绕过该门禁。

标题区必须保留标题前后独立视觉实体：履约标使用 `fulfillment_tag`，商家标使用
`merchant_tag`，标题后景点等级使用 `scenic_rating_tag` 且 `kind=tag`；实际前置、后置或行内位置由当前元素
坐标决定，不另存预计位置。商品头图上的「时令、冰镇」等钻石属性使用
`product_attribute_tag` 并归属 `head_media`，不得因旧字段名为“履约标签”而归入
`fulfillment_tag`。标题文字不得吞入已由像素确认的前后标签；没有独立像素边界时也不得按
枚举词硬切。所有 `kind=tag` 元素的槽位名必须以 `_tag` 结尾，所有 `_tag` 槽位也只能
引用 `kind=tag` 元素；例如 `promotion_tag`、`guarantee_tag`、`gift_tag`。批量 audit 的
`titleAffixErrors` 必须为 0 才可发布。

```bash
<pythonBin> phase2-card-annotation/scripts/build_atomic_manifest_v3_goldens.py
```

Phase3 通过 `scripts/phase2_bundle_loader.py` 直接消费 atomic v3；入口核对枚举与契约版本、截图哈希、publication 状态及元素引用，任一门禁不一致立即失败；taxonomy SHA-256 仅作溯源记录。`countDecision`、`dedupDecision` 等 Phase3 派生字段不得写回黄金 JSON。

10. 黄金回归只在整条推理完成后做 `expectedCardTypes`/`predictedCards` 对照，绝不能向生产识别传入期望卡型：

```bash
<pythonBin> phase2-card-annotation/scripts/rerun_golden_cv.py \
  --output-dir .artifacts/golden-cv-rerun
```

```bash
<pythonBin> phase2-card-annotation/scripts/validate_element_manifest.py \
  <manifest.json> --audit <manifest.audit.json>
```

同一 `comparisonGroupKey` 有两张以上完整结果卡时，追加 `--require-alignment-anchors`。Phase3 的视觉层级、静态复杂度和真实性门槛分别由其 skill 追加对应校验参数；Phase2 不输出评级。

## 5. 页面与组件事实

根对象必须且只能含七个发布键：

```json
{
  "query": "布洛芬",
  "screenshot": "/abs/path/布洛芬_全部_1.png",
  "cards": [],
  "recognition": {},
  "pageFacts": {},
  "pageFactInventory": {},
  "relations": []
}
```

轻量模式不发布 `annotatedImage`；批次级 Phase5 统一使用各词级 Agent 交付、并由 Phase4 回写到问题项的原始 `screenshot`。旧清单中的该字段仅为兼容读取，不能作为新产物要求。

`pageFacts` 至少记录 `screen`、`isContinuation`、`viewport` 和 `modules[]`。每个 module 含 `id`、`moduleType`、`coord`、`visibleStatus`、`contentRole`、`isListPrefix`、`isListItem`。

- 模块按视觉/功能独立区域登记：搜索栏、Tab、图筛、业务图筛、快筛、营销条、主点卡、异构卡、结果列表等。
- 普通连续结果只登记一个 `result_list`；Tab 或快筛内部项目不得误写为页面模块。
- 插入结果流的异构卡使用 `isListItem=true` 和连续 `listPosition`；首张结果前的提示/营销条使用 `isListPrefix=true`，不占结果位置。
- `pageFactInventory` 含 `complete`、`scanned`、`uncertainElementIds`、`notes`。看不清、自然触底和跨屏续接必须如实记录，不能写成“缺失”。

## 6. 卡片、分区与最小元素

每张卡必须含 `cardId`、`卡片类型`、`coord`、`regions`、`structure`、`factInventory`。坐标一律为 `[x, y, width, height]`。

```json
{
  "cardId": "C1",
  "卡片类型": "商品卡片",
  "coord": [16, 980, 1192, 480],
  "regions": [{"name": "头图区", "coord": [32, 996, 300, 300], "elements": []}],
  "structure": {
    "visibleStatus": "complete",
    "cardTypeCode": "product",
    "layoutMode": "left_image_right_text",
    "layoutSignature": "image|title>subtitle>price>merchant",
    "comparisonGroupKey": "flash_delivery|product|left_image_right_text",
    "isResultListItem": true,
    "isHeterogeneous": false,
    "listPosition": 1,
    "regions": []
  },
  "factInventory": {"complete": true, "scanned": ["card_boundary", "regions", "images", "text", "render_state", "visual_spec", "layout", "relations"], "uncertainElementIds": [], "notes": []}
}
```

卡型和分区以 `search_card_taxonomy.v1.json` 为准，不能把商品卡、商家图文下挂、文字下挂、无下挂商家卡、酒店、套餐、演出/电影和主点卡套入同一模板。只登记当前截图可见的分区。

卡型决策只有三步：

1. 在已知卡型中，仅保留满足 `card_recognition_contracts.v1.json` 全部 `minimumEvidenceGroups` 且未命中 `forbiddenFeatures` 的类型；多个通过时才选择最接近者。
2. 没有已知卡型通过且存在明确广告标时归 `广告卡`。
3. 否则，只要是稳定独立渲染单元且有可见内容，归 `异构卡`；禁止输出 `unknown`。

不同卡型必须使用各自边界策略：商品卡以单商品主图、标题和价格重复为界；商家图文下挂必须吸附下一商家头图前的商品图组；商家文字下挂必须吸附下一商家头图前的服务文字块；无下挂商家卡以商家头图、标题和基础信息为完整卡头，不能因缺少下挂误归异构卡；酒店单列按逐卡头图/标题锚切分，双列按独立网格单元逐格切分，头图高度逐卡量取；演出按竖版海报、电影按影院标题和场次块切分；套餐保持主图、概要和价格在同一卡内；主点卡位于普通结果列表前且不占 `listPosition`。完整细则只以卡型契约文件为准。

query 只写入输出上下文，不是卡型或页面结构主键。同一 query 的不同截图必须独立识别；混排页必须逐卡应用契约。酒店页尾截断格只可从同列上一张已确认酒店卡继承，不能从行内相邻异构卡继承。处理酒店样本或酒店识别失败时，读取 `references/hotel_card_algorithm.v1.md`；需要双列房型元素分区时再读取 `references/hotel_card_element_contract.v1.json`。

同一 `comparisonGroupKey` 中有两张以上 `visibleStatus=complete` 的结果卡时，每卡必须提供 `layoutAnchors.image/title/primaryInfo` 与 `layoutAnchorRelation`。它们只描述卡内相对位置，不能写评测结论。

每个最小元素必须含 `id`、`所属组件`、`元素类型`（`文本`、`图片`、`标签`）、`坐标`、`isExcluded`。可读文字（含标签）只在 `textFacts.rawText` 发布一次；图片不填伪文本。排除项另写非空 `excludeReason`，活跃元素不发布该键。`内容简述` 仅兼容读取旧清单。真实头图、商品图、图筛配图均单列为图片；叠在图片上的系统标签/icon 仍单列。

`regions[]` 必须按语义阅读顺序发布，而不是按 OCR 返回顺序：标题/实体标题 → 副标题 → 基础信息 → 价格 → 标签 → 商家/下挂 → 媒体。这样“外卖”等小标签即使被 OCR 先识别，也不能把商品标题藏在基础信息之后。

**履约标签位置防错规则**：`外卖`、`团购`、`到店`、`闪购`只是候选词，**不能仅凭文字决定区域**。必须先按当前图确认其相对标题位置：与标题纵向重叠且位于标题左侧或标题起始范围内时，发布为 `元素类型:"标签"`、`textFacts.semanticRole:"fulfillment"`、`styleKey` 第三段为`履约标`、`region:"标题区"`；若在标题下方或独立信息行，则保留其履约语义并归入基础信息区/实际可见区域。配送时长、起送价、配送费同样按当前位置与结构归属。每次变更此规则必须同时覆盖“标题前缀”和“标题下方”两个回归用例。

为单元素色彩评测固定语义边界：相邻但语义独立的价格、销量、履约标、权益标签、角标和图形标签必须各自成为一个元素，`坐标` 即该元素唯一采样边界；同一标签容器内不可分的文字与图形才保留为一个标签元素。元素外背景、照片、相邻 UI 与不属于该语义实体的装饰只保留在 CV/OCR 与校准审计，不能扩大元素坐标。边界无法确认时保留 `uncertain` 并阻断依赖颜色计数的 Phase3，不按搜索词、旧裁剪或固定样例补写。

## 7. 最小元素渲染、文本与视觉规格事实

所有元素写 `render`；文字再写 `textFacts`；标签/icon 与可判视觉实体写 `visual`。

```json
{
  "id": "C1-title",
  "所属组件": "C1",
  "元素类型": "文本",
  "坐标": [360, 996, 620, 52],
  "isExcluded": false,
  "render": {"visibleStatus": "confirmed", "renderState": "normal", "isPhoto": false, "isSystemUi": true},
  "textFacts": {"rawText": "布洛芬咀嚼片", "textStatus": "complete", "semanticRole": "title", "emphasisLevel": "primary", "fontSizeBucket": "medium", "fontWeightBucket": "bold", "textColorRole": "neutral"}
}
```

发布给 Phase3 的元素只保留 `visual.colorRole` 与 `styleKey`；具体 `textColor`、`backgroundColor`、`borderColor`、色彩取样证据及布尔重复标记保留在 CV/OCR 与校准审计。标签/icon 仍必须记录 `containerShape`、图形辅助和是否计入复杂度。图片不在 Phase2 预计算综合色数，必须写 `render.isPhoto=true` 与准确坐标，Phase3 再据此建立排除 mask 并运行确定性像素统计。

- `renderState`：`normal | placeholder | blank | load_failed | naturally_cropped | abnormal_clipped | garbled | uncertain`；它是事实，不是结论。
- `textStatus`：`complete | naturally_ellipsized | abnormal_clipped | garbled | uncertain`。看不清就留空/`uncertain`，不得猜测。
- `semanticRole`：`title | subtitle | price | rating | sales | location | fulfillment | promotion | filter | recommendation | other`。
- 完整结果卡的文字若存在 `unknown`/`uncertain` 规格，必须记入 `factInventory.uncertainElementIds`；该卡不能作为视觉层级“优秀”证据。

## 8. 标签 / icon 视觉属性契约

这是 Phase3 静态元素复杂度的唯一输入。Phase2 只记录事实，不计分、不评级、不预聚合数量。

Phase2 只发布已确认的标签/icon 原子、归属、坐标和基础视觉事实，不发布 Phase3 专用的预计数、预去重或评级结论。Phase3 必须遍历当前组件的全分区原子，现场测量样式、决定纳入并去重计数。Phase3 像素扫描若发现原子边界外的疑似漏标，可触发 Phase2 基础识别回退；未确认 blob 不能直接参与正式计数或评级。

扫描范围：头图角标/腰封、标题前 badge、履约标与独立 icon、基础信息、标签区、价格旁促销标、文字下挂、每个图文下挂商品的角标/腰封、保障标与图筛项。每个独立标签、角标、券标、腰封和独立 icon 都拆为一个元素；不能因颜色或轮廓相近而合并。同一标签容器内的闪电/奖杯等图形辅助与文字必须合为一个 `tag` 原子并记录 `graphicAssist`。

神券下挂是上述“独立标签拆分”规则的结构化例外：先按前述区域、最左位置、优惠语义和“领取/使用”提示四项联合确认其属于一个优惠下挂，再按当前像素保留内部可见原子；这些原子仍共同归属于同一个 `items[]` 下挂项，供 Phase3 按一个神券下挂实例理解，不能因为 OCR 返回多段文字而按多个独立标签解释。

标签/icon 的 `visual` 必填。当前阶段不做通用圆角容器检测；未由像素事实确认时，`containerShape` 写 `unknown`，不得按业务词猜形状：

```json
{
  "entityKind": "tag",
  "visualStatus": "confirmed",
  "colorRole": "red",
  "containerShape": "unknown",
  "graphicType": "无",
  "graphicAssistRole": "无",
  "countedInComplexity": true,
  "dedupWithElementIds": [],
  "styleKey": "标签|red|券标|unknown|无"
}
```

`entityKind` 只能是 `tag | icon | text | image`；`colorRole` 只能是 `neutral | red | orange | yellow | green | blue | purple | multicolor | unknown`。`styleKey` 固定为“实体类别｜颜色角色｜语义角色｜容器形态｜图形辅助”，其中第三段是标签视觉语义的唯一发布位置；只有五段都相同并写明理由时才可去重。

每张完整卡还必须有 `visualInventory`（各可见分区的已确认元素、styleKey、是否计入与未确认项）和 `tagScanChecklist`。每项包含 `candidate`、`status: found|not_found|uncertain`、`checkedRegions`、`elementIds`。检查表提醒扫描，不能按搜索词补造标签。

## 9. 关系、整页门控与不确定性

`relations` 只允许记录 `same_card`、`same_field_across_cards`、`title_to_image`、`title_to_append`、`overlapping_annotation`、`same_supply_candidate`。每条含 `from`、`to`、`status`、`evidence` 和可选 `normalizedValue`。

完整结果卡中，主标题与可见图片、下挂实体的关系必须分别写为 `title_to_image`、`title_to_append`；无法确认则写 `uncertain` 并登记关联元素。不得写“图文不符”“重复供给”“颜色过多”等评测结论。

主 JSON 的 `recognition` 至少包含 `contractVersion`、`status`、`phase3Ready`、`wholePageGate`、`blockingCardIds`、`backends`、`errors`、`semanticHookFindings`、`reprocessTargets`、`reprocess`。

- 只有 `status=confirmed`、`phase3Ready=true`、`wholePageGate=true` 且 manifest validator 通过时，Phase3 才能消费。
- 任一卡、任一阻断 hook 或页面级事实失败时，`status=blocked`、`phase3Ready=false`；`blockingCardIds` 给出重跑范围，但不代表其他卡可以先发布。
- `reprocessTargets` 只记录原图上的有界裁剪重跑目标和原因，不写模型补读任务，不写纠错器生成的替代文本。
- 可选的独立 recognition audit 只保留调试字段来源，不改变主 JSON 的状态或事实。
