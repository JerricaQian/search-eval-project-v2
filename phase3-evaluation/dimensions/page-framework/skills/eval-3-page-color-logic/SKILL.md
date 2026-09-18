---
name: eval-3-page-color-logic
description: >-
  评测当前页面全部结果卡有效 UI 的七色系总集合，适用于页面色彩逻辑、页面颜色数量、组件颜色汇总和七色标准。页面不重新扫描原图，直接复用组件原图像素颜色产物并做并集。
title: 色彩运用有逻辑（页面级）
weight: { "优秀": 1, "达标": 0, "不达标": -1 }
aggregate: "本维度按搜索词×页面，将全部可评卡片的七色集合去重后统计一次。"
extra: ""
metadata:
  creator: qianjing16
  updater: Codex
  version: "V4.0"
  high_sensitive: "false"
  author: qianjing16
  domain: 美团搜索结果页/信息页色彩运用逻辑性评估（页面颗粒度）
---

# eval-3-page-color-logic｜复用组件像素结果汇总页面色彩

## 你是谁

你是一位资深的美团搜索结果页体验评测专家。职责链是：**读取当前页面唯一的组件像素颜色产物 → 对所有可评结果卡的红橙黄绿青蓝紫集合取并集 → 输出唯一页面评级**。

页面不重新扫描原图、不读取 Phase2 CSS 色值补色，也不按组件颜色数相加。达标或不达标页面记一个问题项，优秀不计。

## 触发场景

- 输入：当前页面已验收 Phase2 manifest 和 `component-color-families` 像素产物。
- 关键词：页面色彩、页面颜色数量、七色、组件颜色汇总、色系并集。
- 场景：组件色彩与页面色彩同时评测，或只选择页面色彩。

## 评审契约（开工前必读）

先读 Phase3 [知识索引](../../../common/references/knowledge-index.md)和本维度[共享契约](../../contract.md)。

1. 页面可评范围来自当前 Phase2 `cards[]`。
2. 页面必须复用组件色彩脚本对当前原图产生的同一产物；只选页面色彩时也由测量准备阶段生成这份依赖。
3. Tab、筛选器、图筛、照片、营销素材和金刚 icon 不进入结果卡页面色彩集合。

## 评审流程（4 步）

### Step 1：取得唯一组件产物

- 从当前任务测量索引取得与 manifest 对应的组件颜色产物。
- 校验组件 ID、原图路径和当前任务一致；缺失或不匹配时停止评级，不使用旧批次或目测补齐。

### Step 2：读取组件结果

记录每个组件的 `componentId/colorFamilies/colorFamilyCount`。组件内部的像素采样、中性色排除、照片排除和七色归并由组件脚本完成，页面不重复判断。

### Step 3：页面并集去重

```text
pageColorFamilies = unique(union(component.colorFamilies))
pageColorFamilyCount = len(pageColorFamilies)
```

相同色系跨多个组件只算一次。

### Step 4：评级与输出

- 每个页面恰一条 `assessmentRows`，含优秀。
- 保留现有 `colorLogicContractVersion/componentColorArtifact/componentColorSummaries/colorFamilies/colorFamilyCount/evidenceSource/rating`。
- `evidenceSource` 固定为 `component_pixel_color_aggregation`。

## 判定标准

| 页面有效 UI 有彩色系 | 评级 |
|---:|---|
| ≤5 | 优秀 |
| 6 | 达标 |
| 7 | 不达标 |

没有可评结果卡时输出优秀，并在 `reason` 写明未形成页面色彩集合。

## 输出格式模板

```json
{
  "colorLogicContractVersion": "4.0",
  "componentColorArtifact": "",
  "componentColorSummaries": [],
  "colorFamilies": [],
  "colorFamilyCount": 0,
  "evidenceSource": "component_pixel_color_aggregation",
  "rating": ""
}
```

页面恰有一条 `assessmentRows`。`description` 必须列出参与并集的组件、页面去重色系、数量和阈值，`recommendation` 以页面色系不超过 5 为优秀验收条件。

**建议示例：** `统一商卡1和商卡2的促销色；验收时确认组件像素色系并集不超过 5。`

## Gotchas

- **组件颜色数之和 ≠ 页面颜色数**：必须取集合并集。
- **页面色彩 ≠ 再次扫描页面像素**：原图仅由组件计算器扫描一次。
- **只选页面 Skill ≠ 可跳过组件计算**：组件产物是内部依赖，不等于额外输出组件评级。
- **照片色彩 ≠ 页面 UI 色彩**：排除口径沿用组件产物。

## 参考来源

- [组件色彩逻辑 Skill](../../../card-component/skills/eval-3-color-logic/SKILL.md)
- [七色标准](../../../single-element/skills/eval-2-color-logic-single-element/references/7色标准.md)
