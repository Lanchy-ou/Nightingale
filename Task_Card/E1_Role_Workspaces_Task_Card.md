# E1 Task Card — Role Workspaces: Nurse/Staff and Admin

> 状态：**COMPLETE — EXIT GATE VERIFIED（2026-08-27）**
>
> 对应总计划：`docs/phase_e_capability_enhancement_plan.md`
>
> 本卡目标是完成角色工作流，不创建平行患者数据模型。

---

## 1. 目标

在现有真实 Session、DB User、clinic scope 与统一纵向患者记录上完成两个角色闭环：

```text
Nurse/Staff
-> shared clinic workspace
-> patient Glance/Timeline/Source
-> Nurse Consult / Staff Note / Comment / Task

Admin
-> clinic oversight workspace
-> users/invites/account/session/audit
-> no clinical authoring
```

本卡不是视觉换皮。完成标准是用户可以从真实登录开始完成权限允许的工作，并且直接 API 调用同样受 server-side authorization 约束。

---

## 2. 永久角色决定

### 2.1 Nurse 身份

- MVP 后端权限角色继续使用 `staff`；
- Nurse 是 professional identity/title，不新增第五套 RBAC role；
- Nurse 与 Doctor 在 Event/协作层平行，在 clinical authority 上不平行；
- Nurse Consult 与 Doctor Consult 永远是独立 Event；
- 相同非空 `encounter_id` 只允许 UI 组成一个 Clinic Visit，不合并数据或作者。

### 2.2 Admin authority

- Admin 是 clinic-scoped oversight，不是 super-clinician；
- Admin 可管理本 clinic 的 identity/access 与查看必要 audit metadata；
- Admin 不得创建、编辑、revert Clinician Note 或 Staff Note；
- Admin 不得把 AI Summary 确认为临床事实；
- Admin 不得替 patient/clinician/staff 推进临床 Task；
- Admin 不得跨 clinic 查看用户、患者、邀请、Session 或 AuditLog。

---

## 3. 开工 Decision Gates

### DG1 — Nurse capability matrix

开工前冻结 Nurse/Staff 的最小允许行为：

- read clinic patient directory；
- read Glance/Timeline/Artifacts/Source/Comments/Task；
- create Nurse Consult；
- create/edit own-role staff note；
- create/reply/resolve Comment；
- create/transition 权限允许的 Task；
- 不允许 clinician note、doctor consult、clinician confirmation 或 patient-only action。

### DG2 — Nurse transcript contract

不得把 `NURSE` 静默映射为 `DOCTOR`。在以下方案中选择并记录：

1. 扩展公共 normalization contract，显式接收 `consult_type=doctor|nurse`；
2. 增加 Nurse-specific normalizer，同时复用共享解析 primitives；
3. E1 只接受已经确认的 strict `nurse|patient` segments，preview 留到 E4。

选择 1/2 若改变 D3 normalizer code/hash，必须保留原 frozen holdout labels、重跑全部 holdout，并建立新的版本化 runtime baseline；不得改 expected outcome 迎合实现。

### DG3 — Admin minimum surface

冻结 Admin 最小范围：

- list/create/review clinic invites；
- list clinic users 与 account status；
- disable/reactivate account（若实现，必须有 last-active-admin protection）；
- revoke active sessions；
- view clinic-scoped access/security audit metadata；
- 不加入 billing、appointments、medical analytics 或 cross-clinic console。

---

## 4. Nurse Consult Backend Contract

目标 endpoint：

```text
POST /api/patients/{patient_id}/nurse-consults
```

最低请求合同：

```text
consult_id
ingestion_key
started_at
ended_at
encounter_id?        # optional; only explicit identity groups a Clinic Visit
content.segments[]
  index              # continuous, zero-based
  speaker            # nurse | patient
  text               # trimmed, non-empty
```

持久化顺序：

```text
authorize staff in patient clinic
-> create nurse_consult Event
-> commit immutable Transcript Artifact first
-> redact before LLM
-> reuse the only LLMClient exit
-> create ai_nurse_consult_summary Artifact
-> create only exact-span-resolving Highlights
-> return explicit generation/fallback metadata
```

强制语义：

- Transcript `author_role=system`；
- AI Nurse Summary `author_role=system`、`artifact_type=ai_nurse_consult_summary`；
- Nurse/Staff formal supplement 使用 `staff_note`、`author_role=staff`；
- AI Summary 不创建或覆盖 Staff Note/Clinician Note；
- 相同 consult/ingestion replay 不重复创建 Event、Artifact 或 Highlight；
- raw Transcript 成功保存后 provider 失败不得回滚 raw source；
- failed span restore/anchor 丢弃 candidate，不 fuzzy match；
- staff 不得通过请求 body 选择 clinic、role、author 或 clinical authority。

---

## 5. Nurse/Staff Frontend

复用现有 `ClinicianWorkspacePage` 与 clinical shell，不创建复制版 Nurse App。

角色能力裁剪：

- 左栏继续显示真实登录身份与 Clinic Patients；
- 中栏继续使用 Glance、Timeline、Notes、Tasks；
- 右栏继续使用 Source、Comments、History/Audit；
- staff/Nurse 显示 `Record nurse consultation`，不显示 `Record doctor consultation`；
- Note Composer 默认且只能创建 staff-owned note；
- Glance review 文案继续区分 Staff acknowledgement 与 Clinician confirmation；
- unauthorized action 不仅隐藏按钮，直接 API 同样 403/404；
- patient switch、logout、session expiry 清除 Transcript draft、preview、selected Event、Source、Comment draft 与 pending response。

Nurse Consult UI 最低流程：

```text
Record nurse consultation
-> enter/paste nurse-patient transcript
-> review/resolve unknown segments
-> confirm
-> raw saved
-> AI Nurse Summary/fallback result
-> open new Event Detail
-> exact source / staff note / comment / task
```

---

## 6. Admin Backend Contract

优先复用现有 auth/invite/session/audit 模型，不创建另一套身份数据库。

建议最小 API：

```text
GET  /api/admin/users
PATCH /api/admin/users/{user_id}/status
POST /api/admin/users/{user_id}/revoke-sessions
GET  /api/admin/access-audit
```

所有 endpoint 必须：

- `require_auth`；
- `ctx.role == admin`；
- query 自动限制到 `ctx.clinic_id`；
- cross-clinic/nonexistent 使用统一 resource-not-found；
- response schema `extra=forbid`；
- 不返回 password hash、token hash、raw invite token、cookie、DB key 或 clinical text；
- mutation 写 metadata-only AuditLog；
- 使用 compare-and-set 或等价确定性策略处理并发 account/session mutation；
- 禁止 Admin disable 自己或最后一个 active Admin，除非另有明确恢复合同。

Admin 查看 patient data 若保留，只允许 PDF 所需 clinic oversight；E1 不新增临床 authoring endpoint，也不把 Admin 加入 `note_edit_action` 或 clinical Task transition 权限。

---

## 7. Admin Frontend

Admin 与 clinical workspace 的工作目标不同，允许使用独立 Admin route/shell，但复用视觉系统和身份组件。

最低页面：

```text
Admin Overview
├── Clinic identity and current admin
├── Users / account status
├── Invites
├── Sessions / revoke action
└── Access & security audit
```

页面要求：

- 不展示 clinical edit、AI drafting、Glance confirmation 或 Task completion 控件；
- destructive/access-changing action 需要明确 confirmation；
- loading、empty、error、forbidden、conflict 状态齐全；
- raw invite token 只在创建成功时一次显示，不进入 URL/log；
- clinic scope 与角色限制由后端证明，前端过滤不作安全边界。

---

## 8. 自动化测试

建议新增或扩展：

```text
backend/tests/test_nurse_consult_ingestion.py
backend/tests/test_nurse_workspace_rbac.py
backend/tests/test_admin_oversight_scope.py
backend/tests/test_admin_account_sessions.py
backend/tests/test_role_workspace_state_isolation.py
```

必须覆盖：

### Nurse/Staff

- staff 可创建同 clinic Nurse Consult；
- clinician/patient/admin 不通过该 endpoint 冒充 Nurse；
- cross-clinic 与不存在 patient 均为统一 404；
- Nurse Consult 创建新的 Event，不写固定 seed Event；
- strict speaker/index/time/unknown-field failures 为 422；
- Transcript raw-first、immutable、idempotent；
- AI Nurse Summary system-authored 且 exact provenance；
- provider failure 保留 raw 并明确 fallback；
- staff 不能写/edit clinician note 或产生 clinician confirmation；
- frontend staff journey 可达，且 patient/role switch 清状态。

### Admin

- admin 只看到本 clinic users/invites/audit；
- cross-clinic enumeration fail closed；
- admin response 不含 credential/token/clinical content；
- account status 与 session revoke 被审计；
- stale mutation 返回 deterministic conflict；
- non-admin 不能调用 oversight API；
- admin 不能 create/edit/revert clinical notes；
- admin 不能替临床角色推进 Task；
- last-active-admin protection（若实现）；
- frontend admin route 不出现 clinical authoring controls。

---

## 9. 文件边界

预期允许范围：

```text
backend/app/models.py                       # only if professional title/status support is required
backend/app/authz.py
backend/app/schemas.py
backend/app/api/auth.py
backend/app/api/sources.py
backend/app/api/audit.py
backend/app/api/admin.py                    # new if selected
backend/app/transcript_normalizer.py        # only after DG2
backend/seed/fixture.py                     # minimal synthetic role/demo additions
backend/tests/test_nurse_*.py
backend/tests/test_admin_*.py
frontend/src/App.tsx
frontend/src/api.ts
frontend/src/types.ts
frontend/src/pages/ClinicianWorkspacePage.tsx
frontend/src/pages/AdminInvitesPage.tsx
frontend/src/pages/AdminWorkspacePage.tsx   # optional new
frontend/src/components/NewNurseConsult.tsx # or shared parameterized component
frontend/src/index.css
```

不得顺手重构 Patient View、Copilot、D5 security、Glance scoring 或 unrelated visual styling。

---

## 10. Exit Gate — E1 Complete

1. Nurse/Staff 使用同一 clinical shell，未创建平行患者工作区；
2. staff 能创建一个新的 Nurse Consult 并得到 raw Transcript、AI Nurse Summary/fallback 与 exact source；
3. Nurse/Doctor Event 与 authority 始终分离；
4. Admin 能完成 clinic-scoped user/invite/session/audit oversight；
5. Admin 不能进行任何 clinical authoring/confirmation；
6. 所有角色/cross-clinic/不存在资源矩阵通过；
7. role/patient/session switch 无状态泄漏；
8. D3 frozen expectations 未被修改迎合实现；若 normalizer 变更，有新版本证据；
9. 全量 backend tests、frontend build、D3/D4 eval 与 D5 security regression 通过；
10. README/AGENTS/ATTRIBUTION 只在实现实际完成后更新。

---

## 11. 非目标与停止条件

非目标：独立 Nurse 数据库、完全复制 Nurse App、Admin clinical editor、跨 clinic super-admin、appointment/billing、真实 lab order、Voice/ASR、Self-Learning、Data Decay。

停止条件：

- 需要把 Nurse 当 Doctor 才能复用 pipeline -> 停止并修正合同；
- 需要前端 role/page 名称作为权限来源 -> 停止；
- Admin 必须获得 clinical authoring 才能完成页面 -> 停止；
- 为 Nurse input 修改 frozen expected outcomes -> 停止；
- 状态切换后可看到上一 patient/role 数据 -> 停止并修复后再继续。

---

## 12. Implementation Evidence（2026-08-27）

Decision Gates 冻结结果：

- DG1：Nurse/Staff 使用既有 `staff` RBAC role；`professional_title=Registered Nurse` 只作身份呈现；
- DG2：采用 Nurse-specific normalizer/preview，显式 `nurse|patient`，冻结 Doctor normalizer bytes/hash 完全不变；
- DG3：实现 users/invites/account status/session revoke/access audit 完整最小 surface，包含 self-disable 与 last-active-admin protection；
- Admin 不进入 clinical patient workspace；产品路由直接进入独立 oversight shell。

已实现：

- `POST /api/transcripts/nurse-normalize`：staff-only、无持久化/LLM、unknown/Doctor label fail closed；
- `POST /api/patients/{patient_id}/nurse-consults`：新 Event、strict canonical Transcript、raw-first、existing LLMClient/fallback、exact-anchor-only Highlights、幂等与统一 RBAC；
- shared clinical shell 的 Nurse/Staff identity、teal role accent、Nurse Consult workflow、explicit encounter selection 与 role/patient/session state isolation；
- `GET /api/admin/users`、`PATCH /api/admin/users/{user_id}/status`、`POST /api/admin/users/{user_id}/revoke-sessions`、`GET /api/admin/access-audit`；
- clinic-scoped explicit response projections、CAS account/session mutations、metadata-only audits、self/last-active-admin protection；
- 同一 Nightingale design system 下的 `AdminWorkspacePage`，包含 Overview、Users/Sessions、Invites 与 Access Audit，且无 clinical authoring controls。

观察到的验证结果：

- E1 新增 32 个 Nurse/Admin/frontend-contract tests；
- 当前完整 workspace backend suite：399 passed；E1 自身新增 32 tests，其他并发分支测试不计作 E1 产出；
- D3 40-case corpus validation/runtime hard gates PASS，Doctor normalizer SHA-256 仍为 `1ac0e01e92401b1728e7b938541e71f8d95e81cca137376004953eb2cd371476`；
- D4 frozen Copilot eval PASS；`pip check` 与 high-confidence secret scan PASS；
- frontend TypeScript/production build PASS，`git diff --check` PASS；
- local browser QA 完成 Clinician → Staff/Nurse → Nurse Consult preview/confirm/Event Detail → Admin Overview/Invites/Audit；console 0 warning/error；
- 无新增 dependency、provider、外部 dataset 或 attribution 条目；E2–E4 未由本卡推进。
