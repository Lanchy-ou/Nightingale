# C1 任务卡 — Encounter + Manual Doctor Consult Backend

> 状态：**COMPLETE（2026-08-26）**
> 前置基线：M1–M6 Complete；133 个 pytest 通过。
> 完成验证：156 个 pytest 通过；frontend production build 通过。
> 后续：进入 `C2 — Clinician Workspace + Consult Review UX`。
> 目标：为医生端 `New Consult` 冻结数据合同，并在现有 Event / Artifact / AI pipeline 上完成一条安全、幂等、可追溯的 Doctor Consult 后端纵向链路。

---

## 1. 本卡冻结的产品决定

1. `New Consult` 是操作入口；提交成功后创建一个新的 `doctor_consult` Event，并出现在主 Timeline。
2. 当前唯一新增输入方式是**手动粘贴 speaker-labelled 文字 transcript**。录音、音频上传、ASR、diarization、OCR、外部 EHR 导入全部后置。
3. 同一次现实到院可在 UI 中组成一个 `Clinic Visit`，但底层 `nurse_consult` 与 `doctor_consult` 仍是独立 Event。
4. `Event` 新增可选 `encounter_id` 字符串；只有相同且非空的 `encounter_id` 才能被 UI 分组。不得只按日期自动合并。
5. Doctor-only `New Consult` 创建新的 `encounter_id`，其 Clinic Visit 初始只有一个 Doctor Consult Event；未来 Nurse workflow 可以显式加入同一 encounter，但不在本卡实现。
6. Transcript 是不可覆盖的 raw source；AI Doctor Summary 是 `author_role=system` 的独立 Artifact；正式 assessment/plan 必须写入 clinician-owned `clinician_note`。
7. 不导入公开数据集作为 canonical data。可参考 PriMock57 的对话结构，但 Demo transcript 必须手写并与 `backend/seed/fixture.py` 的 FACTS 一致。

```text
Clinic Visit（encounter_id，可只有一个 Event）
  ├─ Nurse Consult Event（已有/未来）
  └─ Doctor Consult Event（New Consult 创建）
       ├─ Transcript Artifact
       ├─ AI Doctor Summary Artifact
       └─ Highlights → exact Transcript spans
```

---

## 2. 范围

### In Scope

- optional `Event.encounter_id` + API response field；
- canonical 2026-08 Doctor Consult synthetic transcript；
- strict transcript request schema；
- clinician-only Doctor Consult create + ingest endpoint；
- stable IDs / namespaced idempotency；
- raw-first persistence；
- 复用现有 redaction、provider/fallback、extraction、conflict、scoring、provenance；
- metadata-only audit；
- clinic-scoped patient list 与 current identity 所需的最小只读 API（供 C2 shell 使用）；
- C1 自动化测试与 README/API 合同说明草稿。

### Out of Scope

- Clinician Shell / New Consult 页面 / Timeline 视觉重构（C2）；
- Nurse `New Consult` endpoint 或 Nurse Workspace；
- 录音、ASR、音频、OCR、外部 EHR、外部 transcript dataset ingestion；
- Task、care-team assignment、正式认证；
- Doctor AI Assistant；
- processing queue / job table；
- Encounter 独立表、Care Episode UI；
- 性能、Bonus、Patient Experience 重构。

---

## 3. 数据合同

### 3.1 Event encounter grouping

在 `backend/app/models.py` 的 `Event` 增加：

```text
encounter_id: string | null
```

同时扩展 `EventOut` 和前端 `Event` 类型（前端使用在 C2）。

规则：

- canonical fixture 中 2026-08-21 的 Nurse/Doctor Consult 共享一个明确 `encounter_id`；
- ungrouped historical review、patient follow-up、clinician review 保持 null；
- 新 Doctor Consult 生成新的 stable encounter id；
- 同一 encounter 内 Event 按 `started_at` 排列；
- Event 内 Artifact lifecycle 仍按 `created_at` 排列；
- 不新建 Encounter 表，不按同日/相邻时间推断 encounter。

### 3.2 Transcript schema

前端 paste 形式（C2 实现）：

```text
DOCTOR: How has your headache changed?
PATIENT: It is better, but I still feel nauseous in the morning.
DOCTOR: Have you completed the blood test?
PATIENT: Not yet.
```

服务端 canonical content：

```text
{
  segments: [
    { index: 0, speaker: "doctor", text: "..." },
    { index: 1, speaker: "patient", text: "..." }
  ]
}
```

冻结验证规则：

- request 和每个 segment 使用 strict Pydantic schema，`extra="forbid"`；
- speaker 只允许 `doctor|patient`；
- index 从 0 开始、连续、唯一；
- text 为 trim 后非空字符串；
- timestamp 当前不要求；没有就不生成；
- 服务端不能信任前端 preview，也不能让 AI 猜 speaker/timestamp；
- Artifact 保存 canonical segments，segment text 不由 AI 改写；
- Transcript Artifact 不可通过 note edit/revert API 修改。

### 3.3 Doctor Consult endpoint

新增：

```text
POST /api/patients/{patient_id}/doctor-consults
```

请求至少包含：

```text
consult_id
ingestion_key
started_at
ended_at?
content.segments[]
```

响应使用专属 schema，至少包含：

```text
event
encounter_id
source_artifact_id
ai_summary_artifact_id
highlight_ids
generation_method
degraded
fallback_reason
idempotent_replay
```

端点顺序：

1. `require_auth`；
2. resolve patient，scope-first authorization；
3. 只允许 clinician 创建 Doctor Consult；同 scope 无权限 403，跨 clinic/不存在统一 404；
4. 校验 `ended_at >= started_at`；
5. 使用 patient + consult_id 派生 stable Event/encounter identity；
6. 创建 `doctor_consult` Event；
7. 创建 `transcript` Artifact（`author_role=system`, `author_id=null`）并先 commit；
8. 调用 `backend/app/api/sources.py` 的现有 `_ingest_common` / `run_pipeline`，不得建立第二个 provider 出口；
9. 原子写入 AI Summary + valid Highlights；
10. 返回显式 generation/fallback 状态。

现有 `POST /api/events/{event_id}/sources` 保留，供既有测试和未来“已有 Event 添加 source”的工作流使用。

---

## 4. 三个工作包

### C1.0 — Baseline + Contract

- 先提交/隔离当前 M6 安全修正和 docs；
- 冻结本卡、synthetic transcript、encounter 规则与 API schema；
- full pytest + frontend type/build baseline。

验证：133+ tests 绿；工作树只含预期 C1 改动；transcript 不新增 fixture FACTS 之外的临床事实。

### C1.1 — Schema + Consult Ingestion

- `Event.encounter_id`、schemas、fixture/reseed；
- Doctor Consult endpoint；
- idempotency、raw-first、AI pipeline reuse、audit；
- clinic patient list/current identity 的最小只读支持。

验证：Event → Transcript → AI Doctor Summary → Highlight → exact span 全链路通过。

### C1.2 — Tests + Contract Handoff

- 新增 `test_doctor_consult_ingestion.py`；
- encounter grouping contract tests；
- immutability/RBAC/idempotency/fallback/provenance regression；
- C2 所需 API/types 契约记录。

验证：C1 自动化硬门全绿，C2 不需要猜测后端行为。

---

## 5. 自动化测试硬门

至少覆盖：

- clinician 创建同 clinic patient Doctor Consult → 200；
- staff/patient/admin 同 scope → 403；跨 clinic/不存在 → 统一 404；匿名 → 401；
- invalid speaker、空 text、非连续 index、unknown key、ended_at < started_at → 422；
- 相同 consult/ingestion key replay 不重复创建 Event/Artifact；
- raw transcript 在 derived processing 前已持久化；
- provider/schema failure 走明确 fallback；
- generated Highlight 的 source pointer 可解析到新 transcript segment；
- Transcript 不可通过 note edit/revert API 修改；
- 2026-08-21 Nurse/Doctor Events 共享明确 encounter；同日但不同 encounter 不合并；
- Patient View、required micro-tests、现有 source ingestion tests 全部回归绿。

---

## 6. Exit Gate — C1 Complete

只有全部满足时才可声明：

> **C1 / Encounter + Manual Doctor Consult Backend Complete**

1. `New Consult` 后端业务调用创建新的 Doctor Consult Event，而非写入固定 Event；
2. Event 带显式 encounter identity，且没有日期推断分组；
3. Transcript schema strict、raw-first、immutable；
4. AI pipeline 只有既有 `LLMClient` 出口；
5. AI Summary/Highlights 独立保存，exact provenance 成立；
6. RBAC/clinic scope/idempotency/fallback/audit 合同被测试锁定；
7. canonical fixture 与 FACTS 一致；
8. full pytest 绿，C2 API handoff 明确。

---

## 7. 完成记录（2026-08-26）

- `Event.encounter_id`、`EventOut` 与 frontend `Event` 类型已落地；08-21 Nurse/Doctor fixture 共享 `enc_visit_20260821`，其余 Event 不做日期推断。
- `POST /api/patients/{patient_id}/doctor-consults` 已实现 stable Event/encounter/source IDs、namespaced idempotency、raw-first commit、既有 `_ingest_common`/`LLMClient` pipeline 复用和 metadata-only audit。
- strict `DoctorTranscriptSegment/Content/DoctorConsultCreate` 与专属 `DoctorConsultOut` 已冻结；手写 `C1_DEMO_DOCTOR_TRANSCRIPT` 与 `FACTS` 一致。
- C2 只读/API handoff 已提供：`GET /api/me`、`GET /api/patients`、Event `encounter_id`、frontend `createDoctorConsult` 类型。
- `backend/tests/test_doctor_consult_ingestion.py` 覆盖 RBAC/scope、422 fail-closed、idempotency、raw-first、fallback、exact provenance、immutability、encounter 和 C2 handoff；全量回归为 **156 passed**。

---

## 8. 停止条件

- 需要让 AI 猜 speaker/timestamp/缺失事实 → 停止并拒绝输入；
- 需要导入公开数据集才能凑 Demo → 停止并使用 hand-written canonical transcript；
- 需要覆盖 raw Transcript 才能“修正”内容 → 停止，留给 C2 Comment + Clinician Note；
- 需要按日期合并 encounter → 停止，要求显式 `encounter_id`；
- 需要新增 ASR/Task/AI Assistant 才能继续 → 越界；
- required tests 或 Patient View leak tests 回归 → 先修复，不进入 C2。
