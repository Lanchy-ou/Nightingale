# Phase E — Capability Enhancement

> 中文名称：能力提升阶段
>
> 状态：**IN PROGRESS — E1/E2 COMPLETE；E3–E5 状态以各自任务卡/分支验收为准（2026-08-27）**
>
> 前置状态：Phase D 工程实现与自动化验收完成；当前核心基线为 342 个 backend tests、D3/D4 frozen evaluation、frontend production build 与 D5 security evidence 通过。
>
> 本文只冻结目标、边界、依赖与验收方式，不代表 E1–E5 已实现。

---

## 1. 阶段目标

Phase E 在不破坏现有纵向病历、权限、来源追溯和患者隔离的前提下，把当前成熟 Demo 提升为更完整、可适应、可扩展且可提交的 Nightingale 原型。

本阶段集中处理五个纵向目标：

1. 让 Nurse/Staff 与 Admin 拥有符合职责而非复制页面的工作区；
2. 让 Glance 从显式用户反馈中学习未来相似候选的优先级；
3. 让旧的低价值数据发生确定性降权和分层，但不丢失 raw source 或 provenance；
4. 把录音设计为独立 Voice Capture Adapter，输出可审核 Transcript 并复用现有 AI pipeline；
5. 把实现、证据、Technical Brief、Demo Video 与提交包收口为一致交付。

Phase E 不改变永久产品模型：

```text
Patient
  -> Event
    -> Artifact
      -> Span
```

新增能力必须继续围绕同一条纵向患者记录工作，不得产生 Nurse 数据库、Voice 数据库、AI memory 数据库或 Archive 患者副本。

---

## 2. 产品模型补充

```text
Timeline       = what happened
Glance         = what matters now
Tasks          = who must do what next
Patient View   = what the patient needs to know and do
Copilot        = evidence-bound help to understand and draft actions
Self-Learning  = how explicit review changes future soft priority
Data Decay     = how old low-value information leaves the hot path safely
Voice Adapter  = how audio becomes a reviewed source Transcript
```

Self-Learning 与 Data Decay 都可以影响 Glance 排序，但不能改变临床事实：

```text
final importance
  = deterministic base score
  + bounded adaptive adjustment
  + bounded decay adjustment
```

任何学习或衰减都不能覆盖以下硬保护：

- explicit clinical risk；
- unresolved Task；
- clinician-confirmed 或 pinned item；
- conflict / needs_review；
- exact provenance availability；
- patient anti-leak 与 clinic scope。

---

## 3. Phase E 统一 Entry Gate

E1 开工前必须完成一次只读基线冻结：

1. 当前工作区 clean，或所有既有修改都已明确归属；
2. 记录当前 commit hash；
3. backend 全量 tests 通过；
4. D3 corpus validation、runtime evaluation 与 D4 frozen Copilot evaluation 通过；
5. frontend production build 通过；
6. D5 SQLCipher/TLS/security evidence 不因新计划失效；
7. 记录当前 Glance warm-path P95；
8. 确认没有真实 PHI、外部未授权数据或未记录许可证资产进入仓库。

该 Entry Gate 是 E1–E5 的共同基线，不再单独拆分 E0 任务卡。

---

## 4. 任务卡与依赖

| 顺序 | 任务卡 | 目标 | 依赖 |
|---|---|---|---|
| E1 | `Task_Card/E1_Role_Workspaces_Task_Card.md` | Nurse/Staff 复用临床工作台；Admin 获得 clinic-scoped oversight | Phase E Entry Gate |
| E2 | `Task_Card/E2_Self_Learning_Importance_Task_Card.md` | 显式反馈改变未来相似 Glance 候选的可解释优先级 | E1 角色/authority 冻结 |
| E3 | `Task_Card/E3_Data_Decay_Task_Card.md` | Hot/Warm/Cold、确定性 decay、可逆 archive 证据 | E2 scoring fields 冻结 |
| E4 | `Task_Card/E4_Voice_Capture_Adapter_Task_Card.md` | Recording -> ASR -> reviewed Transcript -> existing pipeline | E1 Event/role contract；可独立设计 |
| E5 | `Task_Card/E5_Submission_Package_Task_Card.md` | Technical Brief、Demo Video、README、Attribution、最终验证与提交包 | E1–E4 的已选提交范围 |

默认实现顺序：

```text
Entry Gate -> E1 -> E2 -> E3 -> E4 -> E5
```

并行规则：

- E4 的接口与 synthetic audio research 可以在 E1 role matrix 冻结后独立进行；
- E4 的产品接入必须等待 E1 的 Nurse/Patient/Clinician Event 归属完成；
- E2 与 E3 都会修改 Highlight score/schema，默认不得在同一工作区并行实现；
- E5 可提前建立 Brief/Demo 骨架，但最终事实、指标与截图只能来自通过 Exit Gate 的实现；
- 任何并行工作必须使用文件 allowlist，不得依靠合并时人工猜测冲突语义。

---

## 5. E1 — Role Workspaces

> Implementation status: **COMPLETE — Exit Gate verified 2026-08-27**. See `Task_Card/E1_Role_Workspaces_Task_Card.md` §12. This status does not advance E2–E5.

### Nurse/Staff

- Nurse 在 MVP 中使用 `staff` 权限角色，可增加 professional title，但不新增平行 RBAC 系统；
- 复用现有 Clinic Patients、Glance、Timeline、Notes、Tasks、Source、Comments、History 与 Event Detail；
- Nurse Consult 与 Doctor Consult 是独立 Event，可通过同一非空 encounter id 组成 Clinic Visit；
- Nurse 可创建 Nurse Consult、staff/nurse note、comment 与权限允许的 Task；
- Nurse 不得写或修改 clinician assessment/plan，不得制造 clinician confirmation；
- `Record nurse consult` 复用 consult workflow，但必须有独立 event type、speaker contract、AI Nurse Summary type 与 RBAC。

### Admin

- Admin 是 clinic-scoped oversight，不是权限最大的 clinician；
- Admin 管理 users、invites、account status、session/access oversight 与安全审计；
- Admin 可以看到完成 oversight 所需的 metadata，但不得冒充 clinician/staff author；
- Admin 不得编辑 Clinician Note、Staff Note、AI Summary、Task clinical state 或 provenance；
- 不建设跨 clinic super-admin、billing、appointment、medical operations console。

---

## 6. E2 — Self-Learning Importance

> Implementation status: **COMPLETE — Exit Gate verified 2026-08-27**. This status does not advance E3–E5 and is based on controlled synthetic evaluation, not real clinician validation.

第一版只学习 Glance 的软排序，不学习诊断、Summary 写法或临床事实。

可信信号优先级：

```text
Pin / Keep on top  = strong positive
Confirm / Accept   = moderate positive
Reject / Hide      = negative
Comment / Edit     = observed but ambiguous; no direct weight in v1
```

学习范围与保护：

- clinic-scoped，不跨 clinic；
- 第一版按 `entity_type` 泛化，必要时再扩展到受控 topic key；
- 每个 actor/highlight 只取最新有效反馈，防止反复切换刷分；
- adjustment 有上下限；
- patient action 不训练 clinical ranking；
- staff feedback 不产生 clinician authority；
- 只有成功的 compare-and-set 状态写入才产生 feedback；
- 新候选在写入时计算 adjustment；Glance GET 保持预计算读取。

---

## 7. E3 — Hybrid Storage / Data Decay

Phase E 使用少量带明确时间的 synthetic data 证明策略，不要求大量历史数据。

最低 tier：

```text
Hot  = current, risky, actionable, unresolved or clinician-confirmed
Warm = older but still contextually relevant
Cold = old, resolved, low-risk and safely recoverable
```

Data Decay 只改变热路径与软排序：

- old low-value candidate 可获得负 decay adjustment；
- high-risk、unresolved、confirmed、pinned、needs_review 不允许负 decay；
- Timeline 仍保留 Event；
- raw Artifact、Version、Comment、AuditLog、Task 与 exact Span 不删除；
- Cold source 必须可授权恢复并通过 hash/provenance round-trip；
- Demo 可使用 verified shadow archive 证明压缩/恢复，不得声称已完成生产对象存储迁移。

---

## 8. E4 — Voice Capture Adapter

Voice 是输入适配器，不是第二套 AI pipeline：

```text
Recording
  -> ASR result
  -> speaker/timestamp/confidence review
  -> confirmed Transcript
  -> existing redaction/LLM/provenance pipeline
```

关键边界：

- 页面只表达 capture intent；服务端 Session/DB role 决定归属和权限；
- Clinician、Nurse/Staff、Patient 分别只能创建允许的 Event；
- raw recording 与 machine transcript 独立保存；
- correction 不覆盖 raw source；
- raw audio 不进入 Summary LLM；
- 外部 ASR 需要单独的 privacy/license/provider Decision Gate；
- 没有 speaker/timestamp 时不得发明；低置信和 unknown 必须进入 review；
- E4 不得阻塞 PDF 明确点名的 Self-Learning 与 Data Decay Bonus。

---

## 9. Data Research Track

互联网数据研究不是独立产品卡，分别服务 E2/E4：

- E4 可寻找 synthetic/acted clinical audio 与 speaker-labelled transcripts；
- E2 可寻找带明确 clinician importance/actionability/feedback label 的数据；
- 普通 Transcript 不得被称为 Self-Learning feedback data；
- 许可证不清、synthetic 状态不清、可能含真实患者数据时 fail closed；
- 研究完成后先报告候选、用途、限制与许可证，未获 owner 批准不得下载或导入；
- 如果没有可信 feedback dataset，使用受控 synthetic evaluation protocol，且不得声称真实 clinician validation。

---

## 10. E5 — Submission Package

E5 只收录已通过 Exit Gate 的事实：

- clean working Git repository 与清晰 commit history；
- automated tests 与复现命令；
- README setup/run、redaction、RBAC、architecture 与限制；
- 2–3 page Technical Brief；
- architecture diagram 与完整 schema mapping；
- ATTRIBUTION.txt 与所有新增 data/model/provider license；
- Demo Video；
- 当前、可复现、分层报告的性能/evaluation/security evidence；
- 明确的 synthetic Demo、非生产医疗、非真人 usability 声明。

E5 不通过文案掩盖未完成实现，不把 mock/fallback 结果称为 live provider 结果，不把预期注释称为观察结果。

---

## 11. Phase E 统一工程规则

- 先失败测试/验收，再实现；
- 所有权限继续 server-side enforcement；
- DB User/Session 是身份与角色唯一权威；
- AI-derived 与 human-authored Artifact 永远分离；
- raw source 不被 summary、review、archive 或 correction 覆盖；
- provenance 不允许 fuzzy fabrication；
- learning/decay 只影响 bounded soft priority；
- clinical risk 与 authority 规则不可由用户偏好关闭；
- 日志与 feedback/audit 只保存必要 metadata；
- patientId、role、session change 继续完整清理前端敏感状态；
- 新 schema 必须兼容 SQLite tests 与 SQLCipher Demo，迁移/重建要求必须明确；
- 所有 synthetic data 必须与 canonical facts 一致或明确属于独立 evaluation fixture；
- 不修改 frozen evaluation expected labels 来迎合实现。

---

## 12. Phase E 非目标

- 真实患者/PHI；
- 生产医疗使用或生产容量声明；
- 新 Nurse 数据库或完全复制的 Nurse App；
- Admin 临床 authoring；
- 黑盒诊断模型或自动处方；
- 用 synthetic labels 训练模型后称为真实 clinician learning；
- 让 Comment/Edit 未经解释直接成为正向学习信号；
- 删除 raw Artifact 或 provenance source；
- 在 E4 中重复实现 Summary/Highlight pipeline；
- 为了 Bonus 引入复杂多 agent、fine-tuning、大型 RAG 或不可审计 ranking。

---

## 13. Phase E Completion Gate

只有以下全部满足时，才可声明 Capability Enhancement Complete：

1. E1–E5 的实际提交范围和状态已明确；
2. Nurse/Staff 与 Admin 角色旅程在 server-side RBAC 下通过；
3. Self-Learning 能让未来相似候选发生可解释、bounded、clinic-scoped 的分数变化；
4. Data Decay 能让旧低价值数据降权/分层，同时保护高风险、未完成和 clinician-confirmed 项；
5. Cold/archived source 可恢复并继续解析 exact provenance；
6. 若 E4 纳入提交，录音必须经 review 成为 Transcript 后才触发既有 AI pipeline；
7. 所有历史 backend tests、D3/D4 eval、frontend build 与 D5 security gates 零回归；
8. 新增数据、库、模型、provider 与许可证进入 ATTRIBUTION；
9. Technical Brief 与 Demo Video 只展示观察到的结果；
10. 最终仓库 clean，提交包完整，且没有未经授权的外部发送或发布。
