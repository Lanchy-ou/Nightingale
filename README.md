# Nightingale 72 Hour Build — Project README

## 1. 项目目标

本项目要构建的不是一个普通 EHR 页面，也不是一个单独的 AI 问诊机器人，而是一套围绕患者长期诊疗过程运行的 **shared longitudinal care record system**。

核心目标：

- 将患者、医生、护士、staff、AI scribe 在不同时间产生的信息统一组织起来；
- 保留每条信息的来源、作者、时间、类型和版本；
- 让医生在进入患者页面后 **10 秒内理解当前最重要的问题、风险和未完成事项**；
- 让患者看到自己真正需要知道和执行的内容，而不是医生内部工作记录；
- 所有 AI 生成内容都必须可追溯、可核查，不能冒充 clinician-authored information。

一句话概括：

> 我们维护的是一份不断演化的患者状态；Timeline 记录“发生了什么”，Glance View 负责“医生现在最该关注什么”，Patient View 负责“患者现在需要知道和做什么”。

---

## 2. 核心使用流程

### 2.1 预约后：患者预问诊

患者预约后进入系统，首先完成一次 AI pre-consult session。

患者可以回答：

- 当前主要症状；
- 症状什么时候开始；
- 最近有没有变化；
- 严重程度；
- 当前用药；
- 希望医生知道的其他背景。

系统同时保存：

1. **Raw Patient-AI Session**
   - 完整对话；
   - 时间戳；
   - session_id；
   - 原始 source。

2. **AI Patient Session Summary**
   - 对本次患者输入的结构化总结；
   - 与 raw session 关联；
   - 进入患者 Timeline。

医生默认首先看 summary；需要核实时可跳转到原始对话中的具体片段。

---

### 2.2 正式问诊：Doctor / Nurse Consult

正式问诊产生一个新的 **Encounter Event**。

一个 Encounter 可以同时产生多个彼此关联的 Artifact：

- Raw audio / recording；
- Transcript；
- AI Doctor Consult Summary；
- AI Nurse Consult Summary；
- Clinician Note；
- Staff Note；
- Tasks / instructions。

这些内容不是互相覆盖，而是同一个事件的不同 representation。

示例：

```text
Encounter #001 — 2026-08-26 10:00
│
├── Raw Recording
├── Transcript
├── AI Doctor Consult Summary
└── Clinician Note
```

AI summary 只负责描述和整理；**Clinician Note 才代表医生正式的 clinical assessment / plan**。

---

### 2.3 离院后：Patient Follow-up

患者离院后，在 Patient View 中看到：

- 当前 care plan；
- 自己需要完成的事项；
- follow-up 时间；
- patient-facing instructions；
- 必要风险提醒。

患者仍然可以继续与 AI 交流并报告恢复情况。

新的 Patient-AI follow-up 会再次产生：

- Raw session；
- AI follow-up summary；
- 新 Timeline Event。

医生之后再次打开页面时，应能从 Glance View 快速看到状态变化，例如：

- Headache 7/10 → 3/10；
- Nausea persists；
- BP still elevated；
- Blood test pending；
- Follow-up due tomorrow。

这一过程循环，直到该 care episode 结束。

---

## 3. 信息架构

### 3.1 Timeline 是主轴，但不是唯一物理存储

系统在产品语义上使用一条统一的 **Longitudinal Timeline** 组织患者历史。

Timeline 展示现实世界中发生的 Event：

```text
2025-04-15  Primary Care Review（初次头痛主诉，历史事件）
2026-02-06  Medication Review（历史事件）
2026-08-20  Patient AI Pre-consult（症状加重，新的 care episode）
2026-08-21  Nurse Consultation
2026-08-21  Doctor Consultation
2026-08-24  Patient Follow-up
2026-08-29  Doctor Review
```

但并不意味着所有数据都必须塞在同一张数据库表里。

底层可以分别存在：

- events
- artifacts
- sessions
- transcripts
- clinician_notes
- comments
- versions
- highlights
- tasks
- audit_logs

Timeline 是信息组织主轴，而不是物理数据库结构的限制。

---

### 3.2 三层核心模型

#### Event

代表现实中发生的一件事情，例如：

- patient_ai_preconsult
- nurse_consult
- doctor_consult
- patient_followup
- doctor_review

#### Artifact

代表该 Event 产生的内容，例如：

- raw_conversation
- recording
- transcript
- ai_summary
- clinician_note
- staff_note
- patient_instruction

#### Span

代表 Artifact 内部的具体片段，例如：

- transcript 第 14 段；
- AI summary 第 2 条；
- clinician note 的 Assessment section；
- 录音 08:31–08:47。

推荐的关系：

```text
Patient
  ↓
Optional Care Episode（可选的纵向分组，例如一次持续数周的 headache workup）
  ↓
Event
  ↓
Artifact
  ↓
Span
```

#### 多尺度 longitudinal 时间模型（设计原则）

> The patient record is a multi-scale longitudinal structure. The main Timeline organizes real-world clinical Events, while each Event preserves the chronological lifecycle of its artifacts, collaboration, tasks, revisions, and provenance.

- `Event` 仍然是主 Timeline 的核心展示单位；`Care Episode` 只是可选的上层 grouping，不得因此强制扩大当前 MVP；
- 一个 Event 内部按时间保留完整生命周期：raw consult / transcript、AI summary、clinician note、staff/nurse supplement、comments / thread、tasks、revisions / revert、later review actions；
- 明确区分两类时间：
  - `event_time / started_at / ended_at`：现实医疗事件何时发生；
  - `created_at / updated_at`：围绕该事件的信息何时产生或修改；
- 后续修改仍属于原 Event，不应因为修改发生在另一天就被错误展示为新的医疗事件；
- UI 使用 progressive disclosure，而不是无限嵌套 Timeline：
  - longitudinal history / episode → Event detail → Artifact / thread / revision detail → provenance source span；
- 数据模型可以支持更细粒度时间结构，但 UI 不得把所有 audit / activity 全部 flatten 到患者主 Timeline。

---

### 3.3 Metadata / ID / Provenance

每条核心内容至少需要明确：

- patient_id
- event_id
- artifact_id
- author_role
- author_id
- timestamp
- type
- tags
- risk_level
- version
- provenance_pointer

我们使用三个概念区分不同需求：

- **Metadata / Type**：它是什么；
- **Reference / ID**：它在哪里；
- **Provenance Pointer**：这条信息究竟来源于哪里。

例如 Glance View 上的一条信息：

```text
"Headache frequency increased significantly over 2 weeks"
```

理想 provenance chain：

```text
Glance Highlight
    ↓
AI Summary
    ↓
Patient AI Session
    ↓
Exact source span
    ↓
Patient original message
```

医生应能从摘要直接跳到原始证据，而不是只能看到 AI 的二次描述。

### 3.4 与 Candidate Brief 的术语映射（Brief `Entry` → 内部模型）

内部模型使用比 Brief 更细的粒度，**不改回粗粒度 `Entry`**。最终 Technical Brief 必须显式展示以下映射，让评委能直接对应 Brief 要求的 schema（Entries ↔ Comments ↔ Versions ↔ Highlights ↔ Provenance ↔ AI_Scribed_Notes）：

```text
Brief "Entry"                    → 内部 Event（现实医疗事件）+ 其 Artifacts（并行 representation）
Brief AI-scribed note / Entry     → AI-summary Artifact（author_role = system）
Brief "exact source" / source 消息 → 内部 Span（Artifact 内的具体来源位置）
Brief Comments / Thread           → 内部 Comment（挂载在 Artifact / Event 上）
Brief Versions / Revision         → 内部 Version（可编辑 Artifact 的 snapshot / diff）
Brief Highlights                  → 内部 Highlight（指向 Artifact + Span）
Brief Provenance pointer          → provenance_pointer = Event → Artifact → Span
```

---

## 4. 三个核心视图

### 4.1 Timeline View

回答：

> 这个患者从过去到现在发生过什么？

可以按照 Event 展示，并允许展开查看 Artifact。

---

### 4.2 Glance View

回答：

> 医生现在只有 10 秒，最应该注意什么？

Glance View 不是新的事实库，而是对 Timeline 和当前任务状态的动态投影。

优先显示：

- 当前高风险问题；
- 最近明显变化；
- unresolved tasks；
- clinician-confirmed items；
- medications / allergies / chief complaint；
- follow-up / action required。

每条 highlight 都必须：

- 有 risk_reason；
- 有 provenance；
- 可以 accept / reject / pin；
- 可以回到 source。

---

### 4.3 Patient View

回答：

> 作为患者，我现在应该知道什么、做什么、反馈什么？

Patient View 不是完整医生视图的复制。

患者可以看：

- patient-facing summaries；
- care instructions；
- upcoming tasks；
- follow-up steps；
- recovery guidance。

患者不能看：

- internal clinician comments；
- internal staff comments；
- raw AI-scribed notes；
- 其他不应暴露的内部 clinical reasoning。

**实现（M6 + D2）**：patient 角色登录后进入独立的 `PatientViewPage`（`frontend/src/pages/PatientViewPage.tsx`），不是临床工作区的删减版。唯一聚合端点 `GET /api/patients/{id}/patient-view`（`backend/app/api/patient_view.py`）只读取 clinician-authored `patient_instruction` 与本人 patient-visible assigned Task；不调用 LLM、不从 clinician note 猜行动、不复制内部 clinical content。

产品导航严格为四区：

1. **Today** —— 最新明确 patient instruction、next follow-up、当前未终结 Task；
2. **Care Plan** —— `open | in_progress | reported_done | completed` 分组，患者只能 Start/Report done；`reported_done` 明确显示等待诊所确认；
3. **Check-in** —— 提交前说明、sending/error/retry 状态，原始 patient conversation 先落库；不直接修改 note 或 Task；
4. **Visit Summaries** —— 仅 patient-facing instructions，按 `Event.started_at` 倒序。

服务端合同由 `tests/test_patient_view.py` 与 `tests/test_patient_task_projection.py` 锁定：response schema `extra=forbid`，Task 只返回 `task_id/title/status/due_at/updated_at/reported_done_at/completed_at/patient_visible`；不返回 description、assignee、Artifact/Span、AuditLog、importance score 或 clinical risk reason。`sessions` 仍只含本人的 patient session Event。跨 clinic/非本人使用统一 404，匿名 401，同 scope 非 patient 403。

### 4.4 Care Tasks（D2）

Task 是一等实体，不是 Comment、Highlight 或 pending 文本。最小 API：

```text
POST /api/events/{event_id}/tasks
GET  /api/patients/{patient_id}/tasks
POST /api/tasks/{task_id}/transition
GET  /api/tasks/{task_id}/provenance
```

Task 必须有 origin Event；Artifact/Span provenance 可选但必须成对并精确解析。transition 接收 `expected_status`，以原子条件更新实现 deterministic 409。患者只能推进本人、patient-visible、assigned-patient Task 到 `in_progress|reported_done`；只有 staff/clinician 可将 `reported_done` 确认为 `completed` 或取消未终结 Task。终态不可恢复。create/transition/conflict 进入 metadata-only AuditLog。

`unresolved_task` 不再是 seed 常量。Task↔Glance 映射是**显式的一对一关系**：`Highlight.task_id` 使用 Task FK + unique constraint；Task 创建时仅以条件 UPDATE/CAS 采纳 patient/event/source_artifact/source_span 完全匹配、未占用且非 rejected 的 task Highlight，竞争失败或不匹配则创建专属行。Event-only Task 不误伤同 Event 无关 Highlight；`recompute_task_highlights` 只更新对应 `task_id`，completed/cancelled 清除 unresolved 权重并为专属行写入准确终态文案。精确 provenance 只有用户**明确选择 quote 并确认**后才保存，否则为 Event-level；Glance 的 Open Task 定位到具体 Task。`resolve_exact_span` 对任意异常结构 fail closed（422/404，绝不 500）。clinician/staff 共用 clinic shell 的 `Tasks` tab；没有 Nurse Workspace、假 appointment 或 assignment 状态。

---

### 4.5 Clinician New Consult + Transcript Reliability（Phase C + D3）

> 状态：**Phase C、M7 与 D3 Complete。** D3 frozen corpus、runtime baseline 与复现命令见 `backend/docs/transcript_reliability_baseline.md`。

系统没有另建 transcript 数据孤岛，而是在现有 Event / Artifact / AI / provenance / comment 能力上完成医生端真实工作流：

```text
Clinician Workspace
→ New Consult
→ new Doctor Consult Event
→ Paste raw transcript
→ deterministic normalization preview（不持久化、不调用 LLM）
→ Review / resolve unknown / split / merge
→ Confirm canonical Transcript
→ AI Doctor Summary + Highlights
→ Event Detail / exact source
→ Clinician Note / Comment
→ Timeline + Glance refresh
```

`New Consult` 的语义是创建主 Timeline 上新的 `doctor_consult` Event，不再把输入写入固定的 demo Event。

同一次现实到院允许在 UI 中显示为一个 `Clinic Visit`：

```text
Clinic Visit（相同且非空 encounter_id）
  ├─ Nurse Consult Event
  └─ Doctor Consult Event
```

Nurse/Doctor Event、Artifact、作者和权限始终独立。系统不得因为两个 Event 发生在同一天就自动合并。C1 只增加 optional `Event.encounter_id` 字符串，不新增 Encounter 表。

输入严格限定为 manual text；不接受 audio、ASR、OCR 或 EHR import：

```text
DOCTOR: How has your headache changed?
PATIENT: It is better, but I still feel nauseous in the morning.
```

- normalize 支持冻结的 `DOCTOR/PATIENT`、大小写与 `Dr/Pt` 映射、合理 continuation；
- preview 返回 `speaker_candidate|text|source_start|source_end|confidence_marker|issues`；
- `ACCEPT` 仍需 review；`NEEDS_REVIEW` 必须人工消除 unknown/empty；`REJECT` 不可 confirm；
- unknown 永不默认成 doctor/patient；prompt injection/JSON/Markdown 只作 transcript 内容；
- raw input 超过 4096 UTF-8 bytes 返回 413；segment >4000 chars 或 >500 segments 显式 422，不截断；
- confirm 才产生连续 0-based `doctor|patient` canonical `segments[]`；
- 无时间戳时不生成时间戳；
- raw Transcript 先保存且不可覆盖；
- AI Summary 独立保存为 system Artifact；
- 正式 assessment/plan 只能由 clinician-owned note 承载；
- 修正或澄清通过 Comment + Clinician Note，不改写 raw source。

**C1 已实现的 API handoff：**

```text
POST /api/patients/{patient_id}/doctor-consults
POST /api/transcripts/normalize                 # clinician-only；无 DB patient read / 无持久化 / 无 LLM
GET  /api/me
GET  /api/patients
GET  /api/patients/{patient_id}/events   # Event 含 encounter_id
```

Doctor Consult 请求为 strict `consult_id + ingestion_key + started_at/ended_at + content.segments[]`；segment 必须从 0 连续编号，speaker 仅 `doctor|patient`，未知字段/空文本/时间倒置均返回 422。响应显式返回新 Event、encounter、raw/summary/highlight IDs、`generation_method/degraded/fallback_reason` 和 replay 状态。Event + immutable Transcript 先 commit，再复用唯一 `LLMClient` pipeline；相同 consult/ingestion 重放不重复创建数据。

Phase C 两张任务卡均已完成：

1. `Task_Card/C1_Task_Card.md`：Encounter/Transcript schema、clinician-only Doctor Consult endpoint、raw-first/AI/provenance/RBAC 测试；
2. `Task_Card/C2_Task_Card.md`：三栏 Clinician Shell、New Consult UI、Clinic Visit/Timeline master-detail、Source Viewer、Comment/Revision/Audit 集成。

**C2 + D2 实现**：clinician/staff 登录后进入同一 factual Clinic dashboard，可从左栏 `Clinic Patients` 搜索/切换患者；产品 shell 为左侧 identity/directory、中间 `Glance | Timeline | Notes | Tasks`、右侧 Source/Comments/Versions/Audit。staff 权限由 backend RBAC 裁剪且不能 New Consult。patientId、role 与 session 都是 remount boundary；patient 仍只挂载独立 `PatientViewPage`。

`New Consult` 已是 `Paste transcript → Review segments → Confirm and process` 三步流程。原文与 preview 并排；unknown 明显阻断；speaker/text 可修正，segment 可拆分/合并且 index 自动重排。patient/session change 清除 raw draft、preview、operation identity 和 pending response。提交保留 stable consult/ingestion identity，成功后进入新 Event Detail，并明确显示 raw saved、AI generated 或 deterministic fallback。Timeline 只按非空相同 `encounter_id` 组成 `Clinic Visit`；Event Detail 将 Transcript/AI Summary/Clinician Note 与 Comment/Revision/Audit 保持为 Event 内 lifecycle，不制造新医疗 Event。

D3 frozen evaluation 包含 40 个 synthetic cases（development 26 / frozen_holdout 14）。normalizer 在首次 holdout 前以 SHA-256 冻结；holdout outcome 14/14、speaker 12/12、ambiguous blocking 8/8，silent invention/truncation 为 0。frozen runner **不调用 provider/network**；provider 层明确 `NOT_RUN`，deterministic fallback 单独报告（development exact entity precision 0.888889 / recall 0.571429，task precision 1.0 / recall 0.5）。不得把两层合并为一个成绩。

仍明确后置：独立 Nurse Workspace、Nurse input、录音/ASR、外部 dataset ingestion、复杂 care-team assignment、appointment/billing/notification。Phase C、M7、D1、D2、D3、D4 Exit Gate 已通过；D5 未开始。

---

## 5. AI 的职责边界

AI 不应该拥有唯一的 clinical authority。

### 5.1 LLM 适合负责

- 非结构化文本理解；
- symptom / medication / task / risk candidate extraction；
- patient-facing summary；
- AI scribe summary；
- transcript summarization；
- candidate highlight generation；
- provenance linking suggestions。

### 5.2 不应该完全交给 LLM 的部分

Glance View 排序不能只依赖：

> “让大模型判断最重要的五件事。”

第一版应使用透明、可解释的 importance logic。

概念示例：

```text
importance_score =
    recency
  + clinical_risk
  + unresolved_task
  + clinician_confirmed
  + symptom_change
  + repeated_mentions
  - stale_information
  - resolved_task
```

初期可以完全 rule-based。

---

## 6. Self-Learning Importance

当前没有真实 clinician interaction dataset，因此 MVP **不需要先训练模型**。

更合理的路线：

### Phase 1 — 可运行原型

- LLM extraction；
- rule-based ranking；
- synthetic data；
- clinician accept / reject / pin / edit。

### Phase 2 — Adaptive weights

记录医生行为：

- accept；
- reject；
- pin；
- edit；
- comment。

然后简单更新 importance feature 权重。

例如：

```text
pin unresolved_task
→ unresolved_task_weight + 0.1
```

这已经可以展示“系统会学习”。

### Phase 3 — Learned Ranking

真实交互数据足够后，再考虑：

- Logistic Regression；
- GBDT；
- small MLP；
- Learning-to-Rank model。

不要为了“有模型”而对 synthetic labels 做无意义 fine-tuning。

---

## 7. RBAC

最低角色：

- Patient
- Staff
- Clinician
- Admin

核心原则：

- Patient 只能查看 patient-facing information；
- Staff 不得覆盖 clinician notes；
- Clinician 不得覆盖 staff notes；
- Clinician 可以查看 staff notes 和 AI-scribed notes；
- 访问必须 clinic-scoped；
- 权限必须 server-side enforced；
- UI 隐藏按钮不能作为安全控制。

**D1 身份进入（2026-08-26）**：产品模式下的身份完全来自 server-side session
（HttpOnly cookie），不再接受 `X-User-Id/X-Role` 头。见 §15.4 Demo auth 与生产身份边界。

---

## 8. Revision / Collaboration

系统至少应支持：

- note edits；
- version increment；
- full revision history（full snapshots 或 diffs，架构选择）；
- revert 到任意历史版本；
- diff / "view changes since X"（查看自指定版本以来的变更）；
- audit metadata；
- comments；
- resolve / unresolve；
- optional @mention；
- concurrent editing 不互相覆盖。

同一区域冲突必须有 deterministic resolution strategy。

---

## 9. Privacy / Security

当前 challenge 使用 synthetic data。

即使是 synthetic prototype，也必须体现真实系统的安全架构：

- PHI redaction before LLM；
- redaction names；
- redaction IC / ID numbers；
- redaction phone numbers；
- TLS in transit；
- encryption at rest；
- clean logs；
- no raw sensitive content in logs。

---

## 10. 性能

Consult Glance View：

- warm path P95 ≤ 300 ms；
- 需要说明测量方法或近似方法。

因此 Glance View 不应在每次页面加载时重新把全部病历扔给 LLM。

更合理的设计：

- Event 创建后异步生成 candidate highlights；
- importance score 预计算或增量更新；
- 页面读取预计算结果。

### 10.1 M7 实测基线（`backend/docs/perf_baseline.md`）

`backend/scripts/measure_glance.py` 在一次性 reseed 的 SQLite 上，对 glance / events / patient-view 三个读端点分别采样 100 次（前 10 次 warm-up 丢弃），输出 Layer A（TestClient in-process，应用逻辑 + SQLite 查询）与 Layer B（真实 uvicorn + 本地 HTTP 往返）两层 P50/P95/Mean/Max。

最新一轮：Layer A Glance P95 ≈ **3.8 ms**（远低于 300 ms），events ≈ 6.7 ms，patient-view ≈ 5.0 ms；Layer B 各端点仅增加 ~1 ms 本地往返/序列化开销。排序确定性（`highlight_id` tiebreak）、写后读一致与 highlight 状态并发乐观锁均由 `tests/test_glance_ordering.py` 锁定；读路径零-LLM 由 `tests/test_read_path_no_llm.py`（transitive import 守卫）证明。

> 诚实条款：单用户本地 SQLite 数字只证明 warm read path 不含同步 LLM / 全量历史扫描，不代表分布式或生产级容量。

---

## 11. MVP 构建优先级

当前目标不是训练出最强模型，而是先构建一个 **安全、完整、可以演示真实工作流的运行系统**。

优先级：

1. Event / Artifact / Provenance 数据模型；
2. Longitudinal Timeline；
3. Glance View；
4. Patient View；
5. RBAC；
6. AI Scribe / AI Patient Summary；
7. Revision + audit；
8. Required tests；
9. Adaptive importance bonus；
10. Ambient voice capture bonus。

不要在核心链路完成前投入大量时间：

- fine-tuning；
- complex agent framework；
- advanced voice pipeline；
- sophisticated learning model；
- generic UI polish。

---

## 12. Required Tests

至少实现：

- `test_rbac_scope.py`
- `test_revision_history.py`
- `test_highlight_provenance.py`
- `test_concurrent_edits.py`
- `test_task_lifecycle.py`
- `test_task_rbac_scope.py`
- `test_task_provenance.py`
- `test_patient_task_projection.py`
- `test_task_glance_integration.py`

Bonus：

- `test_self_learning_importance.py`

这些测试不是附属内容，而是 MVP 的组成部分。

---

## 13. 最终 Demo 应展示的故事

### Scenario A — Glance + Provenance

- 打开患者页面；
- 10 秒内理解当前问题；
- 点击某条 highlight；
- 跳回 AI summary；
- 再查看原始 source/span。

### Scenario B — Collaboration + Audit + Importance Learning

- Staff 添加 note，并添加一条带 `@clinician` mention 的 comment；
- Clinician 在一条 AI-scribed note 中手动 highlight 某个短语，并编辑 patient plan 的某个 section；
- 该人工 highlight / pin / edit 行为被记录为 self-learning importance 的 feedback signal；
- 展示 revision history + diff（view changes since X）；
- revert 到之前版本；
- 展示 audit trail。

### Scenario C — Longitudinal Care

- 展示跨日期、跨月份的 Event（至少包含 1–2 条较早历史事件，例如 2025-04-15 的初次头痛就诊与 2026-02-06 的用药复查，再连接到 2026-08 的当前 care episode）；
- patient follow-up；
- status change；
- importance ranking；
- unresolved task；
- clinician-confirmed information。

---

## 14. 当前项目判断

现阶段没有真实临床训练数据，因此第一目标不是“训练模型”，而是：

> **创造一套完整可运行的信息闭环，并使用 synthetic data 验证产品、权限、provenance、AI extraction 和 importance logic。**

如果这个闭环能够成立，那么后续真实 clinician interaction data 才有意义；届时再讨论 learned ranking、个性化 prioritization 或 post-training。


---

## 15. Setup / Run / Tests

**技术栈（已冻结，2026-08-25）**：

- 后端：Python 3.13 + FastAPI + Uvicorn + SQLAlchemy 2.x + SQLite + Pydantic v2
- 前端：React 18 + Vite + TypeScript（SPA，调用 FastAPI JSON API）
- LLM：DeepSeek（经 anthropic SDK，base_url / key 用环境变量注入）；deterministic stub 兜底，demo / 测试不依赖外部 API 实时可用
- 测试：pytest（required tests 均为 `.py`）
- 身份：D1 真实 Demo 身份流程（invite → register → login → HttpOnly session → logout）；密码 Argon2id 哈希，invite/session token 只存 SHA-256 哈希；TLS in transit 与 encryption at rest 是 D5 的部署证据目标（当前不做字段级加密声明）
- 角色：产品模式不再接受 `X-User-Id/X-Role` 头；RBAC 服务端强制

### 目录结构

```text
backend/    FastAPI + SQLAlchemy + SQLite（app/ 代码，seed/ fixture，tests/ pytest）
frontend/   Vite + React 18 + TS（clinician/staff 共用三栏 clinic shell + 独立四区 PatientViewPage）
```

### Demo data（canonical fixture）

一条跨 15 个月的纵向病历（`backend/seed/fixture.py` 是唯一事实源），reseed 命令见上（`python -m seed.seed`）：

```text
2025-04-15  historical_review   初次头痛评估（once weekly，无 red flag）
2026-02-06  historical_review   药物复查（频率上升→启动 propranolol 20 mg daily）
2026-08-20  patient_ai_preconsult  频率 near-daily、严重度 7/10、晨起恶心
2026-08-21  nurse_consult          BP 158/96 升高
2026-08-21  doctor_consult         blood test 开具、follow-up 预约
2026-08-24  patient_followup       严重度降至 3/10、恶心持续、blood test pending
2026-08-26  clinician_review       更新计划：继续 propranolol、催 blood test 结果
```

- 两个历史事件与当前 episode 形成真实跨年/跨月呼应；历史 highlight 低分（无 recency），自然让位于当前 episode。
- C1 已为 2026-08-21 Nurse/Doctor Consult 增加同一显式 `encounter_id=enc_visit_20260821`，使 C2 可将它们显示为一个 `Clinic Visit`；底层仍是两个独立 Event，且不得按日期自动分组。
- `recency` 由 seed 冻结的 `as_of=2026-08-26 12:00` 计算；`repeated_mentions` 按相同 `entity_key` 的 distinct Event 分组（`symptom:headache frequency` 跨 3 个事件、`task:blood test` 跨 2 个事件），新旧两侧分数都重算。
- D2 fixture 另含真实 Task 故事：blood-test Task 当前 `open`；symptom-diary Task 保留 `open -> reported_done -> completed` 的 metadata-only AuditLog 历史。
- **Synthea 决策：不采用**。手写 canonical fixture 已完全满足 Candidate Brief 的 Synthetic Data Only 要求，未引入 FHIR/Synthea 以避免反向重构内部模型。

### 安装与启动（M1/M2 已验证）

```bash
# 后端（Python 3.13+）
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt    # Windows；Linux/macOS 用 .venv/bin/pip

# seed synthetic demo data（可重复执行：先清库再灌入）
.venv/Scripts/python.exe -m seed.seed

# 启动后端（默认 http://localhost:8000）
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

```bash
# 前端（Node 18+）
cd frontend
npm install
npm run dev -- --host --port 5173    # Vite dev server，代理 /api 到 :8000
```

### 运行自动化测试

```bash
cd backend
.venv/Scripts/python.exe -m pytest        # 覆盖第 12 节 required micro-tests
.venv/Scripts/python.exe scripts/evaluate_transcripts.py --validate-corpus
.venv/Scripts/python.exe scripts/evaluate_transcripts.py --evaluate-runtime
.venv/Scripts/python.exe -B scripts/evaluate_copilot.py
```

> 当前进度：M1–M7、Phase C（C1+C2）、**D1 Identity**、**D2 Care Tasks + Patient Experience**、**D3 Transcript Reliability** 与审查修复后的 **D4 Evidence-Bound Clinician Copilot** 已落地。全量 backend collection **316**；强化 frozen Copilot mock eval 见 `backend/evals/copilot/`，其 `COPILOT_READ_PATH` latency 与 Glance P95 分开报告。剩余 Phase D 工作：D5 TLS/at-rest 与跨角色集成。

架构约定（记录确切位置，随阶段更新）：

- **PHI redaction 发生位置**：`backend/app/redaction.py`（`redact_content` / `restore_placeholders`）。在 `backend/app/ai_pipeline.py` 中，所有文本在进入 provider 之前先经 `redact_content`（姓名 / IC·ID / 手机号）；`placeholder_mapping` 仅存在于单次 pipeline 内存，不进 LLM / 日志 / DB。AI summary 与 highlights 由 `persist_derived` 原子写入（raw source 先落库、永不被覆盖）。
- **RBAC 强制点**：所有权限判断在 server-side 完成，集中在 `backend/app/authz.py`（`authorize(action, resource)` + `PERMISSIONS` 矩阵）与 `backend/app/role_context.py`（DB 为身份/角色唯一权威，`X-Role` 只能作 demo 一致性断言，不一致即拒绝，不可提权）。每个端点经 `require_auth`（401）+ `authorize`（同院无权限 403 / 跨院或非本人 404）；不存在、跨院和非本人资源使用相同 404 body，避免存在性探测。UI 只做展示裁剪，不作为安全边界，角色切换会重新挂载整个 patient workspace 以清除敏感状态。
- **LLM 客户端出口**：`backend/app/llm_client.py`（`LLMClient` protocol）是唯一 provider 出口，只能接收 `RedactedContent`。实际仅支持 `mock`（无 key、确定性）与 `deepseek`（live adapter）两个 provider；`NANTINGALE_LLM_PROVIDER` 默认 `deepseek`。`deepseek` 缺 key / provider 出错 / schema 非法时明确降级到 deterministic fallback；key 只从环境变量读取，永不打印/入库。
- **D4 Copilot 边界**：`POST /api/patients/{patient_id}/copilot/query` 只对同 clinic 的 clinician 开放。Provider 只接收最多 12 个脱敏 exact-span cards，且不拥有 draft type/Event/patient/visibility/endpoint；AI Summary 必须继续解析到 raw source 才能成为 source fact。`Find evidence` 先在当前授权 patient 全历史做服务器端匹配，再限制 provider egress；`What changed` 返回两个 Event source facts + 显式 comparison inference。Copilot 不直接写记录；可编辑 Preview 由服务端签发 5 分钟 HMAC token，绑定 actor/clinic/patient/Event/type/evidence，既有 Note/Task API 验证成功后才记录 `draft_origin=copilot`。Patient instruction 必须改成有效 patient-facing 内容；Patient View 从不加载 Copilot。

### Demo auth（D1）：Invite → Register → Login → Session → Logout

产品模式的进入流程是真实身份流程（`backend/app/api/auth.py` + `backend/app/auth_security.py`）：

```text
Admin 创建 clinic invite（一次性链接，不发送真实邮件）
  -> 被邀请者打开 /register?token=…（只预览掩码邮箱/角色/clinic，无存在性枚举）
  -> 注册：invite 消耗 + User + UserCredential 在同一 transaction；
     注册者不能覆盖 invite 的 role/clinic/patient binding；
     patient invite 只能把新登录绑定到既有 Patient 记录，绝不创建第二条纵向记录
  -> 登录：Argon2id 校验（argon2-cffi），未知邮箱/错误密码/禁用账号返回同一 401 body
  -> 会话：256-bit 随机 token 只存 SHA-256 哈希，HttpOnly + SameSite=Lax cookie
     （部署 HTTPS 后设 NANTINGALE_SECURE_COOKIES=true 加 Secure）
  -> 每次请求都重新解析 cookie → DB User（role/clinic/patient 全来自 DB）
  -> 登出：条件 UPDATE 原子 revoke，客户端 cookie 同时清除
```

内置 Demo 账号（synthetic，密码相同 `nightingale-demo`；见 `backend/seed/fixture.py`）：

| 角色 | 邮箱 | 登录后进入 |
|---|---|---|
| Clinician | doctor@demo.clinic | 三栏 Clinician Workspace |
| Staff | staff@demo.clinic | 共用 clinic shell（RBAC 裁剪，含 Care Tasks） |
| Patient | alice@demo.clinic | 独立四区 Patient View（pat_001） |
| Admin | admin@demo.clinic | PatientPage + Invite 管理页（`/admin/invites`） |

相关环境变量（后端）：

```text
NANTINGALE_DEMO_AUTH=true          # 显式开启 legacy X-User-Id/X-Role 头模式（默认关闭；测试/开发专用）
NANTINGALE_SESSION_TTL_HOURS=12    # session 有效期（默认 12 小时）
NANTINGALE_INVITE_TTL_DAYS=7       # invite 有效期（默认 7 天）
NANTINGALE_SECURE_COOKIES=true     # HTTPS 部署后开启 cookie Secure 标志
NANTINGALE_COPILOT_CONFIRMATION_SECRET=<shared secret>  # 多 worker 必配；单进程未配置时使用进程随机 secret
```

前端环境变量（`frontend/.env`）：

```text
VITE_DEMO_AUTH=true                # 前端与后端 demo 模式需同时开启；默认关闭
```

**Demo auth 与生产身份验证的边界（诚实声明）**：

- 密码哈希（Argon2id）、token 哈希、server-side session、revoke/expiry、cookie 标志、单次 invite、注册绑定和 AuditLog 都是真实实现，不以明文落库/入日志；
- 属于 Demo 的：不发真实邮件/SMS（admin 复制一次性链接）、无 MFA/SSO/OAuth、无 forgot-password（可 admin 重新邀请）、无跨 clinic membership、无生产 KYC/执照校验；
- 未做：TLS 与 at-rest 加密的部署证据（D5 范围）、生产 PostgreSQL、真实 PHI。

### DeepSeek API key 放在哪里

不要把 key 写入源码、JSON、测试 fixture 或提交到 Git。后端按顺序从环境变量 `DEEPSEEK_API_KEY` → `Natingale_API_KEY` 读取（当前 Windows 用户级已设置的是 `Natingale_API_KEY`，二者皆可）。Windows PowerShell 中可只为当前终端设置：

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API key"
$env:NANTINGALE_LLM_PROVIDER = "deepseek"
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

若希望以后新开的终端也能读取，可写入当前 Windows 用户的环境变量（执行后需**重新打开终端**，已运行的进程不会自动刷新）：

```powershell
[Environment]::SetEnvironmentVariable("DEEPSEEK_API_KEY", "你的 DeepSeek API key", "User")
```

项目 `.gitignore` 已排除 `.env`，但当前后端没有加载 `.env` 文件，因此仅创建 `.env` **不会生效**。`deepseek-v4-flash` 曾于 2026-08-26 完成一次无 PHI smoke check（记录在 `backend/docs/gate0_provider_status.md`）；live adapter 在配置 key 后可用，但无 key 或调用失败时仍会明确降级到 deterministic fallback。

---

## 16. Bonus: Hybrid Storage / Data Decay

> 明确标记为 Bonus，不改变第 11 节的 MVP 优先级。

设计方向：

- recent / clinically important information 保持高可访问性（热路径，直接参与 Glance 计算）；
- older low-value data 可以 summary / compress / archive（冷路径）；
- raw source 与 provenance chain **不得因 compression 丢失**——压缩的是展示与索引成本，不是可追溯性；
- clinician-confirmed / unresolved / high-risk information 不参与简单 decay；
- data decay 只降低旧数据的呈现优先级，不得删除仍被 provenance 引用的 source span。

---

## 17. Bonus: Ambient Voice Capture

> 明确标记为 Bonus，不要求当前优先实现。

边界约束：

- **Patient voice capture**：仅 patient view 可用。PWA on mobile；录音 → redact PHI before LLM → transcribe → 提取结构化事实 → 生成 patient consult session summary。
- **Clinical / staff voice capture**：仅 clinical view 可用。PWA on mobile 或 laptop。

架构描述至少覆盖：

- speaker-labelled transcript；
- timestamps；
- confidence markers；
- code-switching support；
- clinical summary；
- provenance back to source segments。

Extra bonus（加分项，非当前优先级）：noisy environment、diarization、overlap handling、multilingual medical terminology、multi-device capture。
