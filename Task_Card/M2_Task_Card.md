# M2 任务卡 — 第一条 Vertical Slice：Glance → Provenance → Exact Source

> 对应：`Nightingale_72H_Development_Plan.md` Phase 2（§6）+ `AGENTS.md` M3。
> 截止目标：**Milestone 2 — 最迟 2026-08-26 晚**。
> 前置状态：M1 已完成（6 commits，16/16 pytest 绿，fixture 6 events / 12 artifacts 已验证）。
>
> **这是第一个必须可 demo 的 milestone。**

---

## 1. 目标

验证本项目最关键、最有辨识度的信任链：

```text
Glance Highlight
→ originating Event
→ AI Summary Artifact
→ source Transcript / Conversation Artifact
→ exact sentence / span
```

医生或 staff 打开患者页，**10 秒内**理解当前最重要的 3–5 条信息，每条都能解释"为什么重要"，并能一键跳回确切来源句子。

**本阶段不接真实 LLM**——继续用 deterministic stub。要证明的是系统能保存、解析、展示 AI 信息的来源，而不是摘要质量。

---

## 2. 范围

### In Scope

- `highlights` 表 + deterministic candidate 生成（stub）
- 透明 rule-based importance 排序（简化版）
- Glance API（读预计算结果）+ provenance 解析 API
- highlight 状态交互：accept / reject / pin（本阶段第一个写接口）
- 前端：Glance 面板替换 M1 占位 + source jump + span 高亮
- `test_highlight_provenance.py`（required test 之一）

### Out of Scope（明确不做）

- 真实 LLM extraction / summarization（Phase 4）
- comment / revision / RBAC 拦截（Phase 3）
- self-learning 权重更新（Phase 7；但 status 变化要**落库**，为以后留 feedback 数据）
- Glance 性能测量（Phase 6；但 API 必须按 warm-path 设计，不许在请求里现算）

---

## 3. 数据模型新增

### Highlight 表

```text
highlight_id
patient_id
event_id              -- 来源 Event
artifact_id           -- 直接来源（通常是 ai_summary artifact）
source_artifact_id    -- 原始来源（transcript / raw_conversation）
source_span           -- JSON pointer，沿用 M1 结构 {kind, index} 并可扩展 offset
text                  -- highlight 展示文本
risk_reason           -- 为什么重要（人话，一句话）
feature_flags         -- JSON：recency/explicit_risk/unresolved_task/
                         clinician_confirmed/symptom_change/repeated_mentions
importance_score      -- 由 feature_flags 加权算出，存库不现算
status                -- suggested | accepted | rejected | pinned
created_at, updated_at
```

### 硬约束

- 每条 highlight 的 `source_span` 必须能解析出**真实存在于 source artifact 中的原文片段**——span 定位用**确定性字符串匹配**（quote → offset），stub 也不例外；匹配不上就不许生成这条 highlight；
- `importance_score` 写入时预计算，Glance 读取零计算；
- status 变更必须写 `updated_at`，并保留旧值到日志/审计字段（M2 可简化为一列 `status_history` JSON，Phase 3 再并入 AuditLog）。

---

## 4. Deterministic Stub 设计

从 fixture 预写 candidate 清单，每条含 `quote`（原文句子）+ 语义标注。生成流程：

```text
fixture candidate（quote + feature_flags + risk_reason）
→ 在 source artifact 中确定性定位 quote（segment index / offset）
→ 定位成功才生成 highlight，写入 span
→ 按 feature_flags 加权计算 importance_score
→ 存库
```

建议 fixture 提供 5–7 条 candidate，覆盖：

| candidate | feature_flags | 预期排序 |
|---|---|---|
| headache weekly→near-daily | symptom_change + recency | 高 |
| nausea persists（08-24 follow-up） | symptom_change(unresolved) + recency | 高 |
| BP 158/96 elevated | explicit_risk | 高 |
| blood test pending | unresolved_task | 高 |
| follow-up scheduled | unresolved_task | 中 |
| existing medication since 2026-02 | （无加分项） | 低/可被截断 |

排序权重（写死在代码常量里，注释说明可解释）：

```text
score = 2*recency + 3*explicit_risk + 2*unresolved_task
      + 2*clinician_confirmed + 3*symptom_change + 1*repeated_mentions
```

Glance 默认展示 top 3–5 条 `status != rejected` 的 highlight。

---

## 5. API 契约

```text
GET /api/patients/{patient_id}/glance
    → { highlights: [...] }   -- 预计算、按 score 排序、过滤 rejected

GET /api/highlights/{highlight_id}/provenance
    → { event, summary_artifact, source_artifact,
        span: {kind, index, offset...}, quote }
    -- 每一跳都带 id / type / author_role / timestamp，前端直接渲染链路

POST /api/highlights/{highlight_id}/status
    body: { status: "accepted" | "rejected" | "pinned" }
    -- 校验状态机合法迁移；记录 status_history
```

---

## 6. 前端

### Glance 面板（替换占位）

每条 highlight 卡片：

```text
[风险色点] text
           risk_reason（灰色小字）
           [View source]  [✓]  [✗]  [📌]
```

- pinned 置顶，accepted 正常，rejected 从列表消失（可设 "show rejected" 开关，可选）；
- clinician-confirmed 的条目带确认徽标。

### Source jump

点击 `View source`：

1. Timeline 滚动定位到来源 Event 并展开；
2. 展示 provenance 链：Event → AI summary → source artifact；
3. source artifact 正文中**高亮 quote 所在 segment/句子**并滚动到可见位置。

这是整个 demo 的"wow moment"，必须流畅，不许只跳到 Event 级别就算完。

---

## 7. 任务分解（串行，每步一个 commit）

| # | 任务 | 难度 | 产出 |
|---|------|------|------|
| 1 | highlights 表 + fixture candidate + 确定性 span 定位 stub | **L3** | seed 后 highlight 落库且 span 可解析 |
| 2 | importance 加权 + Glance / provenance / status 三个 API | L2 | curl 可验证 |
| 3 | `test_highlight_provenance.py` + glance/status 测试 | L2 | 全绿 |
| 4 | Glance 面板 + accept/reject/pin 交互 | L2 | 面板可用 |
| 5 | source jump + span 高亮 | **L3** | wow moment 成立 |
| 6 | 顺手清理 README §15 顶部已过期的 "scaffold 尚未创建" 警告横幅 | L1 | 文档与实际一致 |

任务 1 的 span 定位与任务 5 的高亮跳转是本阶段仅有的两处 L3，其余都是常规工程。

---

## 8. 测试

### `test_highlight_provenance.py`（required）

- 每条 highlight 都有完整 provenance pointer（event → artifact → source artifact → span）；
- pointer 逐跳 resolve 成功，无悬空引用；
- span 解析出的 quote 是 source artifact 内容的真实子串；
- AI-scribed 来源的 highlight 同样满足以上全部。

### 附加

- Glance API：排序正确、rejected 不出现、score 与 feature_flags 可换算（可解释性断言）；
- status API：合法迁移成功、非法值 422、status_history 有记录。

---

## 9. 验收（Exit Gate，与计划 §6 一致）

1. Glance 3–5 条信息，10 秒内可以理解；
2. 每条有 `risk_reason`；
3. 每条 provenance 可解析；
4. 点击至少一条 AI-derived highlight 能跳到**确切 source span**（句子级高亮）；
5. `test_highlight_provenance.py` 通过，全部 pytest 绿。

达成后即拥有**最小可 demo 产品**（Scenario A 核心已可演示）。

---

## 10. 风险与注意

- **span 定位宁缺毋滥**：quote 匹配失败就丢候选，不许硬造 span——这是 Phase 4 不换架构的前提；
- score 权重是常量不是配置系统，别过度工程；
- `status_history` 是权宜字段，注释标明 Phase 3 并入 AuditLog，别让临时设计长成名誉性功能；
- Glance 读路径**不许**有任何实时计算/字符串匹配，全部读库；
- 完成后更新 AGENTS.md 实现状态（沿用 M1 commit `bd544b4` 的做法）。
