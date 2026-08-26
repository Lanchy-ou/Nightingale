# M5 任务卡 — Longitudinal Demo Data + Optional Synthea Enrichment

> 对应：`Nightingale_72H_Development_Plan.md` Phase 5（§9）+ `AGENTS.md` §13 Demo Data Requirement。
> 截止目标：**Milestone 5 — 2026-08-28 凌晨/上午完成 longitudinal demo data**（最终提交截止 2026-08-28 17:30 SGT/MYT；本卡目标工期 ≤ 0.5 天）。
> 前置状态：M1–M4 已完成（103/103 pytest 绿，AI vertical slice、redaction、deterministic scoring、ingestion RBAC、bounded conflict 已落地）。
>
> **阶段边界说明**：本任务卡只做 demo 数据纵深。M5 完成只可声明 **Longitudinal Demo Data Complete**；Patient View 页面、性能测量（Phase 6）、Scenario A/B/C 正式 walkthrough、Technical Brief、demo video 均不在本卡内，Core Complete 不可提前声明。

---

## 0. 开工前 Gate

1. **M4 基线已落库**：live DeepSeek adapter、Gate 0 `LIVE_VERIFIED (2026-08-26)` 证据与 anthropic dependency 已由 commit `45c572a` 提交；不得在 M5 重做、重写或重新提交这部分。
2. 开工时重新执行全量 pytest 与 frontend build，记录 baseline；若回归则先停止并修复 M4，不得带病进入 M5。
3. M5 的自动化测试继续只走 mock/deterministic 路径，不读取真实 key、不产生外部请求；live adapter 只用于 owner 明确触发的手动无 PHI/demo 验证。
4. 当前工作区中的 M5 任务卡改动属于本卡文档；实现时不得把其他无关改动混入 M5 commit。
5. **pat_002 / clinic_002 仅作 RBAC 隔离用途**，本卡不得给它堆叙事数据。

---

## 1. 目标与成功定义

把当前“能工作的小样例”扩展成一条有说服力的 longitudinal patient journey，使 Scenario C 能清楚回答：

> 这个患者过去发生过什么？现在什么变了？哪些事情仍未完成？为什么 Glance 现在优先显示这些信息？

成功必须同时满足：

- 时间层级清晰：`2025-04-15` 历史事件 → `2026-02-06` 历史事件 → `2026-08` 当前 care episode（5 个 Event），`started_at`（真实发生时间）与 `created_at`（记录时间）两轴不混；
- 当前 episode 补齐 `AGENTS.md` §13 的 **Event 5 — clinician review**：updated plan 落库后，Timeline 能看到新 Event，Glance 能看到由该 Event 支撑的新 current-priority Highlight；
- 历史事件不再是单薄占位：2025-04-15 初次头痛评估与 2026-02-06 药物复查要有可信的 clinician note 内容，且与当前 episode 的叙事（头痛、propranolol）形成真实的跨月/跨年呼应；
- `recency` 与 `repeated_mentions` 不再由 fixture 手填猜测：seed generator 使用冻结的显式 `as_of` 计算 recency，并按相同 `entity_key` 的不同 Event 分组，使新旧两侧 Highlight 都重算；
- `repeated_mentions` 在跨 Event 场景下真实触发（`symptom:headache frequency`、`task:blood test`），且新旧两侧 Highlight 分数都被重算（遵守 M4 §12 合同）；
- 所有新 narrative 与 fixture `FACTS` 严格一致，`tests/test_seed_integrity.py` 同步扩展；
- 每条新 Highlight 仍走 verbatim quote → `locate_span` 确定性锚定，匹配失败丢弃，绝不伪造 span；
- 103 个既有测试零回归。

---

## 2. 范围

### In Scope

- fixture 新增 **Event 5：`clinician_review`**（建议 `2026-08-26` 上午，与 demo 当天对齐）及其 Artifact：
  - `clinician_note`（updated plan，`author_role=clinician`）；
  - `patient_instruction` 更新版（只准备后续 Patient View 所需的患者可见内容，本卡不做页面）；
- 丰富两个历史 Event 的 clinician note 内容（见 §5），必要时各补一条 anchor 到 note 本身的 Highlight；
- 新增跨 Event 实体呼应所需的 Highlight candidates，并在 `backend/seed/highlights.py` 补齐 deterministic structural-flag 计算；M4 runtime 的两侧重算在 `backend/app/ai_pipeline.py`，不得误认为 `app/highlights.py` 已替 seed 完成该工作；
- `FACTS` 扩展 + `test_seed_integrity.py` 新断言；
- demo DB（`backend/nantingale.db`）重新 seed 并人工走查 Scenario C；
- README demo data 段落回填（新时间线概览 + 如何 reseed）；
- **Synthea 决策门**（见 §7）：默认不做；只有在本卡其余项全部完成且有明确余量时才评估。

### Out of Scope（不得顺手实现）

- Patient View 页面 / patient-facing summary 设计（硬缺口，须单独排期，见 §9）；
- Task 表 / assignment / task completion workflow；M5 没有 Task/status model，所有 seed/runtime Highlight 的 `unresolved_task` 继续固定为 `false`，不得从“pending”文字猜成 true；
- performance 测量与 Glance 优化（Phase 6 / M6）；
- self-learning / adaptive weights（Phase 7，严格后置）；
- Voice capture、data decay；
- 新增第二个有叙事的 patient、新增 clinic；
- FHIR 全量映射、Synthea 实际接入重构内部模型（决策门未过则禁止动工）；
- 任何 scoring 权重调整（M2 冻结权重不得在本卡改动）；
- demo video、Technical Brief（Milestone 6）。

---

## 3. Fixture 变更合同（永久纪律）

1. **Single source of truth**：所有新叙事只进 `backend/seed/fixture.py`；runtime fallback（`deterministic_pipeline.py`）继续禁止 import seed。
2. **FACTS 一致性**：每加一句叙事，先问是否与 6 条既有 FACTS 矛盾；新增事实必须登记进 `FACTS` 并在 `test_seed_integrity.py` 加断言。
3. **Span 锚定规则不变**：新 candidate 必须带 verbatim `quote`，由 `locate_span` 字符串匹配定位；匹配失败 → drop，不得 fuzzy match、不得手写 index/offset。
4. **author_role 语义不变**：历史/复查 note = `clinician`；AI summary = `system`；本卡不给历史事件补 AI summary（历史事件保持 clinician-authored，避免制造“AI 摘要历史病历”的错误语义）。
5. **两时间轴**：新 Event 的 `started_at/ended_at` 取叙事时间；Timeline 排序只吃 `started_at`。fixture 的 `created_at` 使用明确、确定性的“记录产生时间”（通常略晚于 Event），不得读取 seed wall clock，也不得拿 `created_at` 冒充 `started_at`。
6. **id 风格**：沿用现有命名，建议 `EVT_REVIEW_0826` / `ART_REVIEW_NOTE` / `ART_REVIEW_INSTRUCTION` / `hl_*` 语义化 ID。
7. **既有人物/药物/数值不改写**：propranolol 20 mg daily（2026-02-06 起）、BP 158/96（08-21）、blood test pending 等既有事实只许延伸，不许篡改。

---

## 4. Event 5 — clinician review 设计

叙事目标（须与 FACTS 对齐后定稿）：

```text
2026-08-26 clinician_review（evt_review_0826）
├─ clinician_note（art_review_note，v1；ArtifactVersion v1 由既有 seed backfill 生成，不伪造初始 AuditLog）
│   ├─ 头痛严重度从 7/10 改善到约 3/10；频率在现有证据中仍为 UNKNOWN，不得写成“频率回落”
│   ├─ 晨起恶心仍在 → 计划调整（如继续观察/对症建议，不下诊断结论）
│   ├─ blood test 结果仍未回来 → 明确“催结果/待结果回来后复诊”→ 使 task:blood test 跨 Event 重复出现
│   └─ 继续 propranolol 20 mg daily（呼应 2026-02-06 历史用药）
└─ patient_instruction（art_review_instruction，本卡必需）
    └─ 患者可执行事项：继续服药、完成血液检查、按约复诊
```

必须演示的“变化”：

- Timeline 顶部出现最新 `clinician_review` Event（`started_at` 排序）；
- Glance 中 `task:blood test` 因第二个 Event 提及触发 `repeated_mentions=true`：**既有 `hl_blood_test_pending` 与新 Highlight 两侧分数都重算**（逐代码路径验证，不许只给新条目加分）；
- headache 实体跨 `evt_hist_2025` / `evt_pre_0820` / `evt_fu_0824` 出现，验证跨月/跨年 repeated_mentions；
- 新 clinician note 可编辑：demo 时现场 edit → v2 → diff → revert 链路照常工作（Scenario B 素材）。

---

## 5. 历史 Event 丰富化设计

```text
2025-04-15 historical_review（evt_hist_2025）— 初次头痛评估
  note 要点：偶发头痛（约每周一次）初诊；无 red flag；建议观察/记录头痛日记。
  → 与 2026-08 “once weekly → near-daily” 形成真实对照，支撑 symptom_change 叙事。

2026-02-06 historical_review（evt_hist_2026）— 药物复查
  note 要点：头痛频率上升，启动 propranolol 20 mg daily 预防性用药；嘱随访。
  → 支撑 “medication:propranolol 20 mg daily since 2026-02-06”（已有 hl_medication_existing，保持 quote 锚定有效）。
```

约束：

- 历史 note 适度扩写即可，**不新增 Event 类型、不引入新 Artifact 类型**；
- 若历史 note 改写导致 `hl_medication_existing` 的 quote `"Start propranolol 20 mg daily"` 失配，必须同步修正 candidate 或保留原句；
- 历史事件保持 clinician-authored + 低分（无 recency/risk），在 Glance 中自然让位于当前 episode——这正是 Scenario C “为什么旧的低价值信息排在后面”的演示素材。

---

## 6. Scoring 验证合同（不改权重）

冻结权重（M2/M4 已锁定，本卡只验证不改）：

```text
score = 2*recency + 3*explicit_risk + 2*unresolved_task
      + 2*clinician_confirmed + 3*symptom_change + 1*repeated_mentions
```

- `recency` 以注入的 `as_of` 计算，测试不读 wall clock；新 Event（08-26）与 08-24 follow-up 的 recency 断言要选对 `as_of`；
- `repeated_mentions`：同一 `entity_key` 出现在 ≥2 个不同 Event 的有效 Highlight → 两侧重算；本卡固定验证 `task:blood test` 与 `symptom:headache frequency`，不得用近似 key、前缀匹配或 fuzzy matching；
- `clinician_confirmed` 仍只能由 clinician accept/pin 触发，seed 不预置 confirmed 状态（demo 现场操作，供 Scenario B/自学习使用）；
- `unresolved_task=false`：pending 仍可保留在 `assertion_value` / 文本中供人理解，但没有 Task/status model 就不能获得 unresolved-task 加分；
- seed generator 接收显式 `as_of`（建议冻结为 `2026-08-26 12:00`），从 Event `started_at` 计算 recency；不得继续信任 fixture 中手填的 recency；
- seed generator 在全部 quote 成功锚定后，按 `entity_key` 的 distinct `event_id` 分组计算 repeated_mentions，再统一计算 score；quote 失败被 drop 的 candidate 不得参与 repeated 计数；
- seed 生成路径与 M4 ingestion 路径产出的 Highlight 字段结构必须一致（entity_type/entity_key/assertion_value/review_status），不许出现“seed 特供形状”。

---

## 7. Synthea 决策门（默认不做）

进入评估的前提（全部满足才可讨论）：

1. 本卡 §4–§6 全部完成、测试全绿、Scenario C 人工走查通过；
2. 距 Milestone 6 feature freeze 仍有 ≥ 8 小时余量；
3. owner 明确同意。

若评估通过，仅允许：

- 用 Synthea/synthetic FHIR 生成 structured history backbone，选 1 个患者；
- 只映射 Patient / Encounter / Condition / Observation / MedicationRequest / AllergyIntolerance 中本项目真实使用的字段；
- 围绕同一 patient truth 生成叙事，**禁止**让 FHIR 模型反向重构 Event/Artifact/Span 内部模型。

任一前提不满足：在 README/Brief 中如实记录“Synthea 未采用，demo 数据为手写 canonical fixture”，这完全符合 Candidate Brief 的 Synthetic Data Only 要求。

---

## 8. 任务分解（串行，每步一个 commit）

| # | 任务 | 验证 |
|---|---|---|
| 0 | baseline：全量 pytest + frontend build；确认 M4 commit 已在历史中 | 103+ 测试绿；build 通过；不重做 live adapter |
| 1 | `FACTS` 扩展（Event 5 计划、历史事件细节）+ `test_seed_integrity.py` 新断言 | fact 断言先行（可先红后绿）；不把严重度改善写成频率改善 |
| 2 | 历史 Event 1/2 note 适度丰富化 | quote 锚定不失效；全量测试绿 |
| 3 | Event 5 clinician_review + clinician_note + patient_instruction 落库 | v1 snapshot 由既有 backfill 生成；Timeline 排序正确 |
| 4 | seed scoring 结构化计算：显式 as_of recency、unresolved=false、distinct-Event repeated 两侧重算 | 新增 scoring 测试绿；不手填/猜测结构性 flags |
| 5 | 新 Highlight candidates + exact provenance | quote 先锚定再参与 repeated 分组；Glance 排序可解释 |
| 6 | reseed demo DB + 前端人工走查 Scenario C 全链路 | 跨年/跨月层级、Glance 优先级、source jump、needs-review、edit/revert 均可演示 |
| 7 | README demo data 段落回填 + AGENTS.md §19 状态追加 M5 段 | 文档与实际一致 |
| 8 | Synthea 决策留痕；默认结论“不采用”，只有 §7 三项前提全满足才可另行评估 | 不做也必须写明理由；不得影响硬门 |

---

## 9. 测试矩阵

### `test_seed_integrity.py`（扩展）

- Event 5 存在、类型 `clinician_review`、`started_at` 晚于 `evt_fu_0824`；
- 新 FACTS 逐条断言；
- Event 5 只声明已有证据支持的变化：头痛严重度改善；若未新增可靠事实，频率保持 UNKNOWN；
- Event 5 clinician note 有且仅有一条 v1 snapshot，初始 seed 不伪造 edit/revert AuditLog；
- patient instruction 为 patient-visible artifact，且不包含内部临床评论或 reasoning；
- 历史 note 包含既定关键句；既有 candidate quote 仍可锚定（`extract_text == quote`）。

### 新增 scoring / longitudinal 测试（可并入现有 highlight 测试文件或新文件）

- 跨 Event 同一精确 `entity_key` → 两侧 Highlight `repeated_mentions` 均为 true 且分数均含 +1；同 Event 重复两次不触发；
- quote 无法锚定而被 drop 的 candidate 不参与 repeated_mentions 计数；
- 跨月/跨年 mention（2025 hist ↔ 2026 episode）同样触发；
- 显式 `as_of=2026-08-26 12:00` 下，08-20/21/24/26 Event 均按 7-day 合同计算 recency，2025-04 与 2026-02 历史 Event 无 recency；
- 所有 seed Highlight 的 `unresolved_task` 均为 false；pending 文本不会得到该项 +2；
- 新 seed Highlight 的 provenance 链（Highlight → Artifact → Event → span）全部可解析（复用 `test_highlight_provenance` 的断言辅助）。

### 回归

- 全部既有测试（103）零回归；
- M4 的 ingestion / fallback / conflict / RBAC 测试不得因 fixture 增容而变脆（发现变脆 = seed 与 runtime 耦合泄漏，停下来修耦合，不改测试放水）；
- frontend TypeScript/Vite build 通过。

---

## 10. Exit Gate — Longitudinal Demo Data Complete

用 reseed 后的 demo DB 人工走查，必须全部成立：

1. Timeline 呈现 2025-04-15 → 2026-02-06 → 2026-08-20/21/21/24/26 的清晰层级，排序只吃 `started_at`；
2. Event 5 的 updated plan 可见，且 clinician note 可 edit/diff/revert；
3. Glance 顶部被当前 episode 的高价值项占据（pending blood test、持续恶心、头痛严重度/既往频率变化），历史低价值项自然靠后，且每一项分数都能按冻结权重解释；不得为了固定某个视觉顺序改权重或伪造 flag；
4. `task:blood test` 等跨 Event 实体两侧分数重算已被测试与界面双重证实；
5. 每条新 Highlight 点击可跳回 exact source span；
6. 103+ 测试全绿；frontend build 通过；`git diff --check` 通过；README/AGENTS 状态一致；
7. Synthea 决策有明确留痕（做/不做 + 理由）。

通过后只可声明：

> **M5 / Longitudinal Demo Data Complete**

---

## 11. 停止条件与风险

- baseline 中 M4 出现回归 → 先修，不进 M5；不得把回归归因于 fixture 后直接放宽测试；
- 新叙事与既有 FACTS 冲突 → 改叙事，不改 FACTS 既成事实（除非 owner 批准）；
- quote 锚定失败 → drop candidate，不得放宽匹配；
- 为凑 longitudinal 效果而改冻结权重、把 UNKNOWN 当 true、手填不符合规则的 recency/repeated/unresolved flag、引入 Task 表或做 Patient View → 越界，停止；
- fixture 增容导致 runtime 测试变脆 → 暴露 seed/runtime 耦合，先解耦再继续；
- Synthea 前提不满足却动工 → 越界，停止。

---

## 12. 后续阶段预警（不在本卡范围，但影响排期）

M5 之后仍欠的**硬门**（Completion Definition 必需）：

- **Patient View 页面**（§4.3 + 完成定义 #6）：目前完全未动工，是最大缺口，建议 M5 完成后立即排期（预计 0.5–1 天，可复用 `PATIENT_VISIBLE_ARTIFACT_TYPES` 与既有 session API）；
- **性能测量**（Phase 6）：warm-path Glance P95 ≤ 300 ms 的测量方法需写入 Technical Brief；
- **Milestone 6**：Technical Brief、demo video、Scenario A/B/C 正式录制、最终打包提交。

排期建议：M5（0.5 天）→ Patient View（0.5–1 天）→ 性能测量 + Brief + 视频（剩余全部），Bonus（self-learning 等）仅在上述全绿后启动。
