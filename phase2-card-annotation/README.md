# Phase2 轻量截图识别

本目录负责把搜索结果页截图转换成 Phase3 可消费的结构化事实。生产路径采用“本地 CV 候选 + 黄金结构范例 + 当前图片像素复核 + 卡型/枚举/元素契约门控”；模型只复核当前图片，不复制黄金字段，也不生成整页标注图。

`phase2.atomic-manifest.v3` 每次写出前必须使用 `references/search_card_taxonomy.v1.json` 校验枚举与契约版本；文件 SHA-256 仅作为可选溯源记录，不参与发布阻断。所有标签元素统一使用 `kind: "tag"`，槽位名统一以 `_tag` 结尾，例如 `product_attribute_tag` 与 `scenic_rating_tag`。

生产 Phase2 与离线黄金校准共享元素契约：完整已知卡必须有主标题；每个下挂项分别拥有自己的图片/文字/价格；基础信息和标签按语义原子拆分。生产流只用本地 CV 几何/图片候选及当前图片视觉复核确认文字和归属，不运行本地 OCR；黄金只提供结构。标题明确时仍需本卡拓扑兼容；标题不明确时使用卡内内容与最小证据契约，任一路径的元素/归属门禁不满足均阻断。

详细执行纪律见 `SKILL.md`；卡型边界与最小证据以 `references/card_recognition_contracts.v1.json` 为准。

## 输入与输出

输入是一张 PNG/JPG 截图。每张截图独立生成一个主 JSON：

```text
截图 A ──▶ elements_A.json
截图 B ──▶ elements_B.json
截图 C ──▶ elements_C.json
```

禁止把多张截图的页面、卡片或元素合并进一个识别 JSON。批量回归的 `index.json` 只记录每张图自己的 `canonicalManifest` 和统计指标，永远不是 Phase3 事实源。

主 JSON 固定包含 `query`、`screenshot`、`cards[]`、`recognition`、`pageFacts`、`pageFactInventory` 和 `relations`。门控失败仍写主 JSON，但必须设置 `recognition.phase3Ready=false`，Phase3 不得消费；旧清单的 `annotatedImage` 仅兼容读取。

## 生产入口

`<pythonBin>` 由调用方注入；可移植任务使用 `workflowArgs.pythonBin`，不得假定项目 `.venv` 或 `python3` 别名。

先生成不可发布的本地候选，再读取当前整图并写复核记录；生产任务的完整命令和暂存路径以 `workflow/contracts/phase234-query-pipeline.md` 为准：

```bash
<pythonBin> phase2-card-annotation/scripts/run_phase2_recognition.py \
  --stage candidate --query <query> --screenshot <absolute-screenshot-path> \
  --output <candidate-bundle.json> --artifacts-dir <attempt-artifacts-dir>
```

```bash
<pythonBin> phase2-card-annotation/scripts/run_phase2_recognition.py \
  --stage publish --query <query> --screenshot <absolute-screenshot-path> \
  --candidate-bundle <candidate-bundle.json> --visual-review <visual-review.json> \
  --output <attempt-manifest.json> --recognition-audit <recognition-audit.json> \
  --artifacts-dir <attempt-artifacts-dir>
```

生产发布按三关验收：**证据绑定**（候选与复核属于当前截图）、**事实一致**（卡型/元素清单、当前图审计与跨层归属）、**一次性发布**（有效审计及版本/哈希绑定）。内部脚本和检查项仍保留，但 CV 候选只是提示：显式 `modules[]` 是完整当前图页面模块库存，未选中的 CV 模块不发布，只记审计提示；页面模块与结果卡重复、下挂项错归属等真实冲突仍阻断。只有三关通过才提升到不可覆盖的正式路径；失败时依据 retry plan 在新暂存尝试中修正。

## 当前执行链

1. 本地 CV 生成页面、卡片和图片候选，不生成可发布的文字事实。
2. 当前图复核确认主标题、卡型家族、卡片拓扑、页面模块、下挂项及独立原子；显式 `modules[]` 即页面模块完整库存，`rejectedModules[]` 可补充记录误报原因，不再要求逐项驳回每个未选中的 CV 候选。
3. `map_result_card_semantics.py` 先采用可信标题语义，必要时再结合卡内内容；商家子型由下挂拓扑决定，异构卡需正面结构证据。
4. `build_phase2_manifest.py` 组装每张截图自己的事实清单，复核的 `itemIndex` 优先于行距，结果位置按可见顺序编号。
5. `validate_element_manifest.py` 与 `semantic_ownership.py` 分别验收结构/当前像素审计和跨层归属；失败保留暂存证据并生成定向 retry plan。
6. `promote_phase2_attempt.py` 核对截图、复核与暂存清单哈希及三份有效审计后一次性发布；历史正式清单不可覆盖。

## 卡型与页尾规则

卡型决策顺序固定为：本卡可信主标题语义明确、且卡片拓扑/页面位置兼容的已知卡型 → 结合卡内内容与边界、满足最小契约的已知卡型 → 有明确广告证据的广告卡 → 稳定独立的异构候选。异构正式发布还需 `heterogeneousEvidence` 说明区别于已知卡型的可见结构及已知卡型不成立的原因；不能把证据不足的酒店或商家卡自动归入异构卡。标题含“酒店”等字样但语义指向商品（如酒店用品），或标题含商品词但商家下挂拓扑明确时，不得仅凭词面覆盖结构。无法确定标题语义时进入第二步；正式输出不发布 `unknown`。

结果流最后一张重复卡自然触底时，可在无广告证据的前提下继承上一张已确认已知卡型。只豁免因截断不可见的必需字段；已显示文字的乱码、OCR 分歧和字段文法错误仍阻断整页。

不同卡型的边界策略不得混用：商品卡按单商品主图/标题/价格重复切分；商家图文下挂吸附商品图组；商家文字下挂吸附服务文字块；酒店单列按逐卡头图/标题锚切分、双列按独立网格单元逐格切分，头图高度逐卡测量；演出/电影、套餐和主点卡分别使用自己的拓扑契约。酒店细则见 `references/hotel_card_algorithm.v1.md`。

### 已知失败模式与回归口径（2026-08-20）

“隆江猪脚饭”样本验证了以下必须同时满足的发布条件：顶部状态/调试层不参与 OCR；图片内来源不生成正文列退化裁剪；重复商家头图之间的摘要和横滑商品区是一张 `商家卡片_图文下挂`，不能退回异构卡；确认该卡型后商品图归“下挂商品区”而非“特殊下挂”；横滑商品必须逐项拥有图片/文字/价格所有权，没有确认价格的项为 `uncertain`；底部卡仅对屏幕外部分标 `naturally_cropped`。主会话局部复核的字段必须进入 recognition audit，并且 OCR 门控、manifest schema、itemGroups 所有权与枚举校验全通过后才可进入 Phase3。

搜索词不是页面模板主键。同一搜索词的多次截图分别生成 JSON，允许结果模块和卡片不同；同页混排时逐卡判型，不能用页面多数卡型覆盖单卡。双列酒店页尾截断格只从同列上一张已确认酒店卡继承。

## Phase3 事实

每个最小元素携带坐标、归属、原文、`render`，文字携带 `textFacts`，标签/icon 携带 `visual`。Phase2 记录颜色、颜色角色、字重/字号桶、渲染状态、关系和标签扫描库存；不输出评级。

当前阶段不做通用圆角容器检测。无法由像素确认的 `containerShape` 写 `unknown`。图片在 Phase2 只记录准确坐标与 `render.isPhoto=true`；组件与页面色彩在 Phase3 直接排除图片，只复用非图片 UI 元素的已确认颜色角色。

## 回归与经验沉淀

黄金样本只用于推理后的回归和清洗后的归一化几何学习，不能向当前截图注入人工卡型、坐标或字段值。酒店样本位于 `golden-samples/hotel-card/`；相同 query 的不同 `searchInstance` 不得合并：

```bash
<pythonBin> phase2-card-annotation/scripts/learn_card_geometry_profiles.py \
  --output phase2-card-annotation/references/learned_card_geometry_profiles.v1.json

<pythonBin> phase2-card-annotation/scripts/rerun_golden_cv.py \
  --output-dir .artifacts/golden-cv-rerun
```

仓库以 `golden-atomic-2.1/` 下 34 份页面可重建黄金 JSON 和汇总 `index.json` 为当前版本；`golden-atomic-2.0/` 保持不动，仅用于回滚与审计。这 34 份 atomic v3 同时也是后续重建的原始输入。`scripts/build_atomic_manifest_v3_goldens.py` 默认重新校验并规范化写出 2.1、重建索引，不依赖旧格式。旧 `golden-sample-results/**/*.elements.json` 已外部归档；只有一次性追溯迁移时才显式传入 `--legacy-source-root`。逐 manifest audit sidecar 已删除，审计摘要集中保存在索引中。

## 历史兼容文件

`scenes/`、旧 `annotation_scene.py` 和 `annotate_image.py` 仅保留历史标注复现能力，不属于 Phase2 生产识别流程，不得作为新截图的坐标、卡型或元素事实来源。
