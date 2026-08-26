# M4 任务卡 — AI Pipeline + Redaction + Deterministic Prioritization

> 对应：`Nightingale_72H_Development_Plan.md` Phase 4（§8）+ `AGENTS.md` M6。
> 截止目标：**Milestone 4 — 最迟 2026-08-27 晚完成 AI vertical slice**。
> 前置状态：M3 已完成（61/61 pytest 绿，RBAC / revision / audit / concurrency / threaded comments 已落地）。
>
> **阶段边界说明**：本任务卡沿用开发计划的 Phase 4 编号，但它不是 `AGENTS.md` 中尚未完成的 Patient View。M4 完成只可声明 **AI Vertical Slice Complete**；Patient View、性能测量、最终 Scenario A/B/C walkthrough 等硬门通过后，才可声明 Core Complete。

---

## 1. 目标与成功定义

在 M1–M3 已冻结的 provenance、storage 和 permission contract 上，让一份**不在 seed 中的新 source**走通：

```text
new raw source
→ persist raw source first
→ redact every LLM-bound text field
→ live/mock LLM summary + candidate extraction
→ restore exact placeholders locally
→ deterministic quote anchoring against raw source
→ bounded clinician-conflict check
→ atomic persist of AI summary + valid highlights
→ precomputed deterministic score
→ Glance + source jump
```

成功必须同时满足：

- raw source 永远先保存，AI 失败不能丢失原始证据；
- LLM 从未收到姓名、IC/ID 或电话号码原文；
- AI summary 是独立 Artifact，绝不覆盖 raw / clinician / staff Artifact；
- AI summary 的 `provenance_pointer` 至少指向本次 Event + raw source Artifact（summary 无单一支持句时不伪造 span）；
- 每条落库 Highlight 都能解析到 raw source 的真实子串；
- fallback 能处理本次新 source，不读取固定 seed candidate；
- pipeline 的 live/mock/fallback 状态在请求后仍可追溯；
- 重试同一 ingestion key 不产生重复 Event / Artifact / Highlight。

---

## 2. 范围

### In Scope

- recursive PHI redaction（姓名 / IC·ID / 手机号）；
- provider-neutral `LLMClient` interface + mock client；DeepSeek adapter 仅在 Gate 0 compatible 后实现；
- 三类 flow：
  - `raw_conversation → ai_patient_session_summary`
  - nurse transcript → `ai_nurse_consult_summary`
  - doctor transcript → `ai_doctor_consult_summary`
- validated structured candidates + normalized entity identity；
- placeholder restore → raw quote deterministic anchoring；
- fixture-independent deterministic fallback；
- bounded clinician-conflict flag（不声称通用临床矛盾检测）；
- source ingestion API、idempotency、RBAC 和事务边界；
- server-computed importance flags + write-time score；
- redaction / three-flow / fallback / idempotency / RBAC / conflict / provenance tests；
- README redaction 入口回填；仅在实际引入依赖后更新 `ATTRIBUTION.txt`。

### Out of Scope（不得顺手实现）

- Patient View 页面与 patient-facing summary 设计；
- Task 表 / assignment / task completion workflow；
- self-learning / adaptive weights；
- performance measurement 或 Glance 优化；
- Synthea / FHIR enrichment；
- Voice capture；
- manual highlight；
- 通用医学 contradiction engine、诊断或自动 clinical authority；
- prompt 多轮调优、RAG、fine-tuning、multi-agent pipeline；
- encryption-at-rest 的生产实现（但本阶段不得新增未加保护的 reversible PHI mapping 存储）。

---

## 3. 开工前 Gate 0 — Provider Protocol

README 当前写有 “DeepSeek 经 anthropic SDK”。实现前必须先做一次**非临床、无 PHI**的最小协议 smoke check，并记录：

```text
provider
endpoint/base_url
request protocol
SDK/package + version（如有）
model
timeout
result = LIVE_VERIFIED | NOT_LIVE_VERIFIED | INCOMPATIBLE
```

规则：

- 在兼容性被证实前，不把某个 SDK 写入 `requirements.txt`；
- 若冻结的 anthropic SDK 路径不兼容，停止 live adapter 工作并报告，不得静默换 SDK / provider；
- mock + deterministic fallback 可继续开发，但最终状态必须诚实标记 `NOT_LIVE_VERIFIED`；
- 没有一次成功的 live smoke evidence，不得声称“真实 DeepSeek 已验证”；
- API key 只从环境变量读取，不打印、不写文件、不进入测试 fixture。

---

## 4. 模块边界

```text
backend/app/
├── redaction.py               # redact_content / restore_placeholders
├── llm_client.py              # LLMClient protocol + provider adapter
├── extraction.py              # Pydantic output schema + normalization
├── deterministic_pipeline.py  # fixture-independent runtime fallback
├── conflicts.py               # bounded, deterministic conflict check
├── ai_pipeline.py             # orchestrate; no HTTP/RBAC logic
└── api/sources.py             # ingestion + authorization + transactions
```

永久纪律：

- `llm_client` 只能接收 `RedactedContent`，不能接收 raw string/dict；
- 所有 provider 调用只有一个出口；禁止其他模块直接调用 SDK/HTTP；
- Glance GET 路径不得 import 或调用 `ai_pipeline`；
- 日志不记录 raw text，也不记录 redacted clinical text；只记录 IDs、耗时、redaction counts、candidate counts、drop/fallback reason；
- M2 的 `backend/seed/highlights.py` 继续只负责 seed，**不得**作为 runtime fallback；
- pipeline 不改变 M1–M3 的 span 结构和 `locate_span` / `extract_text` 语义。

---

## 5. Redaction 与 Raw Span 对齐合同

### 5.1 API

```text
redact_content(content, known_names)
→ RedactionResult(
     redacted_content,
     placeholder_mapping,
     redaction_counts
   )
```

- 递归处理 source content 中的文本叶子，至少覆盖：
  - `segments[*].text`
  - `messages[*].text`
  - 顶层 string sections；
- 保留 message/segment 顺序与 id/index；speaker 只能以 `patient|doctor|nurse|ai` 等角色标签进入 provider，含人名的 speaker label 必须先 normalize/redact；
- `known_names` 来自当前 Patient、同一 Event 的已知 User 名称与结构化 speaker 名称，不从 fixture module 硬编码；
- 这是面向 synthetic MVP 的 deterministic coverage，不冒充通用 name NER；若 source 出现无法归属但疑似姓名的输入，live provider path 必须 fail closed，不能假定“未命中即安全”；
- IC/ID 与 phone 规则必须有边界测试，避免一个值同时被两类 regex 重复替换；
- placeholder 必须稳定、唯一：`[NAME_1]` / `[ID_1]` / `[PHONE_1]`。

### 5.2 Mapping 处理

- `placeholder_mapping` 仅存在于单次 pipeline 内存；
- mapping 不进 LLM、不进日志、不进 DB、不进 AuditLog；
- 允许在 provider 返回后，对 summary/candidate 中**完整且未修改**的 placeholder token 做本地恢复；
- provider 输出未知 placeholder、破损 placeholder 或将 placeholder 拼进其他 token → 输出校验失败并 fallback；
- 落库 generation metadata 只保存 redaction counts，不保存 reversible values。

### 5.3 Quote 锚定顺序

```text
LLM quote over redacted source
→ validate placeholder tokens
→ exact local placeholder restore
→ locate_span(raw_source.content, restored_quote)
→ extract_text(raw_source.content, span) == restored_quote
```

绝不：

- 信任 LLM 返回的 index/offset；
- 对 quote 做 fuzzy matching；
- 在 restore/匹配失败时制造 span；
- 为了通过阈值保留 unresolved candidate。

---

## 6. Extraction Schema

LLM 输出必须通过严格 Pydantic schema；禁止自由形状 JSON 直接落库。

```text
AISummaryResult
  summary: str
  chief_complaint: str | null
  candidates: list[Candidate]

Candidate
  text: str
  quote: str
  risk_reason: str
  entity_type: symptom | medication | allergy | chief_complaint | task | risk
  entity_key: str              # 服务端 normalize 后的稳定 key
  assertion_value: str | null  # normalized value/status/dose/polarity
  explicit_risk: bool
  symptom_change: bool
```

规则：

- `entity_key` 由服务端根据 `entity_type + normalized token` 重新计算，不直接信任 LLM；
- 未识别 entity type / 空 quote / 空 risk_reason / 非法字段 → candidate 丢弃并计数；
- LLM 只建议 `explicit_risk` / `symptom_change`；其余结构性 feature 由服务端计算；
- summary 允许无 candidates；“没有候选”不等于系统错误，但必须记录 `candidate_count=0`。

---

## 7. Runtime Fallback（不得依赖 seed）

`deterministic_pipeline.py` 必须只接收本次 raw source + Event metadata，不能 import：

- `seed.fixture`
- `HIGHLIGHT_CANDIDATES`
- 固定 artifact/event/highlight IDs。

最小 fallback：

- 按原顺序抽取 patient/clinician/nurse 的完整 source sentences；
- 用冻结关键词/正则识别有限的 symptom change、risk、medication、task；
- summary 可为保守的 extractive summary；
- candidate quote 必须是 source 中逐字子串；
- 没有受支持模式时允许 `0 highlights`，不得编造内容。

Fallback 触发：

- provider missing / timeout / network error；
- provider protocol error；
- JSON/schema invalid；
- placeholder validation/restore 失败；
- `valid_anchored / total_validated_candidates < 0.70`；
- `total_validated_candidates == 0` 不按比例除零，记录 `no_candidates`，不强制 fallback。

响应与持久化都必须标记：

```text
generation_method = live | mock | deterministic_fallback
degraded = true | false
fallback_reason = null | provider_missing | provider_error | invalid_output | placeholder_error | anchor_drop_rate
```

---

## 8. 数据模型最小扩展

### Artifact

新增 nullable 字段：

```text
ingestion_key        # raw source 使用；服务端 namespace 后全局唯一
generation_metadata # AI artifact 使用；metadata only
```

`generation_metadata` 允许：

```json
{
  "method": "live|mock|deterministic_fallback",
  "provider": "deepseek|null",
  "model": "string|null",
  "degraded": false,
  "fallback_reason": null,
  "redaction_counts": {"name": 0, "id": 0, "phone": 0},
  "source_artifact_id": "art_..."
}
```

禁止存 prompt、raw/redacted clinical text、mapping、API response dump。

### Highlight

新增 nullable 字段：

```text
entity_type
entity_key
assertion_value
conflict_with_artifact_id
review_status  # null | needs_review
```

这些字段用于 deterministic ranking/conflict/provenance，不引入 Entity 或 Task 新表。

唯一性/幂等：

- 客户端 key 先由服务端做 namespace：event source 使用 `clinic_id:event_id:key`，patient session 使用 `clinic_id:patient_id:session_id`；
- namespaced `ingestion_key` 在 raw Artifact 上全局唯一；不得只做 `(event_id, key)`，否则 session 重试可能先创建第二个 Event；
- patient session 的 Event ID 由 `patient_id + session_id` 稳定派生，重试必须先查 key/稳定 Event ID，再决定是否创建；
- AI summary ID 由 `source_artifact_id + summary_type` 稳定派生；
- Highlight ID 由 `source_artifact_id + restored_quote + entity_key` 稳定派生；
- 同一 ingestion key 重试返回已存在结果，不新增重复记录。

---

## 9. 三类 Flow、作者语义与 RBAC

| 入口 | Role | Event type | Raw type / author_role | AI summary type |
|---|---|---|---|---|
| patient session | patient（仅本人） | `patient_ai_preconsult` / `patient_followup` | `raw_conversation` / `patient` | `ai_patient_session_summary` |
| event source | staff（同 clinic） | `nurse_consult` | `transcript` / `system` | `ai_nurse_consult_summary` |
| event source | clinician（同 clinic） | `doctor_consult` | `transcript` / `system` | `ai_doctor_consult_summary` |

- admin 保持 read-only，不能 ingest；
- patient 不能向既有 doctor/nurse Event 上传 transcript；
- staff 不能生成 doctor summary；clinician 不能把 doctor transcript 标成 nurse flow；
- source type / event type / role 任何不匹配 → 403 或 422（scope 仍先检查，跨 clinic / 非本人保持统一 404）；
- AI summary 始终 `author_role=system`, `author_id=null`；
- AI summary 的 `provenance_pointer.event_id/artifact_id` 指回 raw source；只有存在明确单一 supporting quote 时才写 span；
- transcript 始终 `author_role=system`, `author_id=null`；
- patient raw conversation 使用 patient user 作为 `author_id`；
- 所有新写操作写 metadata-only AuditLog；新增 action 至少包括 `source_ingest` / `ai_generate` / `ai_fallback`，不记录 clinical content。
- AuditLog 的 actor 仍是触发摄入的已认证 User；AI Artifact 本身保持 `author_role=system`。不得为满足 FK 临时伪造一个 system user。

新增 centralized actions：

```text
create_patient_session
ingest_nurse_transcript
ingest_doctor_transcript
```

全部加入 M3 的 `PERMISSIONS` / `authorize`，端点不得手写 role if 代替授权。

---

## 10. API 与事务合同

```text
POST /api/events/{event_id}/sources
body: {
  ingestion_key,
  artifact_type: "transcript",
  content
}

POST /api/patients/{patient_id}/sessions
body: {
  session_id,                 # idempotency key
  event_type: patient_ai_preconsult | patient_followup,
  started_at,
  ended_at?,
  content
}
```

统一响应：

```text
{
  event_id,
  source_artifact_id,
  ai_summary_artifact_id?,
  highlight_ids,
  generation_method,
  degraded,
  fallback_reason,
  idempotent_replay
}
```

- staff/clinician 可收到上述完整内部响应；
- patient session 响应只返回 `event_id` / `source_artifact_id` / processing status / degraded，不返回内部 `ai_summary_artifact_id` 或 `highlight_ids`；M4 不借摄入响应绕过 Patient View 的可见性边界；

事务顺序：

1. 鉴权与输入类型校验；
2. 检查 ingestion/session key；若完整结果已存在则直接返回；若只有 raw 或上次 derived 失败，则复用同一 Event/raw 重新执行 derived pipeline；
3. 创建 Event（session 入口需要）+ raw Artifact 并 commit；
4. 执行 redaction/provider/fallback；
5. AI summary + valid Highlights 在第二个事务中原子写入；
6. derived transaction 失败时 rollback derived 数据，raw source 保留；
7. 返回明确失败/degraded 状态，禁止半个 summary + 半组 highlights。

不得使用 `created_at` 冒充 `started_at`；session 的真实发生时间必须由请求提供并校验 `ended_at >= started_at`。

---

## 11. Bounded Clinician Authority / Conflict Contract

M4 不做通用语义矛盾检测。选择一个可解释、fail-closed 的最小策略：

1. AI 永不更新或覆盖 clinician/staff Artifact；
2. AI candidate 默认不是 clinician-confirmed；
3. 仅当 AI candidate 与同 Patient 的 clinician note 能得到相同 `entity_key`，且两边都有可确定的 `assertion_value` 且值不同时：
   - 保留 AI Highlight；
   - `review_status=needs_review`；
   - `conflict_with_artifact_id=<clinician note>`；
   - `risk_reason` 明确说明“conflicts with clinician-authored record; review required”；
   - 不自动 accept/pin，不把 AI assertion 合并进 clinician note；
4. 无法确定 entity/value 时，不宣称 conflict，也不宣称 confirmed，保持 suggested；
5. UI 至少显示 `Needs review` + clinician Artifact 跳转。

现有 `GET /api/highlights/{highlight_id}/provenance` 扩展一个 nullable `conflict_artifact`；只有 `review_status=needs_review` 时返回，并沿用同一 patient/clinic authorization。前端用该 Artifact 的 `event_id` 聚焦 Timeline，不新增第二套 conflict 页面。

`conflicts.py` 只可对 clinician note 的 string leaves 使用冻结的 medication/dose 与 task/status regex 生成 bounded `entity_key/assertion_value`；不得再次调用 LLM，也不得用 substring 相似就声称冲突。无法 deterministic normalize 时走第 4 条。

本阶段只需对 fixture 可确定的 medication/dose 或 task/status 示例实现和测试；不得扩大为诊断判断。

---

## 12. Importance Ranking（服务端决定）

继续使用 M2 冻结权重：

```text
score = 2*recency + 3*explicit_risk + 2*unresolved_task
      + 2*clinician_confirmed + 3*symptom_change + 1*repeated_mentions
```

计算合同：

- `recency`：以显式注入的 `as_of` 计算 `event.started_at` 是否在 7 天内；测试不得读取漂移的 wall clock；
- `explicit_risk` / `symptom_change`：来自通过 schema 的 candidate；
- `unresolved_task`：M4 没有 Task/status model，固定为 `false`，不得把 UNKNOWN 当 true；
- `clinician_confirmed`：pipeline 初始为 `false`；只有 highlight status mutation 的当前 actor 是 clinician 且动作是 accept/pin 时，才置 true 并重算 score，同时写 AuditLog；staff 操作不能改变该 flag；
- `repeated_mentions`：相同 `entity_key` 出现在至少 2 个不同 Event 的有效 Highlight；
- 当第二个 Event 使 repeated condition 首次成立时，新 Highlight 与受影响的既有 Highlight 都要重算，不能只给最新一条加分；
- `needs_review` 不等于 confirmed，不获得 clinician-confirmed 加分；
- score 在写入或明确 feedback 更新时预计算；Glance GET 继续零 LLM、零 extraction。

---

## 13. 任务分解（串行，每步一个 commit）

| # | 任务 | 验证 |
|---|---|---|
| 0 | provider protocol smoke + 状态记录 | LIVE_VERIFIED / NOT_LIVE_VERIFIED / INCOMPATIBLE 明确 |
| 1 | schema extension + seed/backfill：Artifact/Highlight 最小字段 | 61 tests 不回归；不引入 migration framework |
| 2 | `redaction.py` + placeholder restore tests | provider payload 无 PHI；raw quote 可恢复匹配 |
| 3 | extraction schema + normalization | 非法 candidate fail-closed |
| 4 | fixture-independent deterministic fallback | 新 source 可处理；不 import seed |
| 5 | `LLMClient` + mock/provider adapter | timeout/error 分类；无 key 可测试 |
| 6 | pipeline + bounded conflict + deterministic score | derived transaction 原子、无覆盖 |
| 7 | ingestion APIs + centralized RBAC + idempotency | 三类 flow 和重试行为通过 |
| 8 | UI 最小入口/状态/needs-review 展示 | Glance/source jump/clinician jump 可演示 |
| 9 | 完整测试 + README/Attribution 回填 | 全量 pytest + frontend build |

若 Gate 0 为 INCOMPATIBLE，不得用临时换 provider 吞掉问题；继续 mock/fallback 实现，并把 live adapter 标为 blocked，等待 owner 决策。

---

## 14. 测试矩阵

### `test_redaction.py`

- known patient/user name、IC/ID、phone 均替换；
- nested messages/segments 结构不变；
- mock client payload 不含任何原文 PHI；
- placeholder 完整恢复后 quote 能定位 raw span；
- mapping 未进入 Artifact/AuditLog/log capture；
- overlapping ID/phone pattern 有确定结果。

### `test_ai_pipeline_fallback.py`

- provider missing / timeout / invalid JSON / placeholder corruption / anchor drop rate 分别触发正确 fallback reason；
- fallback 对新 source 工作且不 import seed fixture；
- unsupported source 允许 0 highlights，不编造；
- raw Artifact 在 provider/fallback/derived-write 失败时均保留；
- derived transaction 不留下 partial data。

### `test_ai_pipeline_e2e.py`

参数化三类 flow：

- patient raw conversation → patient summary；
- nurse transcript → nurse summary；
- doctor transcript → doctor summary；
- summary `author_role=system`, `author_id=null`；
- valid Highlights 全部解析到 raw substring；
- Glance 可见且 source jump 正确；
- clinician/staff/raw Artifacts 内容与版本完全不变。

### `test_source_ingestion_rbac.py`

- patient 只能给自己的 session 写 raw conversation；
- staff 只能走 nurse transcript flow；
- clinician 只能走 doctor transcript flow；
- admin 不可写；
- 跨 clinic / 非本人统一 404 body；
- type/event/role mismatch 拒绝；
- 同 ingestion/session key 重试不产生重复数据。

### `test_ai_conflict_authority.py`

- bounded normalized value conflict → `needs_review` + clinician artifact pointer；
- clinician note 未被修改、版本未增加；
- 无法确定的内容保持 suggested，不伪造 conflict/confirmed；
- clinician accept/pin 才触发 `clinician_confirmed=true` 和 score 重算。

### 回归

- M1–M3 全部测试；
- `test_highlight_provenance.py`；
- frontend TypeScript/Vite build；
- Glance GET module/import 检查，证明不调用 pipeline/LLM。

---

## 15. Exit Gate — AI Vertical Slice Complete

使用一份不在 seed 中的新 synthetic source，必须证明：

1. raw source 先持久化；
2. provider/mock 实际只收到 redacted content；
3. 正确生成对应类型 AI summary；
4. summary 明确记录 live/mock/fallback/degraded metadata；
5. 每条落库 Highlight 都能回到 raw source 的 exact substring；
6. Glance 出现新 Highlight，source jump 正常；
7. clinician/staff note 没有被覆盖或改版；
8. bounded conflict 示例显示 `Needs review` 和 clinician pointer；
9. 相同 ingestion key 重试无重复；
10. 三类 flow、RBAC、fallback、全量回归测试通过；
11. provider 状态被诚实记录，不把 mock/fallback 冒充 live；
12. README 与实际 redaction/client 入口一致。

通过后只可声明：

> **M4 / AI Vertical Slice Complete**

不得声明 Core Complete，直到 Patient View、性能测量及项目最终完成定义中的其余硬门另行通过。

---

## 16. 停止条件与风险

- provider SDK/protocol 不兼容 → 停止 live adapter，不静默换栈；
- 无 API key → mock/fallback 继续，状态为 `NOT_LIVE_VERIFIED`；
- quote 无法 exact restore/anchor → 丢弃或 fallback，不 fuzzy match；
- fallback 也无法产生可信 candidate → 允许 0 highlights，保留 raw；
- conflict 无法 normalized compare → 保持 suggested，不猜测；
- ingestion 重试产生 duplicate → 本阶段失败；
- raw source 因 AI 错误回滚丢失 → 本阶段失败；
- Patient 能通过新增 API 越权摄入或读取内部 AI 内容 → 本阶段失败；
- 为完成 M4 而新增 Task、Patient View、自学习、Voice、RAG、模型训练 → 越界，停止。
