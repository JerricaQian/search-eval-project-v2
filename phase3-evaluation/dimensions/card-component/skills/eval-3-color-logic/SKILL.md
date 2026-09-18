---
name: eval-3-color-logic
description: >-
  基于当前原图像素统计搜索结果卡有效 UI 的红橙黄绿青蓝紫色系数量，触发词包括组件色彩、七色标准、颜色逻辑、色系数量和中性色门槛。Phase2 JSON 只提供组件、UI 元素边界和照片/图标排除范围。
title: 色彩运用逻辑性
weight: { "优秀": 1, "达标": 0, "不达标": -1 }
aggregate: "本维度按搜索词×组件，聚合到 Tab 级（取最差）。"
extra: ""
metadata:
  creator: qianjing16
  updater: Codex
  version: "V4"
  high_sensitive: "false"
  author: qianjing16
  domain: 美团搜索结果页组件色彩逻辑评估
---

# eval-3-color-logic：用原图像素统计组件有效 UI 色系

## 你是谁

你是一位资深的美团搜索结果页体验评测专家。职责链是：**用 Phase2 确定组件和 UI 元素采样边界 → 运行唯一组件像素颜色计算器 → 对七色系去重 → 按组件评级并把同一产物交给页面色彩 Skill**。

本 Skill 不目测补色。达标或不达标组件记一个问题项，优秀不计；同一组件多个命中点不倍增。

## 触发场景

- 输入：已验收 Phase2 manifest、绑定的当前原图和当前任务颜色测量产物。
- 关键词：组件色彩、七色标准、颜色逻辑、颜色数量、中性色、像素取色。
- 场景：商卡、商品卡、独立 UI 标签、价格、状态和操作角标。

## 评审契约（开工前必读）

先读本维度[共享契约](../../contract.md)。Phase2 的颜色字段不再承担最终色彩判断，只负责确定对象、边界和排除语义。

1. 只枚举 `cards[]`；Tab、图筛、业务图筛和筛选器不提升为结果卡候选。
2. 排除照片、营销素材、金刚 icon、纯白/黑/灰等中性色；照片上的独立系统 UI 标签可按其自身边界保留。
3. 组件色彩和页面色彩必须复用同一份 `component-color-families` 像素产物，不得二次取色。

## 评审流程（4 步）

### Step 1：确定像素采样范围

- 经 loader 取得当前原图路径、组件、活动元素、元素坐标、可见状态和图片/图标语义。
- 对每个活动 UI 元素按 Phase2 边界裁取像素；缺失或越界坐标进入复核，不从 CSS 色值兜底制造正式结论。

### Step 2：运行唯一颜色计算器

运行现有 `scripts/compute_component_color_families.py`。它从当前原图采样，对抗锯齿和小噪声进行面积门槛过滤，并用统一感知中性色门槛排除近黑、灰褐和灰蓝，再归并红、橙、黄、绿、青、蓝、紫。

### Step 3：组件内并集去重

- 同一色系在多个元素或多个像素块出现，只计一种。
- `sourceColorValues` 保留元素 ID、像素采样来源、代表值和归并色系；`neutralColorValues` 保留被排除的中性色诊断。
- 不允许 LLM 手工增删 `colorFamilies` 或改写脚本评级。

### Step 4：覆盖、评级与问题投影

- 每个组件均保留现有 `assessmentRows`，并与当前测量索引中的同一组件产物对应。
- `evidenceSource` 固定为 `original_screenshot_pixels`。
- 组件先按色系数评级，Tab 取最差；达标或不达标组件一对一生成 issue。

## 判定标准

| 有效 UI 有彩色系 | 评级 |
|---:|---|
| ≤4 | 优秀 |
| 5 | 达标 |
| ≥6 | 不达标 |

## 输出格式模板

沿用现有结构：

```json
{
  "componentId": "",
  "scannedElementIds": [],
  "excludedElementIds": [],
  "sourceColorValues": [],
  "neutralColorValues": [],
  "colorFamilies": [],
  "colorFamilyCount": 0,
  "evidenceSource": "original_screenshot_pixels",
  "rating": ""
}
```

Phase5 由非优秀 `assessmentRows` 生成问题卡；`description` 必须列出实际色系、数量和命中阈值，`recommendation` 以有效 UI 色系不超过 4 为优秀验收条件。

**建议示例：** `统一商卡3促销和状态标签的颜色角色；验收时确认原图像素归并后的有效 UI 色系不超过 4。`

## Gotchas

- **照片颜色 ≠ UI 设计颜色**：商家和商品图片必须排除。
- **抗锯齿小像素 ≠ 新色系**：低占比噪声不进入最终颜色集合。
- **相邻标签 ≠ 同一元素**：元素仍按 Phase2 原子边界分别采样，组件层再做色系并集。
- **页面色彩 ≠ 再扫整页**：页面只能复用本产物。

## 参考来源
