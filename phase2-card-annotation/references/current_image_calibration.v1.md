# 当前图片校准契约 v1

本契约把黄金 JSON 的校准方法迁移到每一张用户输入图片。黄金样本只提供结构范例；当前图片的文字、坐标、元素数量、顺序、样式和裁切状态必须全部重新取证。

## 校准链路

1. 读取当前完整截图一次，先确认页面模块、结果卡、卡内区域、每个可见下挂项和独立视觉实体。
2. 读取本次运行产生的本地 CV、卡型语义和门控产物。本地 CV 只提供页面、图片和几何候选；当前图 LLM 复核负责可见文字、卡型与拓扑事实。
3. 参考 `golden_structure_exemplars.v1.md` 选择最接近的结构，只复用区域、元素和所有权关系。
4. 对 OCR 分歧、碎片、标签边界、异构下挂和完整字形覆盖不足之处生成局部裁图，再用当前像素复核。整图固定读一次，局部复核最多十一张，总读图次数不超过十二次。
5. 逐一复核主 JSON 中全部非排除元素，同时检查当前截图中是否还有漏掉的可见模块、卡片、下挂项或原子元素。不能只处理门控已报告的 OCR 失败项。
6. 将修正同步写入唯一主 manifest，并同步维护 region、itemGroups、relations、factInventory 与 recognition 状态。主 JSON 之外的审计不是 Phase3 第二事实源。
7. 使用枚举文件、元素契约和当前图片校准审计共同校验。任何当前像素事实仍不能确认时，保持 `blocked`，不得发布为 Phase3-ready。

## 模型视觉能力的边界

模型可以依据当前整图或当前局部裁图确认：完整可见字面、独立视觉边界、元素类型、语义角色、卡片/区域/下挂归属和自然裁切状态。

模型不得：

- 从黄金 JSON、搜索词、常识或相邻卡片复制、补全当前图的文字、坐标、数量或顺序；
- 把语言上更通顺的猜测写成原文，或把 OCR 候选直接做语言纠错；
- 将图片内部包装字、招牌字或装饰字拆成独立 UI 元素；
- 因为结构和 schema 完整就把未逐像素确认的字段标为 `confirmed`；
- 在 Phase3 中回看截图并补写 Phase2 事实。

本地 CV 与模型视觉复核是互补证据。CV 不替代当前文字、卡型或图文归属判断；模型视觉复核也不能绕过卡型契约、枚举和确定性校验。

`search_card_taxonomy.v1.json` 中“不让视觉模型补读”的识别规则约束本地候选器：枚举/规则代码自身不得悄悄调用模型或把模型猜测伪装成 OCR 事实。它不取消候选阶段之后、由本契约明确记录证据的当前图片校准步骤。

## 复核审计

候选运行没有提供复核记录时，脚本会写出一个不可发布的模板：`reviewedAgainstCurrentPixels=false`，所有元素为 `uncertain`。不要修改这份模板来解锁。

完成当前图片复核后，先写入一个复核记录。它只记录新增/替换的像素观察；未变的候选不需要重复抄录：

```json
{
  "screenshot": "/absolute/path/to/current.png",
  "completeCurrentPixelReview": true,
  "localReviewPaths": [],
  "modules": [],
  "rejectedModules": [],
  "cards": [
    {
      "cardId": "C2",
      "coord": [0, 0, 0, 0],
      "cardTypeCandidate": "商家卡片_图文下挂",
      "topology": {
        "regions": [
          {"slot": "merchant_head", "coord": [0, 0, 0, 0], "visibleStatus": "confirmed"},
          {"slot": "merchant_info", "coord": [0, 0, 0, 0], "visibleStatus": "confirmed"},
          {"slot": "attached_goods", "coord": [0, 0, 0, 0], "visibleStatus": "confirmed"}
        ],
        "attachedItems": [
          {"itemIndex": 1, "coord": [0, 0, 0, 0], "visibleStatus": "confirmed"}
        ]
      },
      "fields": [
        {"coord": [0, 0, 0, 0], "text": "当前可见原文", "role": "title", "visibleStatus": "confirmed"}
      ]
    }
  ]
}
```

`completeCurrentPixelReview=true` 是对本截图整图一次、逐项核对全部活动元素的明确声明；不是“只复核了 `cards[]` 里修正项”。每张卡必须使用根目录 `card-type-registry.v1.json` 中的 `cardTypeCandidate`，并至少声明一个拓扑区域；完整可见的图文下挂商家卡必须声明 `merchant_head`、`merchant_info`、`attached_goods` 及每个可见 `attachedItems`。结果流尾卡被视口自然截断、下挂完全未露出时，只声明已看见的卡头/商家区域并由同组完整卡继承卡型，不得补造屏外 `attached_goods`、图片 ID、文字或 `attachedItems`；这类不可见缺口不阻断 Phase3。`attachedItems[].visibleStatus="naturally_cropped"` 只说明该子项被横向/纵向边缘截断，不降低完整可见商家卡的结构状态。`localReviewPaths` 仅列实际读取的局部裁图，必须唯一，最多 11 个。

显式 `modules[]` 是当前像素确认的完整页面模块库存；未列入的 CV 候选不进入清单，并作为非阻断提示留在归属审计中。对重要误报可用 `rejectedModules[]` 补充 `moduleType`、`coord` 和基于当前像素的 `reason`，但不要求逐个驳回 CV 噪声。未提供 `modules` 的旧复核继续走 CV 兼容路径，不能将其解释为“已确认页面没有模块”。文字/图文下挂的每个可见实体由 `attachedItems[].itemIndex` 指定唯一所有者；纵向换行、价格和门槛不改变同项归属。复核确认为 `异构卡` 时，还须提供 `heterogeneousEvidence.distinctStructure` 及非空 `whyKnownCardTypesFail[]`，说明正面结构证据，不能仅写“其他类型不匹配”。这些复核事实由 `semantic_ownership.py` 在冻结前交叉验收。

将记录作为 `--visual-review` 回灌 `run_phase2_recognition.py`。最终 manifest 和校准审计会在同一次命令中一起重建；不得在 manifest 或审计中手改通过状态。`<pythonBin>` 由调用方注入；可移植任务使用 `workflowArgs.pythonBin`：

```bash
<pythonBin> phase2-card-annotation/scripts/run_phase2_recognition.py \
  --query <query> --screenshot <screenshot> --output <elements.json> \
  --artifacts-dir <artifact-dir> \
  --recognition-audit <elements.recognition-audit.json> \
  --visual-review <current-screenshot-review.json>
```

最后运行：

```bash
<pythonBin> phase2-card-annotation/scripts/validate_element_manifest.py <elements.json> \
  --audit <elements.audit.json> \
  --recognition-audit <elements.recognition-audit.json> \
  --require-current-image-calibration
```

校验器要求每个非排除元素在审计中恰好出现一次，并交叉核对卡片、坐标、字段类型和可见原文。缺项、重复、审计与 manifest 不一致、黄金字段注入、未完成当前像素复核或超过读图上限都会阻断。
