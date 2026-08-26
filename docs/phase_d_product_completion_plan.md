# Phase D 产品化完善阶段 - 总执行方案

> 状态：**APPROVED FOR PLANNING（2026-08-26）**
>
> 前置状态：M1-M7、C1/C2 已完成；161 个后端测试与 frontend production build 已通过。
>
> 本阶段目标不是准备提交材料，而是把当前技术纵切原型升级为医生、staff 和患者可以从登录开始完整走通一次照护流程的产品级 Demo。

---

## 1. 阶段判断

当前系统已经证明以下技术机制成立：

- 单一纵向患者记录；
- Event -> Artifact -> Span provenance；
- Glance、Timeline、Comments、Revision、Audit；
- server-side RBAC 与 clinic scope；
- patient-safe projection；
- transcript -> redaction -> AI -> exact source 的严格 happy path；
- warm-path Glance 性能。

当前系统尚未形成完整产品闭环：

- 没有真实注册、邀请、登录、session 和 logout；
- Patient View 是安全投影，不是完整患者产品；
- "pending" 仍是文字/Highlight，没有可推进、可完成、可审计的 Task；
- Transcript 只证明严格固定格式可运行，没有现实输入归一化与冻结评测集；
- clinician 右栏没有 patient-scoped、evidence-bound Copilot；
- TLS 与 encryption at rest 尚未形成真实部署证据；
- 现有顶部 Role selector 是 demo 控件，不是身份系统。

因此 Phase D 的完成定义是：

> 医生、staff 和患者分别通过真实 Demo 身份进入系统，并围绕同一个患者记录完成 transcript 导入、临床审核、Task 推进、患者说明、患者 check-in 与后续确认；所有 AI 事实可追溯，所有写入受权限和审计约束。

---

## 2. 产品模型

```text
Timeline     = what happened
Glance       = what matters now
Tasks        = who must do what next
Patient View = what the patient needs to know and do
Copilot      = evidence-bound help to understand and draft actions
```

Phase D 不改变永久核心模型：

```text
Patient
  -> Event
    -> Artifact
      -> Span
```

Task、Copilot answer 和患者可见内容都必须链接回这个模型，而不是创建平行患者数据库或 AI 记忆库。

---

## 3. 已确认的产品决策

### 3.1 身份与注册

- clinician/staff/admin 通过 clinic-scoped invite 注册；不得公开自选临床角色；
- patient 通过绑定既有 `patient_id` 的邀请注册；不得按姓名搜索并认领记录；
- Demo 可以不发送真实邮件/SMS，但邀请 token、过期、单次使用、密码哈希和 server-side session 必须真实实现；
- Role selector 仅可保留在显式 development/demo-control 模式，正式产品路由不得以它作为身份来源；
- Phase D 暂不支持一个用户跨多个 clinic membership。

### 3.2 Task authority

- Task 是一等实体，不是 Comment、Highlight 或 patient instruction 的别名；
- patient 只能把自己可见且分配给自己的 Task 报告为 `reported_done`；
- staff/clinician 才能确认 `completed`；
- Task 状态变化必须有 actor/time/audit，并影响 Glance unresolved scoring；
- Task 必须关联 patient，并在可能时关联 Event/Artifact/Span provenance。

### 3.3 Transcript boundary

- canonical transcript 继续使用严格、不可变、连续 index 的 speaker-labelled segments；
- raw text 先进入无持久化的 normalization/preview 路径；
- unknown speaker、低置信解析和格式歧义不得静默进入正式记录；
- 用户确认后才写入 canonical Transcript 并触发现有 redaction/LLM/provenance pipeline；
- Phase D 不加入 audio、ASR、OCR 或 EHR import。

### 3.4 Copilot authority

- Copilot 只读取当前授权 patient 的记录；
- 每个临床事实必须带可解析 evidence；推断和 unknown 必须明确标记；
- Copilot 可以生成 draft note/task/instruction，但不得直接写正式临床记录或完成 Task；
- 所有持久化动作必须由授权用户显式确认；
- patient switch、role/session change 必须清空 Copilot 临时状态。

### 3.5 Security direction

- TLS 保护传输；encryption at rest 保护数据库/磁盘/备份；RBAC 保护已登录用户之间的数据边界，三者不可互相替代；
- SQLite 保留为快速单元测试路径；部署/多人集成路径优先评估 PostgreSQL；
- at-rest gate 优先要求可验证的数据库/volume/backup 加密，不先盲目加密全部 Artifact JSON；
- 应用级字段加密只在明确字段、查询影响和密钥轮换策略后实施；
- 继续使用 synthetic data，Phase D 不授权真实 PHI。

---

## 4. 两条必须跑通的产品旅程

### 4.1 Clinician journey

```text
Receive invite
-> Register
-> Login
-> Clinic patient directory
-> Open patient Glance
-> Review history/tasks
-> Start consult
-> Paste/import transcript
-> Review normalization preview
-> Confirm canonical transcript
-> AI summary/highlights
-> Verify exact source
-> Create/edit clinician note
-> Create patient-visible task/instruction
-> Close consult
-> Follow later patient/staff updates
```

### 4.2 Patient journey

```text
Receive patient invite
-> Register and link existing record
-> Login
-> Today
-> Read current instruction
-> View care tasks
-> Report task done or submit symptom update
-> Review visit summaries/follow-up
-> Clinic verifies and updates plan
```

Staff 使用与 clinician 相同的 clinic shell，但功能按 RBAC 裁剪；Phase D 不创建独立 Nurse Workspace。

---

## 5. 任务卡与依赖顺序

| 顺序 | 任务卡 | 目标 | 依赖 |
|---|---|---|---|
| D1 | `Task_Card/D1_Identity_Access_Task_Card.md` | Invite、register、login、session、logout、产品路由 | M3 RBAC |
| D2 | `Task_Card/D2_Care_Tasks_Patient_Experience_Task_Card.md` | 一等 Task + 可完成的 Patient Experience | D1 |
| D3 | `Task_Card/D3_Transcript_Reliability_Task_Card.md` | Raw import preview + 冻结 transcript 评测 | D1；复用 M4/C1 |
| D4 | `Task_Card/D4_Clinician_Copilot_Task_Card.md` | 有证据、只生成草稿的 patient-scoped Copilot | D2 + D3 |
| D5 | `Task_Card/D5_Security_Integration_Task_Card.md` | TLS/at-rest 部署证据 + 三角色 E2E/可用性收口 | D1-D4 |

执行顺序默认串行通过 Exit Gate。D2 UI 设计与 D3 corpus 编写可以并行准备，但不得在 D1 身份合同未冻结前接入产品路由；D4 不得在 Task 与 Transcript 可靠性完成前开工。

---

## 6. 阶段级验收标准

Phase D 只有在以下全部成立时才可声明 Product Demo Complete：

1. demo-control role selector 不再是正式产品身份入口；
2. clinician、staff、patient、admin 均能通过真实 invite/login/session 流程进入授权视图；
3. patient 不能通过前端或直接 API 获取任何 internal clinical content；
4. clinician 能完成 New Consult -> Transcript Preview -> AI -> exact source -> clinician note；
5. clinician/staff 能创建和推进 Task，patient 能报告完成，clinic 能确认完成；
6. Task 状态真实影响 Glance 和 Patient Today/Care Plan；
7. 冻结 transcript holdout 有可复现指标，失败和 unknown 明确可见；
8. Copilot 的事实回答 100% 带可解析 evidence，任何写入只产生待确认 draft；
9. HTTPS/TLS 与 at-rest encryption 有当前部署的验证证据，不只写在 README；
10. 三条 E2E journey 通过，全部历史 required tests 零回归；
11. frontend production build、PostgreSQL integration path（若 D5 采用）和 SQLite unit path 均通过；
12. README、AGENTS 和任务卡状态与实际实现一致，不再声明未实现的 AES-GCM 或 production readiness。

---

## 7. 跨卡工程规则

- 每张卡先写失败测试/验收用例，再实现；
- 所有身份与权限判定继续以数据库和 server-side session 为权威；
- 任何 AI-derived 内容继续独立于 human-authored Artifact；
- raw/canonical source 不得被 AI summary 覆盖；
- 失败必须可见，不允许 silent fallback 到另一个用户、speaker、Task 状态或来源；
- 日志与 AuditLog 只记录必要 metadata，不记录密码、token、密钥或完整患者文本；
- 新 UI 必须有 loading/empty/error/forbidden/conflict 状态；
- patientId、role、session change 继续作为完整前端状态隔离边界；
- 不为尚未实现的 appointment、billing、prescription、voice 或 assignment 展示假状态。

---

## 8. Phase D 非目标

- 真实患者数据或生产医疗使用；
- 自助选择 clinician/admin 角色；
- MFA、SSO、真实邮件/SMS 供应商集成；
- billing、appointment scheduling、处方/化验真实下单；
- Voice/ASR、OCR、EHR import；
- 独立 Nurse Workspace；
- 多 clinic membership；
- model fine-tuning、自学习 ranking、data decay；
- 无证据的诊断型聊天；
- 大规模 RAG 或生产容量声明。

---

## 9. 计划变更规则

- 新需求若不直接服务两条核心 journey，进入 backlog，不插入当前卡；
- 任何卡需要放松 provenance、RBAC、clinician authority 或 patient anti-leak 才能完成时，立即停止并重新设计；
- PostgreSQL、字段加密、真实邮件等架构选择必须以卡内 Decision Gate 记录，不从文档假设为已实现；
- D1-D5 全部通过前，不恢复 Technical Brief、demo recording 或 Bonus 工作。
