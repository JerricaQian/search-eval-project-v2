---
name: eval-3-color-logic
description: >-
  仅复用当前 Phase2 JSON 已确认的 UI 颜色角色，统计搜索结果卡有效 UI 的红橙黄绿青蓝紫色系数量，并处理同色系或跨色系渐变；适用于组件色彩、七色标准、颜色逻辑、渐变和色系数量评测。不读取原图像素，不运行取色脚本。
title: 色彩运用逻辑性
weight: { "优秀": 1, "达标": 0, "不达标": -1 }
aggregate: "本维度按搜索词×组件，聚合到 Tab 级（取最差）。"
extra: ""
metadata:
  creator: qianjing16
  updater: Codex
  version: "V5.1"
  high_sensitive: "false"
  author: qianjing16
  domain: 美团搜索结果页组件色彩逻辑评估
---

# eval-3-color-logic：用 Phase2 JSON 统计组件有效 UI 色系

## 你是谁

你是一位资深的美团搜索结果页体验评测专家。职责链是：**读取 Phase2 JSON 中每个组件的已确认 UI 元素 → 排除照片、图片、图标和中性色 → 对已确认颜色角色按七色系去重 → 按组件评级**。

本 Skill 不读原图、不裁剪像素、不运行颜色脚本，也不目测补色。达标或不达标组件记一个问题项，优秀不计；同一组件多个命中点不倍增。

## 触发场景

- 输入：已验收 Phase2 manifest；需要格式归一化时可使用只读 loader。
- 关键词：组件色彩、七色标准、颜色逻辑、颜色数量、中性色。
- 场景：商卡、商品卡、独立 UI 标签、价格、状态和操作角标。

## 评审契约（开工前必读）

Phase2 JSON 是本 Skill 唯一颜色事实源。

1. 只枚举 `cards[]`；Tab、图筛、业务图筛和筛选器不提升为结果卡候选。
2. 只评 `isExcluded != true`、`render.visibleStatus=confirmed`、`visual.visualStatus=confirmed` 的活动 UI 元素。
3. 排除 `render.isPhoto=true`、`visual.entityKind=image/icon`、元素类型为图片/图标的实体，以及纯白、黑、灰等 `neutral` 中性色；照片上的独立系统 UI 标签仍按其自己的 JSON 元素和颜色角色评测。
4. 颜色优先读取 `visual.colorRole`；文本/标签元素若该字段为缺失或 `unknown`，但 `textFacts.textColorRole` 是明确颜色角色，则直接复用后者。两字段均为明确颜色角色时必须一致。
5. 可计数的单色只允许 `red/orange/yellow/green/cyan/blue/purple`，输出为红、橙、黄、绿、青、蓝、紫。
6. `multicolor` 不再必然阻断：已确认为同色系渐变时计1种，已确认为不同色系渐变时计2种。渐变类型必须来自 Phase2 补充复核或用户明确校正；只有 `multicolor` 而没有渐变类型时仍进入 `reviewItems`，禁止猜测。
7. 两个颜色字段均缺失/`unknown`、明确颜色字段互相冲突，或只有 `primary/secondary/emphasis/accent` 等非颜色旧枚举时，记录 `reviewItems` 并停止该组件正式评级；禁止回退原图、像素脚本或语义猜色。

## 评审流程（4 步）

### Step 1：建立组件与元素清单

- 从当前 Phase2 JSON 取得 `cards[]`、区域和全部原子元素。
- 每个组件的元素必须分入 `scannedElementIds`、`excludedElementIds` 或 `reviewItems`，三类互斥且覆盖该组件全部元素。

### Step 2：读取并核验 JSON 颜色角色

- 对每个可评元素优先读取 `visual.colorRole`；值为缺失或 `unknown` 时，可回退到已确认的 `textFacts.textColorRole`。
- 两字段均为七色或 `neutral` 时执行交叉核验；明确值不一致即进入复核。`unknown` 与另一个明确值并存不视为冲突。
- 对 `multicolor` 只读取已确认的渐变类型：`same-family` 记 `gradientContributionCount=1`，`cross-family` 记 `gradientContributionCount=2`。若具体端点色系未给出，只保留贡献数，不伪造红橙黄绿青蓝紫名称。
- 不读取 `backgroundColor`、`textColor` 或 `borderColor` 的像素/CSS 字符串重新推导颜色家族，不从 `styleKey` 猜色。

### Step 3：组件内并集去重

- 同一色系在多个元素出现，只计一种。
- `sourceColorValues` 保留元素 ID、实际 JSON 字段、原始颜色角色和归并后的中文色系。
- `gradientColorValues` 保留 `elementId/value/gradientFamilyMode/gradientContributionCount/confirmationSource`；渐变贡献数加入 `colorFamilyCount`。已给出具体端点色系时先与单色集合去重，未给出时按已确认贡献数计数。
- `neutralColorValues` 保留被排除的中性色角色；照片、图片和图标只进入排除清单，不进入颜色集合。

### Step 4：覆盖、评级与问题投影

- 每个组件均保留现有 `assessmentRows`，优秀也不得省略。
- `evidenceSource` 固定为 `phase2_json_color_inventory`。
- 仅当 `reviewItems` 为空时才能按色系数评级；只要未决项可能改变组件或 Tab 结论，就停止正式评级并请求 Phase2 复核。
- 组件先按色系数评级，Tab 取最差；达标或不达标组件一对一生成 issue。

## 判定标准

| 有效 UI 有彩色系 | 评级 |
|---:|---|
| ≤4 | 优秀 |
| 5 | 达标 |
| ≥6 | 不达标 |

## 输出格式模板

沿用现有结构，并增加未决复核清单：

```json
{
  "componentId": "",
  "scannedElementIds": [],
  "excludedElementIds": [],
  "reviewItems": [],
  "sourceColorValues": [],
  "gradientColorValues": [],
  "neutralColorValues": [],
  "colorFamilies": [],
  "colorFamilyCount": 0,
  "evidenceSource": "phase2_json_color_inventory",
  "rating": ""
}
```

Phase5 由非优秀 `assessmentRows` 生成问题卡；`description` 必须列出实际色系、数量和命中阈值，`recommendation` 以有效 UI 色系不超过 4 为优秀验收条件。

**建议示例：** `统一商卡3促销和状态标签的颜色角色；验收时确认 Phase2 JSON 中已确认的有效 UI 色系不超过 4。`

## Gotchas

- **照片颜色 ≠ UI 设计颜色**：照片、商品图片和营销素材无论多彩都不计。
- **元素框内背景颜色 ≠ JSON 颜色角色**：本 Skill 不再裁剪元素框读取像素。
- **unknown/multicolor ≠ 0 种颜色**：`unknown` 仅在没有明确 `textFacts.textColorRole` 回退时阻断；`multicolor` 有已确认渐变类型时按1种或2种计数，类型缺失才阻断。
- **强调等级 ≠ 颜色角色**：`primary/secondary/emphasis/accent` 不得映射成颜色。
- **页面色彩 ≠ 颜色数相加**：页面 Skill 对组件色系集合做并集。
