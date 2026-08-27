# E4 Task Card — Voice Capture Adapter

> 状态：**PLANNED — IMPLEMENTATION NOT STARTED**
>
> 对应总计划：`docs/phase_e_capability_enhancement_plan.md`
>
> 依赖：E1 的角色、Event 类型与权限合同；接口/数据研究可独立进行，产品接入必须等待 E1。

---

## 1. 目标

把录音实现为独立、可替换、可测试的输入适配器：

```text
browser recording
-> immutable Recording Artifact
-> ASR provider/local adapter
-> machine Transcript with speaker/timestamp/confidence
-> human review
-> confirmed canonical Transcript
-> existing redaction/LLM/provenance pipeline
```

E4 不创建第二套 Summary、Highlight、Task、Patient 或权限系统。

---

## 2. 产品归属

页面只发送 capture intent，后端 Session/DB User 决定权限与最终 Event：

```text
Clinician intent -> doctor_consult
Staff/Nurse intent -> nurse_consult
Patient intent -> patient_ai_session or patient_followup
```

禁止规则：

- 不根据 route 名称或前端 role prop 授权；
- 不允许请求 body 指定 actor role/author/clinic；
- patient 只能写自己的 patient-bound record；
- Nurse/Doctor capture 永远产生独立 Event；
- 同一 Clinic Visit 只通过显式 encounter id 分组。

---

## 3. 开工 Decision Gates

### DG1 — E4 提交范围

在开工前选择：

1. **Interface + deterministic mock only**：证明模块边界，不声称 Ambient Voice 完成；
2. **Local/approved ASR vertical slice**：真实 synthetic audio -> Transcript；
3. **External ASR provider**：需要 privacy、license、key、network、retention 与 failure Decision Gate。

如果目标是 Candidate Brief Ambient Voice Bonus，至少需要方案 2 或 3 的观察证据；只有 mock 不得称为真实 transcription。

### DG2 — Audio storage

明确：

- recording 存数据库 BLOB、encrypted filesystem 或 object storage；
- encryption at rest 如何验证；
- backup 是否包含/排除 audio；
- retention/size limit；
- MIME/codec/sample rate；
- upload 中断与幂等；
- raw audio 谁可读取；
- 不在 access log/exception 中输出 path/token/audio bytes。

### DG3 — Consent and capture UX

在录音开始前明确：

- synthetic Demo only；
- 当前 recording status；
- stop/cancel；
- 是否保存未确认录音；
- microphone permission；
- 失败时不继续假装录制或转写。

### DG4 — Speaker and review contract

冻结 per-mode speaker allowlist：

```text
doctor consult: doctor | patient
nurse consult:  nurse | patient
patient session: patient | ai/system only if actually present
```

unknown、overlap、low confidence、empty text 不得静默默认为任何角色。

---

## 4. Plugin/Adapter Interface

建议内部协议：

```text
VoiceCaptureRequest
  capture_id
  patient_id
  capture_mode
  started_at
  media metadata

ASRClient.transcribe(AuthorizedRecording) -> ASRResult

ASRResult
  provider/method
  language
  segments[]
    source_start_ms
    source_end_ms
    speaker_candidate
    text
    confidence
    issues[]
  degraded
  failure_reason
```

边界要求：

- `ASRClient` 是唯一 ASR exit；
- Summary `LLMClient` 不接收 raw audio；
- ASR failure 不触发空 Summary；
- provider name/model/version 记录为 metadata；
- provider raw response 不直接进入 DB/API/log；
- timestamps/confidence 不存在时返回 unknown/null，不发明；
- raw recording、machine transcript、confirmed transcript 是不同生命周期状态或 Artifact，不覆盖。

---

## 5. Backend Lifecycle

建议最小状态机：

```text
created
-> uploading
-> uploaded
-> transcribing
-> needs_review | failed
-> confirmed
-> processed
```

终态/错误行为必须确定：

- duplicate upload/transcribe/confirm 使用 idempotency key；
- stale status transition 返回 409；
- confirm 前允许修正 speaker/text、split/merge，并重排 continuous indexes；
- confirmed canonical Transcript immutable；
- correction 后不覆盖 recording 或 machine transcript；
- confirmed 后才调用现有 consult/session ingestion；
- raw Transcript/Event 先持久化，再执行 AI pipeline；
- provider/fallback metadata 分层报告。

建议 API（最终可在实现前收敛）：

```text
POST /api/voice/captures
PUT  /api/voice/captures/{capture_id}/audio
POST /api/voice/captures/{capture_id}/transcribe
PATCH /api/voice/captures/{capture_id}/segments
POST /api/voice/captures/{capture_id}/confirm
GET  /api/voice/captures/{capture_id}
```

所有请求先 scope/role authorization，再读取 capture/audio/status，避免存在性枚举。

---

## 6. Frontend Component

设计共享 `VoiceCapture` 组件，通过 server-provided capability 使用，不复制三份录音逻辑。

最低状态：

- microphone permission pending/denied；
- ready；
- recording + elapsed time；
- stopped / preview；
- uploading；
- transcribing；
- needs review；
- failed + retry；
- confirmed/processed。

Review UI 必须显示：

- audio playback；
- segment time range；
- speaker candidate；
- confidence；
- issues；
- editable speaker/text；
- split/merge；
- unknown blocking；
- confirm 后进入对应 Event Detail。

patient/role/session switch、logout、capture cancel 必须停止 MediaRecorder、释放 stream、清除 object URL、pending upload、draft segments 与 response。

---

## 7. Privacy and Security

- synthetic audio only；
- microphone capture 需要明确 user action；
- raw audio 不进入 Summary LLM；
- external ASR 若接收 audio，必须在 Brief/Attribution 标明 provider、privacy boundary 与 retention；
- 不在日志记录 audio、Transcript、signed URL、key 或 provider raw payload；
- request/audio size limit 与 duration limit；
- MIME sniffing/allowlist；
- filename 不作为可信 path；
- encrypted storage/backup evidence 扩展到 Recording；
- authorized roles 之外无法下载/播放 raw recording；
- Patient View 只能看到允许的 patient-facing output，不暴露 clinical raw audio/transcript。

---

## 8. Internet Data Research

只接受：

- synthetic/acted clinical audio；
- 清楚的 speaker/reference transcript；
- 明确 license 与原始作者来源；
- 无真实患者 PHI；
- 可用于研究/Demo 的许可。

候选需记录：

```text
official URL / paper / owner
synthetic vs acted vs real
license
speakers/language
timestamps/reference transcript
noise/overlap/accent/code-switching
sample count and duration
allowed use
cannot prove
ACCEPT / NEED_CONFIRMATION / REJECT
```

未获 owner 批准不得下载、接受协议或导入仓库。若无合适数据，使用短小、自制、明确授权的 synthetic audio fixture，并如实声明覆盖有限。

---

## 9. Automated Tests

建议新增：

```text
backend/tests/test_voice_capture_lifecycle.py
backend/tests/test_voice_capture_rbac.py
backend/tests/test_voice_transcript_review.py
backend/tests/test_voice_ai_handoff.py
backend/tests/security/test_voice_storage_and_logs.py
frontend/tests/voiceCapture.test.mjs
```

必须覆盖：

- clinician/Nurse/patient allowed capture modes；
- cross-role/cross-clinic/cross-patient denial；
- page intent 不能越权；
- upload idempotency/size/MIME limits；
- unknown/low-confidence/overlap blocks confirm；
- split/merge/index recompute；
- timestamps 不发明；
- stale transition 409；
- raw recording/machine/confirmed Transcript 不覆盖；
- ASR failure 不生成 Summary；
- confirmed Transcript 才进入 existing redaction/LLM path；
- Summary/Highlight exact transcript span；
- optional audio timestamp provenance（若实现）；
- patient cannot access clinical audio/raw AI notes；
- logs/audit metadata-only；
- SQLCipher/backup evidence（若 audio in DB）；
- patient/role/session switch frontend cleanup；
- mock 与 live/local ASR 结果分开报告。

---

## 10. 文件边界

建议新模块集中在：

```text
backend/app/voice/                 # models/domain/provider interface
backend/app/api/voice.py
backend/app/schemas.py
backend/app/models.py
backend/app/authz.py
backend/app/api/sources.py         # only confirmed handoff reuse
backend/tests/test_voice_*.py
backend/tests/security/test_voice_*.py
frontend/src/components/VoiceCapture.tsx
frontend/src/api.ts
frontend/src/types.ts
frontend/tests/voiceCapture.test.mjs
```

不得复制/修改 LLM provider exit，或为 Voice 新建 Summary/Highlight 数据模型。

---

## 11. Exit Gate — E4 Complete

1. 一个共享 Voice Adapter 服务允许的角色入口；
2. server-side identity 决定 capture mode/Event 归属；
3. raw recording、machine transcript、confirmed Transcript 生命周期独立；
4. unknown/low confidence 可见且阻断；
5. confirmed Transcript 才进入现有 redaction/AI/provenance pipeline；
6. 新 Summary/Highlight 可回到 exact transcript segment；若有 timestamp，可回到 audio range；
7. raw audio storage/log/RBAC/backup 边界有当前证据；
8. synthetic data/license/Attribution 完整；
9. 全量历史 tests/evals/build/security regression 通过；
10. 只有真实 ASR vertical slice 才称 Ambient Voice 实现；mock-only 必须标为 interface prototype。

---

## 12. 非目标与停止条件

非目标：生产医疗录音、实时多人流式协作、自动诊断、无审核直接成正式 Note、无限时长录音、复杂多设备同步、重新实现 Summary pipeline。

停止条件：

- 前端 route 决定授权 -> 停止；
- raw audio 被发送给 Summary LLM -> 停止；
- unknown speaker 被默认为 doctor/nurse/patient -> 停止；
- ASR failure 仍生成看似成功的 AI Summary -> 停止；
- 需要覆盖 raw recording/transcript 才能修正 -> 停止；
- mock 结果被称为 live transcription -> 停止并修正文档。
