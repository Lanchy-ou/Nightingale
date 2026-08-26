# M6 任务卡 — Patient View（患者视图）

> 对应：`AGENTS.md` §4.3 Patient View + §7 RBAC patient 规则 + §12 Build Order 的 Patient View 硬门 + §16 完成定义 #6；`Nightingale_72H_Development_Plan.md` Milestone 5 排期建议。
> 前置状态：M5 / Longitudinal Demo Data Complete（118/118 pytest 绿；Event 5 clinician review 落库，`patient_instruction` 已有更新版内容）。
> 目标工期：**0.5–1 天**。这是 Core Complete 前最大的剩余硬门。
>
> **编号说明**：项目任务卡沿用实际执行序号，因此本卡称 M6；它实现的是 `AGENTS.md` Build Order 中尚未完成的 **Patient View** 硬门，不是重复实现已经在项目 M4 完成的 AI Flow。
>
> **阶段边界说明**：本卡只做 Patient View 及其服务端可见性合同。性能测量、自学习、demo 视频、Technical Brief 不在本卡内。M6 通过后仍须 M7（性能 + 硬化）与 Milestone 6（交付物）全部完成才可声明 Core Complete。

---

## 1. 目标与成功定义

为 patient 角色提供一个**独立的、最小信息的**患者视图，使用户 UX 测试成立：

> 患者打开页面，能看懂“我现在该做什么、接下来什么时候复诊、怎么和 AI 助手交流”，且看不到任何内部临床工作区内容。

成功必须同时满足：

- patient 角色登录后进入独立 Patient View 页面，**不是**临床工作区的删减版，而是独立页面 + 独立只读 API；
- 页面只含四类内容：医生确认的患者说明、下一步/复诊安排、康复指导、患者 AI 交互入口；
- 服务端强制过滤：任何内部 clinician note、staff note、原始 AI 临床摘要（`ai_*_summary`）、Highlight、内部 comment、provenance 内部结构都**不出现在任何 patient 可见响应体中**；
- 越权访问他人患者记录保持统一 404（沿用 M3 合同，不泄露存在性）；
- 前端角色切换到 patient 时整树 remount（沿用 M3 约定），临床工作区状态不可残留；
- 118 个既有测试零回归。

---

## 2. 范围

### In Scope

- 新增只读聚合端点 `GET /api/patients/{patient_id}/patient-view`；
- patient-facing summary 采用**读取时的确定性投影**：从最新 `patient_instruction` 的白名单字段形成 `current_summary`，保留 `source_artifact_id/event_id`；不新建第二份 summary Artifact，不调用 LLM，不复制内部 clinical note；
- `PATIENT_VISIBLE_ARTIFACT_TYPES` 继续保持 `{"patient_instruction"}`，不扩大既有通用 artifact API 的 patient 可见类型；
- 前端 `PatientViewPage`（patient 角色路由）+ 患者 AI 会话入口（复用 M4 `POST /patients/{id}/sessions`）；
- patient-view 专属 RBAC / 字段泄漏测试；
- README Patient View 段落回填。

### Out of Scope（不得顺手实现）

- Task 表 / task completion workflow（待办只从 `patient_instruction` 内容展示，不建模型）；
- 新 `patient_summary` Artifact、patient-summary 生成/审批/再生成端点；
- 为 Patient View 新增 LLM 调用、prompt、fallback 或 generation metadata；患者 AI 交互只复用既有 session API；
- patient 对 clinician/staff 的任何消息/评论通道；
- 患者账号体系、登录认证（继续 demo-only role context，服务端 RBAC 才是真边界）；
- 性能测量（M7）、自学习（Phase 7）、Voice capture；
- 患者可见的通知/推送；
- 多患者切换 UI（demo 固定当前 patient）。

---

## 3. API 与可见性合同

### 3.1 端点

```text
GET /api/patients/{patient_id}/patient-view
```

- 在 centralized `PERMISSIONS` 新增 `read_patient_view`，只授予 patient；端点必须调用统一 `authorize`，不得另写一套前端/端点角色判断充当安全边界；
- scope 检查先于 permission：资源不存在、跨 clinic、patient 非本人统一 404 body；同 scope 的 staff/clinician/admin 因 action 未授权返回 403，符合 M3 全局语义；无身份返回 401；
- 响应体与每个嵌套对象都使用专属 Pydantic response schema 和显式字段构造，禁止直接返回 `Artifact.content` 整个 dict；
- **禁止**出现：`highlight_ids`、`review_status`、`importance_score`、`feature_flags`、`entity_key`、`provenance_pointer`/span、comment、audit、version、author_id、generation metadata 或任何 internal note 字段。

冻结响应形状（顶层与嵌套字段不得擅自增删；专属 schema 应拒绝额外字段）：

```text
{
  patient_id,
  display_name,
  current_summary: {                  # 最新 patient_instruction 的安全投影；没有则为 null
    source_artifact_id,
    event_id,
    event_time,
    instruction,
    follow_up?
  } | null,
  instructions: [ {
    artifact_id,
    event_id,
    event_time,
    instruction,
    follow_up?
  } ],
  upcoming: [ {                        # 只投影 content.follow_up 的非空字符串
    source_artifact_id,
    event_id,
    event_time,
    kind: "follow_up",
    text
  } ],
  sessions: [ {
    event_id,
    event_type,
    started_at,
    ended_at?
  } ]
}
```

排序与缺失值合同：

- `current_summary` 取 `Event.started_at` 最新的 patient instruction；同一 Event 多条时以 `Artifact.created_at` 决定最新，再以 `artifact_id` 稳定打破平局；
- `instructions` 按 `event_time` 倒序；`upcoming` 按 `event_time` 倒序；`sessions` 按 `started_at` 倒序；所有排序都必须有稳定 ID tie-breaker；
- `upcoming` 只接受 `patient_instruction.content["follow_up"]` 的非空字符串，不从自由文本推断 task/date，不把 UNKNOWN 变成具体安排；
- session 只包含本 patient 且有本人 `raw_conversation` 的 `patient_ai_preconsult|patient_followup` Event；当前模型没有持久化 processing status，因此响应**不返回也不伪造 `status`**；
- 没有 instruction/session 时返回空数组或 `current_summary=null`，响应顶层 key 保持稳定，不按结果省略字段。

### 3.2 既有端点复核

- `GET /patients/{id}`、`GET /patients/{id}/events`、`GET /events/{event_id}/artifacts` 继续保留 M3 已测试的 patient 过滤合同；M6 前端不调用这些临床浏览端点，但不能以“前端不用”为理由放松服务端过滤；
- M4 session 响应的 patient 侧形状（无内部 id）保持不变，不得在本卡回退。

---

## 4. Patient-facing projection 合同（防泄漏核心）

`ai_patient_session_summary` / `ai_*_consult_summary` 是**内部临床 AI 摘要**，患者永远不可见。M6 不新增另一份 AI summary，而是把 clinician 已确认可给患者看的 `patient_instruction` 投影成最小响应：

```text
patient_instruction Artifact
  ├─ allow content.instruction: non-empty string
  └─ allow content.follow_up: optional non-empty string
          ↓ explicit field projection only
PatientView current_summary / instructions / upcoming
```

规则：

1. 来源只允许 `artifact_type=patient_instruction`，且 Artifact/Event/Patient 三层关联必须一致；`content.instruction` 不是非空字符串时整条跳过，不能拿其他字段兜底；
2. 只复制 `instruction` / `follow_up` 两个允许字段；未知 key 即使后来被写入 instruction content，也不得自动出现在 patient-view；
3. `current_summary` 只是最新 instruction 的 read projection，不另行落库，不宣称 AI 生成，不产生新的事实、诊断解释、风险分析或鉴别推理；
4. 保留 `source_artifact_id/event_id/event_time` 便于内部审计，但不向 patient 返回 span、内部 provenance chain 或作者内部元数据；
5. 无 instruction 时返回 `current_summary=null`、空 instructions/upcoming；绝不从 clinician note、staff note、transcript、AI summary、Highlight 或 comment 倒推；
6. Patient AI 会话是独立交互能力：复用 M4 session ingestion，并继续把生成的 `ai_patient_session_summary` 视为内部 Artifact，不混入 Patient View 响应。

---

## 5. 前端设计

### 5.1 路由

- `role=patient` → `PatientViewPage`；其他角色 → 既有 `PatientPage` 临床工作区；
- 角色切换继续整树 remount（`key={roleKey}` 约定），patient 视图卸载后临床面板状态不得残留，反之亦然。

### 5.2 页面区块（自上而下，患者语言）

1. **你现在需要知道的事**（current_summary：最新医生 instruction 的患者安全投影）；
2. **你的下一步**（upcoming：只显示明确存在的 follow_up 字段；检查/服药要求直接显示 instruction 原文，不做 NLP 推断）；
3. **医生给你的说明**（instructions，按 Event 时间倒序，标注日期）；
4. **和 AI 助手说说你的情况**（会话入口 + 本人历史 session 日期/类型列表；不显示不存在的 processing status）。

### 5.3 硬约束

- `App` 在 role 层直接二选一渲染：patient → `PatientViewPage`，其他角色 → 既有 `PatientPage`；不能先挂载临床页再用 CSS 隐藏；
- patient 视图初始加载只请求 patient-view；提交会话时只额外请求既有 sessions POST，成功后刷新 patient-view；不请求 patient/events/artifacts/glance/highlights/comments/audit/revisions；
- 浏览器网络面板走查：patient 角色下不得出现对内部端点的请求（demo 时可现场展示）；
- 文案用第二人称、无医学术语堆砌；内部字段（score、status、entity_key）永不渲染。

---

## 6. RBAC 与测试矩阵

### 新增 `test_patient_view.py`

- patient 访问本人 patient-view → 200；顶层 key 与所有嵌套 key 必须与 response schema **精确相等**，不能只检查允许字段是子集；
- 响应体序列化后**全文扫描**：不含任何 `ai_` summary 内容片段、staff/clinician note sentinel、comment sentinel、highlight 字段名（`risk_reason`/`importance_score` 等不出现在 JSON key 中）；sentinel 只放测试 fixture，不把真实/推断临床内容写进断言；
- patient 访问他人 patient-view → 404，body 与跨 clinic 404 完全一致；
- staff / clinician / admin 对同 clinic patient-view → 403；跨 clinic 仍为统一 404；无身份 → 401；
- 无 `patient_instruction` 时 `current_summary=null` 且 instructions/upcoming 为空；不得读取 clinician note 兜底；
- 在 `patient_instruction.content` 注入一个未知 sentinel key，断言 patient-view 不返回该 key/value，证明不是原样序列化 content；
- `current_summary` 必须来自最新 Event 的 instruction；同一 Event 多条时按 Artifact.created_at + artifact_id 稳定选择；
- upcoming 只投影非空 `follow_up`；不存在/非字符串时不编造；
- session 列表只含本人 patient session Event，顺序稳定；不含 `status`、`ai_summary_artifact_id`、`highlight_ids`；
- patient 角色直接请求既有 events/artifacts endpoint 仍只见 M3 白名单范围，artifact count 不泄漏内部数量；
- session POST 后 patient-safe 响应保持收敛，新 session 出现在下一次 patient-view GET 中。

### 回归

- 全部既有测试零回归（重点：`test_rbac_scope.py`、M4 ingestion patient 响应形状、`test_seed_integrity.py`）；
- fixture 不新增 patient_summary Artifact；`test_seed_integrity.py` 只需继续证明 Event 3/5 的 patient_instruction 存在、作者为 clinician、字段满足 projection schema；
- frontend TypeScript/Vite build 通过。

---

## 7. 任务分解（串行，每步一个 commit）

| # | 任务 | 验证 |
|---|---|---|
| 0 | baseline：确认 M5 收尾 commit 已在历史中；全量 pytest + frontend build | 118+ 测试绿；build 通过；工作区只含 M6 预期改动 |
| 1 | 专属 response schemas + centralized `read_patient_view` action | schema key 集与 401/403/404 合同测试先行 |
| 2 | `GET /patient-view`：instruction projection、latest summary、upcoming、sessions 与稳定排序 | `test_patient_view.py` 全绿；无 raw content dict 返回 |
| 3 | 既有 patient endpoints 回归审查；只有测试证明泄漏时才收紧 | `test_rbac_scope.py` 回归绿；不做无证据重构 |
| 4 | 前端 `PatientViewPage` + role-level 二选一路由 + remount | build 通过；patient 初始加载只请求 patient-view |
| 5 | 患者 AI 会话入口复用既有 sessions API | POST 响应安全；刷新后新 session 出现在 patient-view |
| 6 | README 回填 + AGENTS.md §19 追加 M6 状态 + 全量回归 | 118+ 测试绿；`git diff --check`；文档一致 |

---

## 8. Exit Gate — Patient View Complete

1. patient 角色打开页面，不看任何解释即可回答：“下一步做什么、什么时候复诊”；
2. 页面 + 网络请求双重验证：无任何内部临床内容泄漏；
3. 患者 AI 会话可发起、可看到本人历史 session 日期/类型；不存在的状态不显示、不伪造；
4. `current_summary`/instructions/upcoming 的来源合同被 exact-key 与 sentinel 泄漏测试锁定；
5. 非本人 / 跨 clinic / 非 patient 角色访问均被正确拒绝且不泄露存在性；
6. 118+ 全量测试、frontend build、`git diff --check` 全绿；浏览器网络走查结果记录在 README 或 M6 验收报告。

通过后只可声明：

> **M6 / Patient View Complete**

---

## 9. 停止条件与风险

- 需要从 clinician note 倒推患者说明才能凑内容 → 停止，改为 `current_summary=null`；
- 需要把 `Artifact.content` 原样返回才能省代码 → 停止，使用显式字段投影；
- 想增加 patient_summary Artifact/LLM 调用来改善文案 → 越界，保留给 core gates 之后另行评估；
- 为页面好看而引入 Task 表 / 审批流 / 通知 → 越界，停止；
- patient-view 响应需要暴露 highlight 或 score 才能排序 → 越界，改为按 Event 时间倒序；
- 收紧既有端点导致 M3/M4 测试变红 → 先确认是否有可复现泄漏；没有泄漏证据则不改既有行为；
- 距 Milestone 6 不足 8 小时时本卡未完 → 砍掉 §5.2 第 3、4 区块之外的全部修饰，优先保证 API 合同 + 测试。

---

## 10. 后续阶段预警

M6 之后剩余硬门：

- **M7 — Performance + Core Hardening**（开发计划 Phase 6）：warm-path Glance P95 ≤ 300 ms 测量方法与结果，写入 Technical Brief；
- **Milestone 6（截止前 8–10 小时 feature freeze）**：Technical Brief（含架构图、schema 映射、trade-offs）、demo video（Scenario A/B/C）、`ATTRIBUTION.txt` 核对、最终打包与邮件提交；
- Bonus（self-learning / voice / data decay）：仅在 M7 + 全部 required tests 绿之后启动，永不阻塞 MVP。
