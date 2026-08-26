# Nightingale 72 Hour Build — 完整开发计划

> 基于 `2026 72 Hour Build_ Nightingale Candidate Brief 2.pdf` 复核，并结合当前项目已经确定的 `README.md` / `AGENTS.md` 产品方向整理。
>
> 截止时间：**2026-08-28 17:30 SGT/MYT**。
>
> 当前原则：**先打通一条真实、可验证的端到端闭环，再扩展功能；required gates 先于 bonus，正确性 / provenance / RBAC 先于 UI polish。**
>
> **当前执行状态（2026-08-26）**：M1–M6 与 Phase C（C1 Backend + C2 Clinician Workspace）已完成（156 pytest、frontend production build、1280px browser QA 通过）；当前进入 Phase 6 Performance + Core Hardening。Phase C 只把既有能力产品化，不改变 required gates，也未增加 Voice、Task、Doctor AI Assistant 或 Nurse Workspace。

---

## 0. PDF 复核后的结论

现有规划方向与 Candidate Brief 基本一致，没有需要推翻的架构决策。需要在执行中明确保留以下几点：

1. **患者页面应是一个 unified single patient page**。Timeline、Glance、collaboration、tasks 等可以分区域或 tab，但产品体验仍围绕同一个患者纵向记录展开，而不是拆成互不关联的子产品。
2. **Glance 面向 clinician 和 staff**，不是只面向医生；目标仍是进入 consult 时 **10 秒内可读、可行动**。
3. **AI-scribed notes 必须作为独立 Timeline entries / Artifacts 保存**，至少覆盖：
   - `ai_doctor_consult_summary`
   - `ai_nurse_consult_summary`
   - `ai_patient_session_summary`
   - `author_role = system`
4. **Revision 不只是 history/revert**，还必须支持或清晰演示 `view changes since X` / diff。
5. **Concurrent edits 是硬性测试项**。不需要实现 Google Docs 级 CRDT；MVP 可以用 section-level ownership + optimistic concurrency / version check，只要不同 section 不覆盖、同 section 冲突有 deterministic strategy。
6. **Glance 的 P95 warm-path ≤ 300ms** 不只要做到，还要在 Technical Brief 中说明如何测量或近似测量。
7. **PHI redaction 必须发生在任何数据进入 LLM 之前**，至少处理姓名、IC/ID、电话号码；日志也必须保持 clean。
8. Bonus 的优先级要调整：评分中明确单列 **Nightingale Alignment Bonus 10 分**，重点是：
   - Self-Learning Importance
   - Hybrid Storage / Data Decay
   因此 core 稳定后，这两个 bonus 应优先于 Voice Capture。
9. Demo Scenario C 应真正体现 longitudinal context，synthetic journey 至少包含跨月、最好跨年的历史事件，而不是全部集中在同一周。
10. 最终交付必须在开发期间同步准备：README、2–3 页 Technical Brief、`ATTRIBUTION.txt`、Demo Video、clear commit history，不能等最后一小时才开始。

这些是对现有计划的补强，不改变我们的核心产品模型：

```text
Timeline = what happened.
Glance View = what matters now.
Patient View = what the patient needs to know/do.
```

---

# 1. 总体开发策略

本项目不采用：

```text
完整前端
→ 完整后端
→ 完整 AI
→ 最后找数据
→ 最后测试
```

而采用 **vertical slice + gated iteration**：

```text
定义最小数据关系
        ↓
创建极小 synthetic patient fixture
        ↓
跑通 Patient → Event → Artifact → Span
        ↓
跑通 Transcript → AI Summary → Highlight → Glance → Source
        ↓
加入 Collaboration / Revision / RBAC
        ↓
替换为真正 AI pipeline
        ↓
扩充 longitudinal synthetic data
        ↓
Clinician New Consult + Manual Transcript
        ↓
Clinician Shell + Event Detail + Comment Context
        ↓
性能 / Required tests
        ↓
Self-learning + Data Decay Bonus
        ↓
Freeze / Brief / Demo / Submission
```

核心思想不是“做很多模块”，而是逐步建立四条闭环：

### 闭环 A：记录

```text
现实医疗事件
→ Event
→ Artifact
→ Timeline
```

### 闭环 B：AI + Trust

```text
Raw Source
→ Redaction
→ AI Summary / Extraction
→ Highlight
→ Glance
→ Provenance
→ Exact Source Span
```

### 闭环 C：多人协作

```text
Staff / Clinician Input
→ Comment / Edit / Task
→ Revision
→ Conflict handling
→ Audit
```

### 闭环 D：Longitudinal reasoning

```text
历史 Events
+ 当前 Episode / Events
+ unresolved actions
+ clinician-confirmed information
→ 当前最重要的信息
```

---

# 2. 核心数据和时间结构

## 2.1 MVP 核心对象

先确定以下概念，不需要一开始把所有东西做成复杂独立服务：

```text
Patient
  ↓
Optional Care Episode
  ↓
Event
  ↓
Artifact
  ↓
Span
```

同时关联：

```text
Highlight
Comment / Thread
Task
Version
AuditLog
User
Role
Clinic Scope
```

`Care Episode` 第一版可以只作为 conceptual grouping / optional field，不强制为了它增加复杂数据库和 UI。

同一次现实到院可能包含多个角色 Event。为支持已确认的前端视觉分组，C1 在 `Event` 增加可选 `encounter_id` 字符串，但不新建 Encounter 表：

```text
Clinic Visit（UI projection：相同且非空 encounter_id）
  ├─ Nurse Consult Event
  └─ Doctor Consult Event
```

`Event` 仍是 canonical Timeline unit。`encounter_id` 只用于说明两个 Event 属于同一次现实到院；不得按同一天、相近时间或结果需要自动合并。

## 2.2 多尺度时间模型

主 Timeline 以现实世界的 `Event` 为单位，例如：

```text
2025-04-15  Primary Care Review
2026-02-06  Medication Review
2026-08-20  Patient AI Pre-consult
2026-08-21  Nurse Consult
2026-08-21  Doctor Consult
2026-08-24  Patient Follow-up
```

一个 Event 内部仍然保留自己的 chronological lifecycle：

```text
Doctor Consult — Aug 21 10:00–10:35
│
├── 10:00–10:35  Actual consult / transcript
├── 10:38        AI doctor summary
├── 10:44        Clinician note
├── 11:02        Nurse supplement
├── 11:16        Doctor comment
├── 11:34        Nurse reply
└── Aug 23 09:10 Clinician revision
```

必须区分：

- `started_at / ended_at`：医疗事件实际发生时间；
- `created_at / updated_at`：围绕事件的记录、评论、修改发生时间。

Aug 23 修改 Aug 21 的 note，仍属于 Aug 21 的 Event，不应被错误展示成一个 Aug 23 的新医疗事件。

UI 使用 progressive disclosure，不做无限嵌套的可视时间轴：

```text
Longitudinal Timeline
→ Event Detail
→ Artifact / Thread / Revision
→ Exact Source Span
```

---

# 3. 并行开发组织方式

建议最多保持四条并行 Track，并严格控制文件 ownership，避免多个 Agent 同时重写相同模块。

## Track A — Core Backend / Data

负责：

- schema / database；
- Patient / Event / Artifact / Span；
- provenance resolver；
- Task / Comment / Version / Audit；
- importance scoring；
- caching / warm-path API。

## Track B — Product UI

负责：

- unified patient page；
- Glance；
- Timeline；
- Event detail；
- Artifact display；
- comments / mentions / tasks；
- revision / diff / revert UI；
- Patient View。

## Track C — AI / Synthetic Data

负责：

- canonical synthetic patient fixture；
- PHI redaction pipeline；
- doctor / nurse / patient-session summaries；
- structured candidate extraction；
- source-span mapping；
- 后期 Synthea / synthetic longitudinal enrichment。

## Track D — Security / Tests / Delivery

负责：

- server-side RBAC；
- clinic scope；
- required micro-tests；
- concurrency tests；
- performance measurement；
- README / Technical Brief / Attribution；
- demo checklist。

### 并行原则

可以并行的是“已经有明确输入输出边界”的任务。

例如：

- Timeline UI 可以使用 mock API 与后端并行；
- AI pipeline 可以对 fixture 跑，与 Glance UI 并行；
- RBAC tests 可以与 UI 开发并行；
- Technical Brief 的架构图可以在 schema 稳定后提前绘制。

不能盲目并行的是：

- 多个 Agent 同时改 schema；
- UI Agent 自己改变后端数据结构；
- AI Agent 自己改变 provenance contract；
- tests 为了通过而修改产品规则。

每一个 major gate 后进行一次 integration，再继续下一轮并行开发。

> **容量提醒**：Track 划分首先是模块边界和 ownership 边界，不等于真实并行产能。如果实际执行是"一个人 + LLM"串行工作，真实容量必须按串行估算——同一时间只推进一条 Track，其余 Track 用已冻结的 mock contract 等待，不要用四条 Track 的排期安慰自己。

---

# 4. Phase 0 — 冻结最小设计与开发边界

## 目标

在大量写代码前，把系统中“哪些东西存在、怎么关联、最核心的数据如何流动”说清楚。

不要写大型设计文档；目标是防止后面反复推翻基础关系。

## 要做什么

1. 确认 MVP entities：
   - Patient
   - Event
   - Artifact
   - Span
   - Highlight
   - Comment
   - Task
   - Version
   - AuditLog
   - User / Role / Clinic
2. 明确三种 AI artifact type 及 `author_role = system`。
3. 明确 event time 与 artifact/activity time。
4. 明确 provenance pointer 至少能定位：
   - Event
   - Artifact
   - exact span / message / transcript segment。
5. 明确核心 API / function contract，只定义当前 vertical slice 必需项。
6. 明确同 section concurrent edit strategy，例如：
   - version mismatch → reject stale write + return conflict；
   - 或 deterministic last-write policy，但必须可审计。
7. 明确 Clinician / Staff 不能互相覆盖对方 author-owned notes。
8. **锁定技术栈**（Phase 0 第一小时内完成）：选型标准 = 72 小时内最不容易出错的栈，而不是最强的栈；锁定后立即写入 README / `ATTRIBUTION.txt` 草稿，freeze 后不得更换。
9. **锁定 role context 机制**（如 header / session 注入的 synthetic user role + server-side 解析），因为 RBAC 测试直接依赖它。

## 可并行

- Track A：schema draft；
- Track B：patient page wireframe / mock data contract；
- Track C：fixture structure；
- Track D：根据 brief 写 test assertions checklist。

## 验收

Agent 必须能明确回答下面这个例子：

> Aug 21 发生一次 Doctor Consult；它有 transcript、AI summary、clinician note、nurse supplement；Aug 23 医生修改了 clinician note；Glance 中一条 highlight 来自 transcript 第 17 段。它们分别存在哪里、如何关联、如何定位到原句、Aug 23 修改为什么仍属于 Aug 21 Event？

如果回答不清楚，Phase 0 不通过。

同时：技术栈与 role context 机制必须已锁定并记录，否则 Phase 0 同样不通过。

---

# 5. Phase 1 — 最小系统骨架 + Canonical Synthetic Fixture

## 目标

系统第一次真正运行起来，但不追求完整 AI 和漂亮 UI。

## 开发数据

先手写一个很小、完全可控的 synthetic fixture，不等外部数据集。

建议只做一个主患者：

```text
Patient A
│
├── 2025-04-15  Historical primary care review
├── 2026-02-06  Medication review
└── 2026-08      Current headache episode
    ├── Aug 20 Patient AI pre-consult
    ├── Aug 21 Nurse consult
    ├── Aug 21 Doctor consult
    └── Aug 24 Patient follow-up
```

当前 episode 的事实保持非常有限、稳定，例如：

- headache 从每周一次变为接近每天；
- morning nausea persists；
- elevated BP；
- existing medication；
- blood test pending；
- follow-up scheduled。

所有后续 transcript / summary / note 必须围绕同一份 synthetic truth，不得互相随机矛盾。

## 要做什么

### Backend

- database / minimal schema；
- seed fixture；
- patient read；
- timeline events read；
- event artifacts read。

### UI

建立 unified patient page，至少有：

```text
Patient header / context
Glance placeholder
Longitudinal Timeline
Event detail / expand
```

### 暂时可以 fake 的部分

- AI summary 可以先是 fixture；
- highlight 可以先 deterministic；
- 用户切换可以先用 synthetic users；
- 不需要完整 authentication product flow，只要 server-side role context 能被测试。

## 可并行

Track A 和 B 基本可以完全并行；Track C 同时制作 fixture；Track D 开始建立测试框架。

## 验收

从浏览器：

1. 打开一个患者；
2. 看到跨日期 Timeline；
3. 展开 Doctor Consult；
4. 看到至少 transcript、AI summary、clinician note；
5. raw / AI / clinician authored content 没有互相覆盖。

只有这一条跑通后才能进入下一阶段。

---

# 6. Phase 2 — 第一条 Vertical Slice：Glance → Provenance → Exact Source

## 目标

先验证项目最关键、最有辨识度的信任链，而不是急着接复杂 LLM。

## 核心示例

```text
Patient source:
“My headaches used to happen once a week, but now they're almost every day.”

↓

AI Summary:
“Headache frequency increased from weekly to near-daily.”

↓

Highlight:
“Worsening headache frequency”

Risk reason:
“Recent symptom worsening / frequency increase”
```

医生或 staff 点击 highlight：

```text
Glance
→ originating Event
→ AI Summary Artifact
→ source Transcript Artifact
→ exact sentence / span
```

## 要做什么

### Provenance

每个 highlight 至少具有：

- `event_id`
- `artifact_id`
- `source_artifact_id`
- `source_span`
- `risk_reason`

并保证 pointer 真能 resolve，而不是装饰字段。

### Glance MVP

只放少量高价值信息，建议 3–5 条：

- current risk / worsening symptom；
- unresolved task；
- clinician-confirmed item；
- medication/allergy if relevant；
- follow-up action。

每条必须：

- readable；
- risk_reason；
- provenance；
- source navigation；
- accept / reject 基础交互。

### Test

开始完成 `test_highlight_provenance.py`。

## 为什么暂时可以不用真正 LLM

这一阶段最重要的是证明：

> 系统能保存、解析和展示 AI 信息的来源。

LLM summarization 本身不是这里最大的工程风险。可以先用 deterministic summary / extraction 把 trust chain 跑通。

## 可并行

- Track A：provenance resolver；
- Track B：Glance + source jump；
- Track C：deterministic AI stub；
- Track D：provenance test。

## 验收

1. Glance 3–5 条信息在 10 秒内可以理解；
2. 每条有 `risk_reason`；
3. 每条有可解析 provenance；
4. 点击至少一条 AI-derived highlight 可以跳到确切 source span；
5. `test_highlight_provenance.py` 通过。

这是第一个必须可 demo 的 milestone。

---

# 7. Phase 3 — Collaboration + Revision + RBAC

## 目标

把系统从“可追溯的信息查看器”变成真正的 shared care record。

这一阶段可以高度并行。

## 3A. Collaboration

至少支持：

- staff note；
- clinician note；
- threaded comments；
- resolve / unresolve；
- `@clinician` 或 `@staff` mention；
- optional assignment / task。

Scenario B 需要能够演示：

```text
Staff adds note
→ comment with @clinician
→ clinician reviews
→ clinician manually highlights a phrase in AI-scribed note
→ clinician edits plan
```

不要求复刻 Google Docs 的实时光标和 CRDT。

## 3B. Revision / Audit

至少支持：

```text
Note v1
→ Edit
→ Note v2
→ diff / view changes since X
→ revert to v1
```

AuditLog 记录 metadata：

- actor；
- role；
- action；
- time；
- target/version。

不要把 raw clinical content 不必要地复制进 audit log。

## 3C. RBAC

最低角色：

- patient
- staff
- clinician
- admin

必须 server-side enforce。

重点验证：

- Patient 看不到 internal clinician/staff comments；
- Patient 看不到 raw clinical AI-scribed notes；
- Staff 不能以 clinician 身份写/覆盖 clinician note；
- Clinician 不能以 staff 身份覆盖 staff note；
- Staff/Clinician 都不能访问其他 clinic 的 patient data；
- Admin 仍然 clinic-scoped。

## 3D. Concurrency

不同 section：

```text
Staff edits staff section
Clinician edits clinician section
→ 两者都保留，不互相覆盖
```

同 section：

必须有 deterministic strategy，例如 version check：

```text
Client A reads version 3
Client B reads version 3
A saves → version 4
B saves with expected_version=3
→ conflict / stale-write rejected
```

## Required Tests

这一阶段必须完成并通过：

- `test_rbac_scope.py`
- `test_revision_history.py`
- `test_concurrent_edits.py`

## 可并行

- Track A：versioning / comments / task backend；
- Track B：comment + revision UI；
- Track D：RBAC / concurrency tests。

RBAC owner 不应与 UI 隐藏逻辑混为一体；UI guard 只用于 UX，真正拒绝必须发生在 server-side。

## 验收

人工走一遍四角色行为 + required tests 全绿。

如果 Patient 能通过 API 拿到 forbidden data，即使 UI 隐藏成功，也判定失败。

## 滑期预案（预先批准的砍项）

Phase 3 是全计划推理密度最高的阶段，也是 Milestone 3 时间窗最可能吃紧的点。如需砍 scope，严格按此顺序：

1. assignment / task 分派（保留 comment + mention 即可满足 Scenario B）；
2. diff UI 简化为最朴素的前后版本对照（保留底层 diff / changes-since-X 数据能力）；
3. admin 角色专属 UI（保留 server-side admin scope 规则）。

**不得砍**：server-side RBAC、version / revert、concurrency 确定性策略、三个 required tests。

---

# 8. Phase 4 — 真正 AI Pipeline + Smart Prioritization

## 目标

在 provenance、storage、permissions 已稳定后，再让真正 LLM 进入核心链。

## AI Pipeline

三类最小 flow：

```text
Patient-AI session
→ ai_patient_session_summary

Nurse consult
→ ai_nurse_consult_summary

Doctor consult
→ ai_doctor_consult_summary
```

全部：

```text
author_role = system
```

AI summary 与 raw source、clinician/staff note 必须并列存在，不覆盖。

## PHI Redaction

所有 LLM-bound text：

```text
Raw Input
→ redact name
→ redact IC / ID
→ redact phone
→ LLM
```

即使当前使用 synthetic data，也必须真实体现这条 pipeline。

日志不得泄漏未 redacted 原文。

## Structured Extraction

AI 可同时提出 candidate structured entities：

- symptom；
- medication；
- allergy；
- chief complaint；
- task；
- risk；
- symptom change。

这些是 candidate / derived information，不自动成为 clinician authority。

## Span 锚定设计决策（开工前写死）

LLM 不得输出 span index / offset 供系统直接信任。正确做法：

- LLM 只负责**引用原文句子**（quote exact source text）；
- span 定位由**确定性字符串匹配**完成（在 source artifact 中定位 quote 对应的 offset / segment / message）；
- 匹配失败 → 该 candidate 降级或丢弃，不得硬造 span；
- 这条规则保证 provenance 可测试、可复现，是 Phase 4 不返工的前提。

## LLM 失败兜底

任何 LLM 调用失败 / 超时 / 输出不合法时，系统回退到 Phase 2 保留的 deterministic stub。demo 和 required tests 不得依赖外部 LLM API 的实时可用性。

## Importance Ranking

MVP 不让 LLM 单独决定“最重要的五条”。

使用 transparent weighted logic，例如：

```text
importance_score =
    recency
  + explicit_risk
  + unresolved_task
  + clinician_confirmed
  + symptom_change
  + repeated_mentions
  - stale_penalty
  - resolved_penalty
```

每条 highlight 都要能解释为什么高分，而不是只有一个神秘 score。

## Glance Interaction

至少：

- accept；
- reject；
- provenance；
- source navigation；
- risk_reason。

建议加：

- pin；
- manual highlight；
- clinician edit。

这些行为以后直接作为 self-learning feedback。

## 可并行

- Track C：redaction + LLM + extraction；
- Track A：importance score / precompute；
- Track B：accept/reject/pin/manual highlight UI；
- Track D：AI provenance / security regression tests。

## 验收

拿一份不在固定 seed 输出中的新 synthetic transcript：

1. 经过 redaction；
2. 生成正确类型 AI summary；
3. 生成 candidates/highlights；
4. 每条保持 provenance；
5. 进入 Glance；
6. source jump 仍然工作；
7. clinician note 不被 AI 覆盖；
8. conflict 时 clinician authority 或 review flag 生效。

---

# 9. Phase 5 — Longitudinal Demo Data + Optional Synthea Enrichment

## 目标

把“能工作的小样例”扩展成一个有说服力的 longitudinal patient journey。

Candidate Brief 只要求 **Synthetic Data Only**；是否采用 Synthea 是我们的实现选择，不是任务硬性要求。

## 推荐数据策略

### 开发阶段

继续使用 canonical fixture，保证测试确定性。

### Demo 阶段

可以：

- 使用 Synthea / synthetic FHIR 作为 structured history backbone；
- 从中选择一个患者；
- 只映射当前项目真正使用的资源，而不是实现整个 FHIR：
  - Patient
  - Encounter
  - Condition
  - Observation
  - Medication / MedicationRequest
  - AllergyIntolerance
  - DiagnosticReport（如需要）
- 再围绕同一个 patient truth 生成当前 doctor / nurse / patient-AI narrative。

不要让 FHIR integration 反过来重构已经稳定的内部模型。

## Demo Journey

至少体现：

```text
2025-04-15  historical event
2026-02-06  historical event
2026-08     current care episode
```

当前 episode 继续包含：

- patient pre-consult；
- nurse consult；
- doctor consult；
- patient follow-up；
- clinician review / pending task。

## 验收

Scenario C 可以清楚回答：

> 这个患者过去发生过什么？现在什么变了？哪些事情仍未完成？为什么 Glance 现在优先显示这些信息？

并且历史事件、当前 Event、内部 Artifact、source span 的时间层级没有混乱。

---

# 9A. Current Phase C — Clinician Consult Workflow（性能验收前）

## 为什么插入 C

M1–M6 已证明数据、安全和 AI 链路成立，但当前前端仍是固定患者、860px 单列、硬编码 transcript ingestion 的功能 Demo。直接进入 Performance 会测到一个尚未形成真实医生工作流的页面。

C 阶段不增加新的产品方向，而是把现有能力组织成一条医生可操作的闭环：

```text
Clinician Workspace
→ New Consult
→ new Doctor Consult Event
→ Manual Transcript
→ AI Doctor Summary / Highlights
→ Event Detail / exact source
→ Clinician Note / Comment
→ Timeline + Glance
```

详细合同以两张任务卡为准：

- `Task_Card/C1_Task_Card.md`：Encounter + Transcript schema + clinician-only Doctor Consult backend；
- `Task_Card/C2_Task_Card.md`：Clinician Shell + New Consult UI + Timeline master/detail + Comment/Source integration。

## C1 — Encounter + Manual Doctor Consult Backend

> 状态：**COMPLETE（2026-08-26）**；Exit Gate 为 156 pytest + frontend production build 通过。

核心工作：

- optional `Event.encounter_id`；
- 2026-08-21 Nurse/Doctor Events 通过同一显式 encounter 组成 Clinic Visit，不按日期自动分组；
- strict `doctor|patient` transcript segments；
- `POST /api/patients/{patient_id}/doctor-consults`；
- stable idempotency、raw-first persistence、metadata-only audit；
- 复用现有 redaction / `LLMClient` / fallback / extraction / provenance pipeline；
- clinic-scoped patient list/current identity 的最小只读支持；
- RBAC、invalid input、idempotency、fallback、exact span 自动化测试。

C1 不做 UI 重构、Nurse input、Voice、Task、AI Assistant 或外部 dataset ingestion。

## C2 — Clinician Workspace + Consult Review UX

> 状态：**COMPLETE（2026-08-26）**；三栏 shell、New Consult、explicit Clinic Visit、Event/Artifact lifecycle 与 Source/Comments/Versions/Audit 已集成，156 pytest + frontend build + browser QA 通过。

核心工作：

- 三栏 Clinician Shell；
- `Clinic Patients`（不是尚无 assignment 支撑的 `My Patients`）；
- `Glance | Timeline | Notes`；
- 独立 New Consult paste / preview / processing/fallback 页面；
- Clinic Visit explicit grouping；
- Timeline master/detail、Event lifecycle、Artifact Reader；
- Source Viewer 右栏化；
- Comment/@mention/reply/resolve、revision、audit 上下文化；
- patient/role switch state isolation；
- full regression、frontend build、1280px/error-state visual QA。

C2 不展示假的 Tasks、Doctor AI Assistant、assignment、appointment 或 Nurse Workspace。

## Phase C Exit Gate

只有以下流程可重复演示且全部安全回归通过，才进入 Phase 6：

```text
New Consult
→ paste transcript
→ raw source saved
→ AI summary + Highlight
→ exact source
→ Comment / Clinician Note
→ Timeline + Glance refresh
```

Phase C 完成不等于 Performance Complete；Glance P95 测量仍严格属于下一阶段。

---

# 10. Phase 6 — Performance + Core Hardening

## 目标

在功能基本完整后，把 Glance 变成真正的 warm-path read，而不是 page-load LLM demo。

## 正确路径

```text
New / updated Event
→ async or background summary/extraction
→ candidate highlights
→ score/precompute
→ store/cache

Page Load
→ read precomputed Glance
```

禁止：

```text
Open patient page
→ send entire patient history to LLM
→ wait for model
→ render Glance
```

## 测量

对 warm-path Glance endpoint / page data path 做多次测量，记录：

- sample count；
- environment；
- warm-up method；
- P50；
- P95；
- 是否包含 network / DB / rendering；
- 近似测量的局限。

Technical Brief 明确说明 measurement / approximation method。

目标：

```text
P95 <= 300 ms
```

## 验收

- warm-path P95 达标或有诚实、可复现的近似说明；
- 不依赖 page-load full-history LLM；
- Required tests 全绿；
- 核心 demo 无明显 race / stale data 问题。

---

# 11. Phase 7 — Bonus，严格后置

进入条件：

```text
所有 required tests 通过
+ Scenario A/B/C 核心流程稳定
+ 没有高风险 RBAC / provenance bug
```

否则不做 Bonus。

## Bonus Priority 1 — Self-Learning Importance

优先实现，因为直接对应 Bonus scoring。

记录：

- accept；
- reject；
- pin；
- manual highlight；
- edit；
- comment。

最小 adaptive mechanism 即可，例如：

```text
Clinician pins “unresolved_task” candidate
→ corresponding feature weight increases
→ later similar candidate obtains higher score
```

重点不是复杂 ML，而是：

- feedback 被记录；
- weight change 可观察；
- 后续 ranking 真发生变化；
- mechanism 可解释。

完成：

- `test_self_learning_importance.py`

## Bonus Priority 2 — Hybrid Storage / Data Decay

至少做 schema + policy + 小型演示：

```text
old + low importance + resolved
→ compressed / summarized / cold representation
```

但：

- raw source / provenance 不得丢失；
- high-risk 不简单 decay；
- unresolved task 不 decay；
- clinician-confirmed critical information 不 decay；
- restore / source verification 路径仍成立。

如果时间不足，可以在 Technical Brief 中清晰解释 architecture + trade-off，并在 demo 中展示 policy，而不是仓促做复杂 storage tiering。

## Bonus Priority 3 — Ambient Voice

只有前两项和 core 均稳定后才考虑。

Patient voice：patient view only。

Clinical/staff voice：clinical view only。

理想输出：

- speaker-labelled transcript；
- timestamps；
- confidence markers；
- code-switching support；
- clinical summary；
- provenance to source segment。

noisy environment / diarization / overlap / multilingual terminology / multi-device 是 extra bonus，不应占用 core 时间。

---

# 12. Required Tests — Hard Gate

最终必须通过：

## `test_rbac_scope.py`

- staff 不能以 clinician 身份写/改；
- clinician 不能以 staff 身份写/改；
- patient 不能访问 internal comments；
- patient 不能访问 raw AI-scribed clinical notes；
- clinic scope enforced。

## `test_revision_history.py`

- edit increments version；
- revert restores old content；
- audit metadata 能说明 who / what / when；
- diff / changes-since-X 行为可验证或演示。

## `test_highlight_provenance.py`

- highlight 有 provenance pointer；
- pointer 能 resolve 到 Timeline Event / Artifact / span；
- AI-scribed highlight 也一样。

## `test_concurrent_edits.py`

- different-section concurrent edits 不互相覆盖；
- same-section conflict deterministic。

## Bonus: `test_self_learning_importance.py`

- 模拟 clinician feedback；
- subsequent similar candidate priority 上升或下降。

测试不是最后才补；每个阶段对应的 test 在该阶段完成。

---

# 13. 三个最终 Demo Scenario 的开发验收

## Scenario A — Glance + AI + Provenance

演示：

1. Staff / clinician 打开 Patient Page；
2. 10 秒内理解当前核心问题 / risk / actions；
3. 点击 AI-derived highlight；
4. 跳到 exact Timeline entry；
5. 继续定位 source span。

通过标准：无需口头解释复杂背景，UI 本身能表达“什么重要、为什么、来源在哪”。

## Scenario B — Collaboration + Audit + Learning Signal

演示：

1. Staff adds note；
2. adds `@clinician` comment；
3. Clinician manually highlights phrase in AI-scribed note；
4. Clinician edits patient plan；
5. version increments；
6. diff / changes since X；
7. revert；
8. audit trail；
9. 若 self-learning 已实现，说明 manual highlight 如何影响未来 ranking。

## Scenario C — Longitudinal Context

演示：

1. 跨月 / 跨年的历史 Events；
2. 当前 care episode；
3. symptom change；
4. unresolved action；
5. clinician-confirmed information；
6. why these items rank above older low-value information；
7. 若 data decay 实现，展示或解释 older low-value data 如何处理。

---

# 14. 最终交付与冻结计划

## Feature Freeze

建议至少在截止前 **8–10 小时**停止新增 core feature。

Freeze 后只允许：

- bug fix；
- test fix；
- data consistency fix；
- demo-path stabilization；
- README / brief / video / attribution；
- performance measurement；
- submission packaging。

不得在最后几小时：

- 重构 schema；
- 替换框架；
- 新增复杂 agent；
- 新增大型 RAG；
- 临时 fine-tune；
- 大规模 UI rewrite。

## 最终 Deliverables Checklist

### 1. Git Repository

- working application；
- required automated tests；
- clear commit history。

### 2. README

必须包含：

- setup；
- run；
- how to run tests；
- redaction happens where；
- RBAC how enforced；
- architecture / important trade-offs 的必要说明。

不得编造不存在的命令。

### 3. 2–3 Page Technical Brief

包含：

- architecture diagram；
- architecture explanation；
- comprehensive schema；
- Brief `Entry` ↔ 内部 `Event / Artifact / Span` 的显式术语映射（便于评委对应 Candidate Brief 的 schema 要求）；
- Event / Artifact / Comments / Versions / Highlights / Provenance / AI-scribed notes / learning mechanism 的关系；
- P95 measurement / approximation；
- assumptions；
- first-principles thinking；
- trade-offs / scope decisions。

### 4. `ATTRIBUTION.txt`

列出：

- external libraries；
- models；
- datasets / external assets（如使用）；
- licenses。

### 5. Demo Video

清晰演示 Scenario A/B/C；不要做成 feature tour，而要讲一个 longitudinal patient story。

### 6. Submission

截止并提交：

```text
Deadline: 2026-08-28 17:30 SGT/MYT
To:       irakumar@ntngale.com
CC:       frank.ng@ntu.edu.sg, carrene.teo@ntu.edu.sg
Subject:  Nightingale 72HR Build -- <Your Name>
```

最终按 Candidate Brief 要求，将 repo link / zip、Technical Brief 和 required deliverables 通过邮件提交到上述 To/CC 地址。

---

# 15. 从现在到截止时间的建议里程碑

以 2026-08-25 22:31 SGT 计，距离截止约 **67 小时**。不应把 67 小时全部规划成开发时间，必须给 integration、视频和提交留 buffer。

> 2026-08-26 状态更新：原 Milestone 1–4、M5 longitudinal data、M6 Patient View 与 Phase C（C1/C2）已完成。当前执行顺序更新为 **Phase 6 Performance → Freeze/Deliverables**；下列早期里程碑保留为历史计划记录。

## Milestone 1 — 最迟 8 月 26 日上午

完成：

- Phase 0；
- schema / contracts；
- canonical fixture；
- patient page + basic Timeline 可运行。

## Milestone 2 — 最迟 8 月 26 日晚

完成：

- Vertical Slice；
- Glance → provenance → exact source；
- `test_highlight_provenance.py` 基本通过。

这时已经要有一个最小可 demo 产品。

## Milestone 3 — 最迟 8 月 27 日中午

完成：

- collaboration；
- revision / diff / revert；
- RBAC；
- concurrency；
- 三个 required tests 对应链路基本全绿。

若时间窗吃紧，立即启用 Phase 3 滑期预案，不得硬扛。

## Milestone 4 — 最迟 8 月 27 日晚

完成：

- true AI pipeline；
- redaction；
- importance ranking；
- three AI-scribe types；
- full required tests 全绿。

此时 **Core Complete**。

## Milestone 5 — 8 月 28 日凌晨 / 上午

完成：

- longitudinal demo data 与 Patient View（已完成）；
- C1 Encounter + Manual Doctor Consult Backend；
- C2 Clinician Workspace + Consult Review UX；
- C2 Exit Gate 后再做 performance measurement；
- Scenario A/B/C walkthrough；
- 若 core 稳定：self-learning；
- 有余力再 data decay；
- Voice 仅在仍有明确余量时做。

## Milestone 6 — 截止前 8–10 小时

Feature Freeze。

完成：

- regression test；
- README；
- Technical Brief；
- `ATTRIBUTION.txt`；
- demo recording；
- clean commit history；
- final package；
- submission verification。

---

# 16. 每次 Integration Gate 都要问的 8 个问题

1. **患者历史还是一条 connected longitudinal record 吗？**
2. **AI summary 有没有覆盖 raw source 或 clinician note？**
3. **Glance 的每条重要信息都能解释“为什么重要”吗？**
4. **每条 AI-derived / highlighted information 都能回到真实 source span 吗？**
5. **Patient 是否通过 server-side 请求也拿不到 forbidden internal data？**
6. **Clinician / Staff 是否保持 author / role boundary？**
7. **修改和并发是否可审计、可回退、不会静默覆盖？**
8. **当前新增功能是否真的改善评分项，还是只增加复杂度？**

任意一个核心问题答案是否定的，应先修复，不继续加 feature。

---

# 17. 最终完成定义

Core Complete 不是“页面很多”，而是以下闭环全部成立：

```text
Synthetic longitudinal patient
        ↓
Real-world Event hierarchy
        ↓
Raw / AI / Clinician / Staff artifacts coexist
        ↓
AI summaries are redacted-before-LLM and traceable
        ↓
Glance surfaces actionable priorities
        ↓
Every highlight can return to source
        ↓
Patient / Staff / Clinician / Admin boundaries enforced server-side
        ↓
Comments / revision / diff / revert / audit work
        ↓
Concurrent edits have deterministic behavior
        ↓
Required tests pass
        ↓
Warm-path Glance performance is measured
        ↓
Scenario A / B / C can be demonstrated cleanly
        ↓
README / Brief / Attribution / Video / Repository ready
```

如果这条链成立，即使没有 Voice、复杂 learned ranker 或极致 UI polish，这仍然是一个完整、有逻辑、有信任机制的 Nightingale prototype。

反过来，如果页面很多但 provenance 断裂、RBAC 只是前端隐藏、AI 与 clinician content 混在一起、revision 会静默覆盖，那么不应视为完成。

---

# 18. 执行优先级

发生冲突时，按以下顺序决策：

```text
1. Correctness
2. Provenance / Trust
3. Server-side RBAC / Privacy
4. End-to-end workflow
5. Glance usefulness
6. Required tests
7. Performance
8. Self-learning / Data decay bonus
9. Demo polish
10. Voice / extra features
```

最终判断标准只有两个：

> **医生或 staff 能否在 10 秒内知道现在最重要的事情？**

> **他们能否立即验证这些信息究竟从哪里来？**

所有开发决策都应围绕这两个问题服务。
