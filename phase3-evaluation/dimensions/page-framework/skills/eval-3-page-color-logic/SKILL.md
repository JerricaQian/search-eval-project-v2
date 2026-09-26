---
name: eval-3-page-color-logic
description: >-
  仅复用当前 Phase2 JSON 已确认的 UI 颜色角色，评测当前页面全部结果卡红橙黄绿青蓝紫色系及已确认渐变贡献的总数；适用于页面色彩逻辑、页面颜色数量、渐变、组件颜色汇总和七色标准。不读取原图像素，不运行取色脚本。
title: 色彩运用有逻辑（页面级）
weight: { "优秀": 1, "达标": 0, "不达标": -1 }
aggregate: "本维度按搜索词×页面，将全部可评卡片的七色集合去重后统计一次。"
extra: ""
metadata:
  creator: qianjing16
  updater: Codex
  version: "V5.1"
  high_sensitive: "false"
  author: qianjing16
  domain: 美团搜索结果页/信息页色彩运用逻辑性评估（页面颗粒度）
---

# eval-3-page-color-logic｜用 Phase2 JSON 汇总页面色彩

## 你是谁

你是一位资深的美团搜索结果页体验评测专家。职责链是：**从当前 Phase2 JSON 为每个可评结果卡建立 UI 色系集合 → 对红橙黄绿青蓝紫取页面并集 → 输出唯一页面评级**。

页面不扫描原图、不运行组件或页面取色脚本，也不按组件颜色数相加。达标或不达标页面记一个问题项，优秀不计。

## 触发场景

- 输入：当前页面已验收 Phase2 manifest；需要格式归一化时可使用只读 loader。
- 关键词：页面色彩、页面颜色数量、七色、组件颜色汇总、色系并集。
- 场景：组件色彩与页面色彩同时评测，或只选择页面色彩。

## 评审契约（开工前必读）

1. 页面可评范围来自当前 Phase2 `cards[]`。
2. 页面和组件色彩使用同一套 JSON-only 颜色规则：优先读取已确认 UI 元素的 `visual.colorRole`；该字段缺失或为 `unknown` 时，文本/标签元素可回退到明确的 `textFacts.textColorRole`；两字段均明确时必须一致。
3. Tab、筛选器、图筛、照片、营销素材、图片和 icon 不进入结果卡页面色彩集合；`neutral` 不计入有彩色系。
4. 可计数颜色只允许 `red/orange/yellow/green/cyan/blue/purple`。
5. `multicolor` 有已确认渐变类型时可评：同色系渐变计1种，不同色系渐变计2种。类型必须来自 Phase2 补充复核或用户明确校正；类型缺失时保留 `reviewItems` 并停止正式评级。
6. 任一可评组件在 JSON 两个颜色字段中都没有明确角色，或存在明确字段冲突、非颜色旧枚举时，页面保留 `reviewItems` 并停止正式评级；禁止回退像素脚本或目测补色。

## 评审流程（4 步）

### Step 1：建立页面组件清单

- 从当前 Phase2 JSON 取得全部可评结果卡。
- 组件色彩 Skill 同时运行时，可复用其 JSON 派生的 `componentColorSummaries`；只选页面色彩时，按相同规则直接从 Phase2 JSON 生成摘要，不输出额外组件评级。

### Step 2：核验组件颜色摘要

每个摘要至少记录 `componentId/colorFamilies/gradientColorValues/colorFamilyCount/scannedElementIds/excludedElementIds/reviewItems`。单色字段必须来自 Phase2 JSON，渐变类型可来自 Phase2 补充复核或用户明确校正，不能来自历史像素产物。

### Step 3：页面并集去重

```text
pageColorFamilies = unique(union(component.colorFamilies))
pageGradientContributionCount = sum(confirmed unnamed gradient contributions)
pageColorFamilyCount = len(pageColorFamilies) + pageGradientContributionCount
```

相同的已命名色系跨多个组件只算一次；渐变已给出具体端点色系时也并入去重集合，只有贡献数时直接加入总数且不猜测色系名。只要任一组件仍有未决 `reviewItems`，不得先行给出正式页面评级。

### Step 4：评级与输出

- 每个页面恰一条 `assessmentRows`，含优秀。
- 保留 `colorLogicContractVersion/componentColorSummaries/reviewItems/colorFamilies/colorFamilyCount/evidenceSource/rating`。
- `evidenceSource` 固定为 `phase2_json_component_color_aggregation`。

## 判定标准

| 页面有效 UI 有彩色系 | 评级 |
|---:|---|
| ≤5 | 优秀 |
| ≥6 | 不达标 |

没有可评结果卡时输出优秀，并在 `reason` 写明未形成页面色彩集合。

## 输出格式模板

```json
{
  "colorLogicContractVersion": "5.1",
  "componentColorSummaries": [],
  "reviewItems": [],
  "colorFamilies": [],
  "gradientColorValues": [],
  "gradientContributionCount": 0,
  "colorFamilyCount": 0,
  "evidenceSource": "phase2_json_component_color_aggregation",
  "rating": ""
}
```

页面恰有一条 `assessmentRows`。`description` 必须列出参与并集的组件、页面去重色系、数量和阈值，`recommendation` 以页面色系不超过 5 为优秀验收条件。

**建议示例：** `统一商卡1和商卡2的促销色；验收时确认 Phase2 JSON 中全部结果卡的有效 UI 色系并集不超过 5。`

## Gotchas

- **组件颜色数之和 ≠ 页面颜色数**：必须取集合并集。
- **页面色彩 ≠ 扫描页面像素**：页面和组件均只读取 Phase2 JSON。
- **只选页面 Skill ≠ 运行组件取色脚本**：组件摘要是页面 Skill 从同一 JSON 派生的内部证据。
- **unknown/multicolor ≠ 无颜色**：`unknown` 只有在缺少明确文本颜色回退时才阻断；`multicolor` 有已确认渐变类型时按1种或2种计数，类型缺失才阻断。
- **照片色彩 ≠ 页面 UI 色彩**：照片、图片和营销素材始终排除。
