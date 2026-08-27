# D3 任务卡 - Transcript Import, Normalization and Reliability Evaluation

> 状态：**COMPLETE（2026-08-27，审查修复后重验）**
>
> 对应总计划：`docs/phase_d_product_completion_plan.md`
>
> 审查修复：① NewDoctorConsult split/merge/edit 后 source_start/source_end 不再失真——能精确映射则重算，否则显式标记 user-modified/unmapped，不显示伪精确范围；② corpus validator 不再自报/强制 `D3_COMPLETE`，改为层级准确的 `CORPUS_VALIDATION_PASS`（完整完成状态仅由 D3 Exit Gate 给出）；③ 统一 AGENTS/README provider 配置——仅 mock/deepseek，deepseek 缺 key 时 deterministic fallback，消除 LIVE_VERIFIED 冲突；④ split/长度计算改为 code-point-aware（emoji/非 BMP 不切 surrogate pair，无法精确时置空）。frozen cases、holdout hashes、normalizer 规则未改动。
>
> 复用：C1 immutable Transcript、M4 redaction/LLM/extraction/provenance pipeline；不得创建第二条 AI/provider 出口。

---

## 1. 目标

证明系统不只会处理一份团队自写的固定 transcript，而能对现实中的文本变体做以下三种明确结果：

```text
ACCEPT       -> 可确定转换为 canonical segments
NEEDS_REVIEW -> 有歧义，用户必须修正后确认
REJECT       -> 无法安全解释，不进入记录/LLM
```

可靠性不是“尽量什么都接受”，而是正确识别可处理边界并保持 fail closed。

---

## 2. 输入与存储合同

### Raw import request

接受普通 text transcript；normalize endpoint 不持久化、不调用 LLM，只返回 preview。

### Preview segment

```text
index
speaker_candidate       # doctor|patient|null
text
source_start
source_end
confidence_marker       # deterministic category, not fake probability
issues[]
```

建议 confidence marker：`exact_label | mapped_label | inferred_boundary | unknown`。

### Canonical confirm

- 用户必须解决所有 `unknown` speaker、空文本、重叠/缺失 source range；
- confirm 后继续使用现有 continuous 0-based `doctor|patient` schema；
- canonical Transcript 是 immutable raw clinical source；
- 不发明 timestamp；raw input 没有 timestamp 就保持无 timestamp；
- 保存前显示最终 canonical preview；
- 保存后复用现有 doctor-consult ingestion 和 exact span pipeline。

---

## 3. Backend 范围

最小新增：

```text
POST /api/transcripts/normalize
```

确认写入继续使用或窄幅扩展现有：

```text
POST /api/patients/{patient_id}/doctor-consults
```

normalizer 只做确定性 parsing/canonicalization：

- 支持 `DOCTOR/PATIENT`、`Doctor/Patient`、`Dr/Pt` 等冻结映射表；
- 支持每行 label 与合理的多行 continuation；
- 不确定 label 不映射；
- 无 label 长段落不得自动交给 LLM 猜 speaker；
- 归一化保留原始字符范围，用于 preview 可解释性；
- normalize 不读取 patient DB、不产生 Event/Artifact/Audit；
- confirm 才执行 RBAC、raw-first persistence、redaction 与 provider call；
- 超长输入有明确 byte/segment limit 和 413/422，不静默截断；
- prompt injection 只作为 transcript 内容，不得改变系统 schema/指令。

---

## 4. Frontend 范围

New Consult 改为三步：

```text
1. Paste transcript
2. Review segments
3. Confirm and process
```

Preview 必须：

- 原文与 segments 可对照；
- unknown/issue 明显高亮；
- 用户可修改 speaker、合并/拆分文本；
- 无法确认时允许返回编辑，不丢 draft；
- confirm 前显示将创建新 Event；
- processing 显示 raw persisted / AI derived / fallback 三种真实状态；
- failed derived processing 不删除已确认 Transcript；
- patient/session switch 清空未确认 preview；
- 不展示伪造的 ASR confidence/timestamp。

---

## 5. 冻结评测集

建立：

```text
backend/evals/transcripts/cases/*.json
backend/evals/transcripts/manifest.json
backend/scripts/evaluate_transcripts.py
backend/docs/transcript_reliability_baseline.md
```

首轮建议 30-50 个 synthetic cases，至少覆盖：

- canonical labels 与大小写/缩写变体；
- continuation lines、空行、重复 label；
- unknown speaker、三人对话、缺少 label；
- 中英混合、口语、自我修正、打断；
- medication/dose、否定、时间表达、任务状态；
- 内部矛盾、无临床信息、超长内容；
- 姓名、IC/ID、电话；
- prompt injection 与恶意 JSON/Markdown；
- quote 可匹配和不可匹配；
- provider invalid schema/failure/fallback。

分区：

- development set：可用于规则开发；
- frozen holdout：冻结 bytes/hash，不进行 outcome-dependent 调整；
- 每例记录 expected normalize outcome、canonical segments 或 reject reason；
- extraction 评测只对明确标注字段评分，UNKNOWN 不转成默认值。

---

## 6. 指标与硬门

最低报告：

- normalize outcome accuracy；
- speaker mapping accuracy（只对有 ground truth cases）；
- silent speaker invention count；
- truncation without explicit error count；
- PHI redaction miss count；
- exact quote restoration/anchor success rate；
- unsupported/ambiguous cases correctly blocked；
- entity/task extraction precision/recall（有标注子集）；
- hallucinated fact count；
- conflict flag accuracy（有标注子集）；
- provider/fallback 分层结果，不能混报。

硬门：

```text
silent speaker invention = 0
silent truncation = 0
raw source overwritten = 0
unanchored highlight persisted = 0
known PHI sent unredacted in frozen cases = 0
```

其他指标不先写任意高阈值；第一轮先形成诚实 baseline，再由 owner 冻结后续目标。

---

## 7. 必须测试

建议新增：

```text
tests/test_transcript_normalization.py
tests/test_transcript_preview_contract.py
tests/test_transcript_limits.py
tests/test_transcript_eval_manifest.py
```

覆盖 normalize 无持久化/无 LLM、label mapping、unknown block、source offsets、confirm continuous indexes、RBAC/raw-first/idempotency、超长输入、prompt injection、failed derived processing、patient switch draft isolation，以及现有 C1/M4 tests 零回归。

---

## 8. Exit Gate - D3 Complete

1. New Consult 三步导入可实际使用；
2. ambiguous transcript 必须人工修正或拒绝，不能静默猜测；
3. frozen corpus、manifest/hash、runner 和 baseline 文档齐全；
4. 所有硬门为零违规；
5. holdout 结果与 provider/fallback 分层诚实报告；
6. confirmed Transcript 仍可回到 exact source，AI summary 不覆盖 raw；
7. 全量 backend tests、eval runner、frontend build 全绿。

---

## 9. 完成记录（2026-08-27）

- `POST /api/transcripts/normalize` 已实现 clinician-only、strict request、无 patient DB read、无持久化、无 LLM/provider 的 deterministic preview；支持冻结 label mapping、continuation、source range 与 `ACCEPT|NEEDS_REVIEW|REJECT`。
- UNKNOWN/第三人/无 label/空 segment/4096-byte/500-segment/4000-character 边界均 fail closed；UNKNOWN 永不默认 doctor/patient，prompt injection/JSON/Markdown 只作文本。
- New Consult 已改为 `Paste → Review → Confirm`；原文/preview 并排，支持 speaker/text 修正与 split/merge；REJECT 不可 confirm，NEEDS_REVIEW 必须清除 null speaker/empty；patient switch 清空 draft/preview/operation/pending state。
- confirm 继续使用 C1 `POST /api/patients/{patient_id}/doctor-consults`；只保存 continuous canonical segments，Event + immutable Transcript raw-first，AI Summary/Highlights 独立，derived failure 不删除 raw。
- frozen corpus 为 40 cases（development 26 / holdout 14），40/40 hashes 与 holdout composite digest 验证通过；normalizer 在首次 holdout 前按 SHA-256 冻结，未针对 holdout 调规则。
- holdout normalize 14/14、speaker 12/12、ambiguous block 8/8；silent invention/truncation/redaction miss/fallback unanchored candidate 均 0。Provider 仅 mock/deepseek，deepseek 缺 key 时 deterministic fallback；frozen runner provider 层明确 NOT_RUN，deterministic fallback 单独报告，未混报。
- backend **296 passed**，corpus validator/runtime runner exit 0，frontend production build 通过；本地 browser QA 覆盖 ACCEPT/NEEDS_REVIEW/REJECT、人工修正、split/merge、confirm/fallback/exact source、patient-switch isolation，console 0 warnings/errors。审查修复后重验：source-range remap/unmapped（含 emoji/非 BMP 的 code-point-aware 拆分）、`CORPUS_VALIDATION_PASS`、provider 配置统一均锁定（`tests/test_transcript_preview_contract.py` 新增 canonical 边界断言，`tests/test_transcript_non_bmp.py` 运行 Node `frontend/tests/transcriptRange.test.mjs`）。

---

## 10. 非目标与停止条件

非目标：audio/ASR、diarization、OCR、实时 streaming、多人 overlap、外部数据集自动导入、LLM speaker guessing。

停止条件：

- 为提高成功率把 unknown 默认为 patient/doctor -> 停止；
- normalize 阶段调用 LLM 或持久化患者记录 -> 停止；
- 根据 frozen holdout 逐例补规则且不重新冻结 -> 停止；
- provider/fallback 混为一个成绩或不可锚定内容仍入库 -> 停止。
