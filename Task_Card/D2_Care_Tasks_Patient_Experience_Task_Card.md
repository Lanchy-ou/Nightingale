# D2 任务卡 - Care Task Lifecycle + Patient Experience

> 状态：**COMPLETE（2026-08-27）**
>
> 对应总计划：`docs/phase_d_product_completion_plan.md`
>
> 本卡有意把 Task 与 Patient Experience 合并：患者页面必须消费真实照护行动，不能继续展示无状态的 pending 文本。

---

## 1. 目标

把当前“可阅读的记录”扩展为“可推进的照护工作流”：

```text
Clinician/Staff creates task
-> Patient sees authorized action
-> Patient reports done
-> Clinic verifies completion
-> Glance/Patient View update
-> Full audit and provenance remain
```

同时把 Patient View 重构为 `Today | Care Plan | Check-in | Visit Summaries`，不复制临床工作区。

---

## 2. Task 状态机

```text
open -> in_progress -> reported_done -> completed
  \          \              \
   ---------- cancelled <----
```

允许的最小转换：

| From | To | Actor |
|---|---|---|
| open | in_progress | assigned staff/clinician，或被分配 patient |
| open/in_progress | reported_done | assigned patient；staff/clinician 也可代报并记录 actor |
| reported_done | completed | staff/clinician |
| open/in_progress/reported_done | cancelled | staff/clinician |

禁止从 completed/cancelled 恢复；如需恢复，创建带 provenance 的新 Task，保留原历史。

---

## 3. 最小数据模型

```text
Task
  task_id
  patient_id
  clinic_id
  event_id                 # required origin event
  source_artifact_id       # optional when no exact artifact
  source_span              # optional but resolvable when present
  title
  description
  assigned_role            # patient|staff|clinician
  assigned_user_id         # optional for role queue
  patient_visible
  status
  due_at
  created_by
  created_at
  updated_at
  reported_done_at
  completed_by
  completed_at
  cancelled_by
  cancelled_at
```

状态历史必须进入 AuditLog；如果选择独立 `TaskStatusHistory`，需说明它与 AuditLog 的职责，不能维护两套相互矛盾的权威历史。

---

## 4. Backend 范围

最小端点：

```text
POST /api/events/{event_id}/tasks
GET  /api/patients/{patient_id}/tasks
POST /api/tasks/{task_id}/transition
```

要求：

- transition 接收 `expected_status`，原子条件更新；stale write -> 409；
- scope 检查先于 Task 内容/状态分支；
- patient API 只投影 patient-visible 且属于自己的 Task；
- patient 看不到 internal description、assignee metadata 或审计字段；
- patient 不能创建、完成、取消或重分配 Task；
- clinician/staff 不能跨 clinic 操作；
- Task provenance resolver 能回 Event，存在 artifact/span 时必须精确解析；
- Glance scoring 的 `unresolved_task` 来自真实未终结 Task，不再 seed 固定 false；
- Task completed/cancelled 后，Glance write path 确定性更新；
- Patient aggregate 只引用明确的 Task/Instruction，不从 clinician note 猜患者行动。

---

## 5. Patient UI 范围

### Today

- 当前 clinician-authored patient instruction；
- 最近到期/逾期的 patient-visible Task；
- next follow-up；
- 清晰的 empty/error/loading 状态；
- 不展示内部 importance score 或 clinical risk reasoning。

### Care Plan

- Open/In progress/Reported done/Completed 分组；
- 药物和检查只来自 patient-facing instruction/Task；
- Patient 对自己的 Task 可执行 Start/Report done；
- Report done 后明确显示“等待诊所确认”，不能伪装 completed。

### Check-in

- 保留患者 AI session，但增加提交前说明、发送状态、失败重试；
- patient input 创建 raw conversation Event，derived AI 仍对 patient 隐藏内部 id；
- check-in 不直接修改 clinician note 或 Task。

### Visit Summaries

- 只显示明确 patient-facing 的 summaries/instructions；
- 按 Event.started_at 排序；
- 不展示 raw transcript、internal comments、AI clinical summary、audit/version。

---

## 6. Clinician/Staff UI 范围

- Patient workspace 新增真实 Tasks view/section，不展示假 appointment/assignment；
- 从 Event/Artifact 可创建 Task，并显示来源；
- staff/clinician 可推进允许的状态；
- reported_done 显示需要 clinic verification；
- Glance item 能说明 unresolved Task 的原因并跳到 Task/source；
- staff 复用 clinic shell 的 Task 能力，不创建独立 Nurse Workspace。

---

## 7. 必须测试

建议新增：

```text
tests/test_task_lifecycle.py
tests/test_task_rbac_scope.py
tests/test_task_provenance.py
tests/test_patient_task_projection.py
tests/test_task_glance_integration.py
```

覆盖：

- 合法/非法状态转换；
- patient 只能操作自己的 patient-visible assigned Task；
- patient 只能 reported_done，不能 completed/cancelled/reassign；
- clinician/staff 同 clinic 权限与跨 clinic 404；
- expected_status stale transition -> 409；
- completed/cancelled 不可恢复；
- create/transition audit metadata 完整且无 raw content；
- provenance Event/Artifact/span 可解析，错误 span fail closed；
- unresolved Task 进入 Glance，终结后确定性退出/降权；
- patient response exact key allowlist 与 sentinel leak scan；
- patient 前端不调用 clinical tasks/comments/audit endpoints；
- session/patient switch 清空 Task drafts/pending responses；
- 全部 M3/M6/Glance tests 零回归。

---

## 8. Exit Gate - D2 Complete

1. clinician/staff 能从真实 Event 创建可追溯 Task；
2. patient 登录后能理解并推进自己的 Task；
3. patient report done 与 clinic completed 权威明确分离；
4. Task 状态真实影响 Glance 与 Patient Today/Care Plan；
5. Patient View 四区可完成一条端到端 journey，且没有 internal data leak；
6. 并发 transition 有确定 409，不静默覆盖；
7. 新 tests、全量 tests、frontend build 全绿；
8. canonical fixture 展示至少一个 open -> reported_done -> completed 的纵向故事。

---

## 9. 非目标与停止条件

非目标：appointment scheduling、真实 lab order、billing、复杂 care-team assignment、Task recurrence、notification provider、patient-to-clinician direct chat。

停止条件：

- 用 Comment/Highlight 冒充 Task -> 停止；
- patient 能直接完成临床确认事项 -> 停止；
- Task 没有 Event 来源或跨 clinic scope -> 停止；
- 为 Patient UI 方便而返回完整 Artifact/Audit -> 停止并改成显式 projection。

---

## 10. Implementation Evidence（2026-08-27）

- 一等 `Task` 表、状态机与 API 已实现于 `backend/app/models.py`、`backend/app/tasks.py`、`backend/app/api/tasks.py`；`event_id` 必填，Artifact/Span 必须成对出现并通过严格 in-bounds resolver。
- transition 使用 `UPDATE ... WHERE task_id=? AND status=?`；`expected_status` stale write 稳定返回 409。`completed|cancelled` 无出边，恢复只能新建 Task。
- server-side 权限集中在 `backend/app/authz.py`；scope 先于 body/status/assignment/provenance 分支。patient 只可操作本人、patient-visible、assigned-patient Task，并且只能 Start/Report done。
- `AuditLog.details` 是 Task 状态历史的唯一权威来源，只记录 metadata；create/transition/conflict 不复制 title/description 或原始临床内容。
- `unresolved_task` 在 Task create/transition 写路径按 Event/Artifact/Span 精确匹配并重算 Highlight score；Glance read path 保持零计算、零 LLM。
- Patient aggregate 已重构为 `Today | Care Plan | Check-in | Visit Summaries`，Task 使用显式 allowlist；staff 与 clinician 共用 clinic shell 的 Care Tasks 能力，没有新增 Nurse Workspace。
- canonical fixture 包含一个当前 open blood-test Task，以及一个 `open -> reported_done -> completed` symptom-diary 故事（AuditLog 保留全历史）。
- 新增 5 个 D2 测试文件、23 个测试；backend 全量 **245 passed**，frontend TypeScript/Vite production build 通过。本地浏览器 QA 覆盖 patient report done → clinic verify → Glance refresh 与 staff shell，console 无 error/warn。
- 未实现且未冒充：appointment、lab order、billing、recurrence、notification provider、patient direct chat。D3/D4/D5 未开始。
