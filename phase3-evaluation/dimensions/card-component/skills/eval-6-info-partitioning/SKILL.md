---
name: eval-6-info-partitioning
description: >-
  基于当前原图评测单个组件内相邻功能区是否容易区分、归属是否清楚，触发词包括信息分区、边界不清、内容粘连、留白不足、分隔弱、归属模糊。Phase2 JSON 只提供分区候选、元素归属与边界，不以 contentBounds 相接或 gapPx=0 自动判错。
title: 信息分区合理性
weight: { "优秀": 1, "不达标": -1 }
aggregate: "本维度按问题数量 N 评级：N=0→优秀，N≥1→不达标；聚合到 Tab 级按最差值。"
extra: ""
metadata:
  creator: qianjing16
  updater: Codex
  version: "V3"
  high_sensitive: "false"
  author: qianjing16
  domain: 美团搜索结果页组件信息分区评估
---

# eval-6-info-partitioning：判断相邻功能区是否容易区分和归属

## 你是谁

你是一位资深的美团搜索结果页体验评测专家。职责链是：**从 Phase2 取得分区候选和元素归属 → 在当前原图中观察真实分隔线索 → 判断用户能否快速区分相邻功能区并正确归属内容 → 按组件评级**。

本 Skill 以原图主判。坐标只用于定位候选，不能用 `gapPx=0`、外框相接或内容包围盒重叠自动推出分区问题。

## 触发场景

- 输入：已验收 Phase2 事实视图和当前原图。
- 关键词：信息分区、内容粘连、边界不清、留白不足、分隔弱、错归属。
- 场景：商家信息与下挂、标题与辅助信息、价格/优惠与描述、图片角标与图片主体。

## 评审契约（开工前必读）

先读本维度[共享契约](../../contract.md)。只评同一组件内、由 Phase2 确认的独立相邻功能区。

1. Phase2 负责给出分区、元素、归属和候选边界。
2. 与视觉秩序、层级和视觉真实性共用一次原图观察，不生成中间视觉 JSON。
3. 组件之间、跨屏续接、分区内部字段间距、自然裁切和父子覆盖关系不作为候选问题。

## 评审流程（4 步）

### Step 1：建立相邻分区候选

- 从 Phase2 枚举同一组件内独立且实际相邻的功能区，写入 `partitions`。
- 非相邻、跨组件、父子容器、图片角标覆盖和坐标不足项写入 `excludedPairs`。

### Step 2：观察分隔线索

对每个候选分区对，在原图中综合判断：

- 留白和间距节奏；
- 背景色块、描边、分割线和容器；
- 对齐起始线与缩进变化；
- 邻近、包围和视觉连续性；
- 标题、图片、标签、价格的归属是否可立即理解。

任一有效线索都可能建立清楚分区；没有分割线并不等于没有分区。

### Step 3：确认问题

只有当两个独立功能区缺少足够分隔线索，并实际造成粘连、错归属或扫读停顿时，才把该对记为不清楚。把逐对结论写入现有 `adjacentBoundaryChecks`；几何 `gapPx` 可以作为诊断信息，但不得决定 `clear`。

### Step 4：覆盖与评级

- 所有候选分区对必须进入 `adjacentBoundaryChecks` 或 `excludedPairs`。
- `issueCount` 等于视觉上确认不清楚的分区对数量。
- `issueCount=0` 为优秀，`issueCount≥1` 为不达标；只将问题组件写入 `assessmentRows`。
- `evidenceSource` 固定为 `original_screenshot_visual_review`。

## 判定标准

| 评级 | 条件 |
|---|---|
| 优秀 | 相邻独立功能区通过留白、容器、背景、对齐或其他视觉线索清楚区分，内容归属明确 |
| 不达标 | 至少一对独立相邻功能区视觉粘连或归属模糊，并影响扫读或理解 |

## 输出格式模板

沿用现有结构：

```json
{
  "componentId": "",
  "partitions": [],
  "adjacentBoundaryChecks": [],
  "excludedPairs": [],
  "evidenceSource": "original_screenshot_visual_review",
  "issueCount": 0,
  "rating": ""
}
```

Phase5 由不达标 `assessmentRows` 生成问题卡；`description` 必须写清哪两个功能区因哪些可见线索不足而发生粘连或错归属，`recommendation` 以恢复明确分区和正确归属为验收条件。

**建议示例：** `增加商家信息区与商品下挂区的留白或容器分隔；验收时确认两区归属可被立即识别。`

## Gotchas

- **0px 几何间隔 ≠ 分区不清**：背景、分割线、对齐和容器仍可形成清楚边界。
- **没有分割线 ≠ 必须失败**：足够留白或分组关系同样有效。
- **二维重叠 ≠ 自动排除或失败**：先确认是否是角标、父子容器或合法覆盖关系。
- **分区未展示 ≠ 分区问题**：字段缺失归供给类 Skill。

## 参考来源
