# M3 任务卡 — Collaboration + Revision + RBAC + Concurrency

> 对应：`Nightingale_72H_Development_Plan.md` Phase 3（§7）+ `AGENTS.md` M4/M5。
> 截止目标：**Milestone 3 — 最迟 2026-08-27 中午**。
> 前置状态：M2 已完成（27/27 pytest 绿，Glance → provenance → span 信任链可 demo）。
>
> ⚠️ **本阶段是全计划推理密度最高、时间窗最紧的一段。吃紧时立即启用滑期预案（§9），不得硬扛。**

---

## 1. 目标

把系统从"可追溯的信息查看器"变成真正的 shared care record：

- staff / clinician 能写自己的 note、互相评论、@提醒；
- 每次编辑有版本、可 diff、可 revert、可审计；
- 四角色权限**server-side 强制**，patient 通过 API 也拿不到 forbidden data；
- 并发编辑行为确定：不同 section 互不覆盖，同 section 冲突拒绝 stale write。

完成后 Scenario B 核心可演示。

---

## 2. 范围

### In Scope

- note 写接口：staff note / clinician note 的创建与编辑（M3 采用 role-owned section，精确定义见 §12）
- threaded comments + resolve / unresolve + `@mention`
- Revision：版本快照 + diff / view changes since X + revert
- AuditLog（metadata only）
- RBAC server-side enforcement（中间件 / 依赖注入，逐端点校验）
- 并发控制：`expected_version` 乐观锁，409 stale-write
- 三个 required tests：`test_rbac_scope.py` / `test_revision_history.py` / `test_concurrent_edits.py`
- 现有 M1/M2 读接口的权限收口：patient / event / artifact / glance / provenance / highlight status 全部纳入同一授权路径
- 最小 audit read API + UI，使 Scenario B 的 audit trail 实际可演示

### Out of Scope（明确不做）

- 真实认证 / 登录（继续 header 注入 role context）
- CRDT / 实时光标 / WebSocket 协作
- assignment / task 分派（滑期预案第 1 砍项）
- admin 专属 UI（保留 server-side admin scope 规则即可）
- Patient View 独立页面（M3 只做 patient role 的 **API 级过滤**，独立患者页面在后续阶段）

### M3 前置修正（必须先做）

- 当前 `role_context.py` 允许 `X-Role` 覆盖数据库角色，这在 M3 不能继续存在。`X-User-Id` 必须解析到真实 `User`，有效角色和 `clinic_id` 均以数据库记录为准；`X-Role` 只能作为 demo 一致性断言，缺失可接受，和数据库不一致则拒绝，绝不能用于提权。
- patient 身份必须能确定地映射到自己的 `Patient`。M3 在 `User` 增加 nullable `patient_id`（仅 patient role 使用），fixture 将 `usr_patient_01 → pat_001`；不能用姓名匹配，也不能把“同 clinic”误当成“本人”。
- 未提供/未知 user → 401；已认证但动作不允许 → 403；目标属于其他 clinic 或其他 patient → 404，统一隐藏资源是否存在。授权必须先于返回资源内容。
- 现有 fixture 中可编辑 note 的 `version=1` 必须补建初始 `ArtifactVersion` 快照；新建 note 也必须在同一事务创建 v1 快照，否则 v1 无法 diff / revert。

---

## 3. 数据模型新增

### Comment

```text
comment_id
anchor_type        -- event | artifact
anchor_id
parent_comment_id  -- null = 新 thread
author_id, author_role
body
mentions           -- JSON array of user_id
resolved           -- bool
created_at, resolved_at, resolved_by
```

- `anchor_id` 是多态引用，不靠数据库外键自动保证完整性；创建/读取时必须解析 anchor → Event → Patient/Clinic（Artifact anchor 先解析所属 Event）。
- reply 的 `parent_comment_id` 必须与子 comment 具有相同 anchor；mention 目标必须是同 clinic 的真实 staff/clinician user。mentions 只存储和展示，不触发通知。

### ArtifactVersion（快照策略）

```text
version_id
artifact_id
version            -- 递增整数，与 artifact.version 一致
content            -- 完整快照（选择 full snapshot，diff 读取时现算）
actor_id, actor_role
created_at
```

- `(artifact_id, version)` 必须唯一；
- 选 **full snapshots** 而非 diff 存储：实现简单、revert 零计算、72 小时尺度下数据量无忧；
- diff / "view changes since X" 在读取时先对 JSON content 做固定 key 排序和缩进序列化，再用 `difflib.unified_diff` 现算，确保输出稳定且可读；
- 创建 note = Artifact(v1) + ArtifactVersion(v1) + AuditLog，一个事务；
- 编辑 = `artifacts.content` 更新 + `version+1` + 追加 ArtifactVersion + AuditLog，四件事一个事务；
- revert 必须从目标快照复制内容并追加新版本；不得修改或删除任何旧快照。

### AuditLog

```text
audit_id
actor_id, actor_role
action             -- create_note | edit_note | revert | comment |
                      resolve | highlight_status | ...
target_type, target_id
from_version, to_version   -- 可空
clinic_id, patient_id, event_id
created_at
```

**metadata only**：不复制 raw clinical content 进 audit log。M2 的 `status_history` 权宜字段保留，但 highlight status 变更从此同时写 AuditLog（注释标明，Phase 7 feedback 读取以 AuditLog 为准）。

`patient_id` / `event_id` 是用于 scope enforcement 和 Event audit feed 的非内容型定位字段；comment / artifact / highlight action 都必须写入，避免通过多态 `target_id` 猜测所属患者。`GET /events/{event_id}/comments` 同时返回直接锚在 Event 和锚在其 Artifacts 上的 comments。

409 conflict 若要求写 AuditLog，必须在失败写事务回滚后用独立、明确的事务记录；不能先写后随业务事务一起回滚。Audit payload 只记录版本号/目标/actor，不记录 note 或 comment 全文。

---

## 4. RBAC 规则矩阵（server-side 唯一权威）

| 动作 | patient | staff | clinician | admin |
|---|---|---|---|---|
| 读 patient-facing summary / instruction | ✅ | ✅ | ✅ | ✅（本院） |
| 读 clinician note / staff note | ❌ | ✅ | ✅ | ✅（本院） |
| 读 raw AI-scribed note / transcript | ❌ | ✅ | ✅ | ✅（本院） |
| 读 internal comments | ❌ | ✅ | ✅ | ✅（本院） |
| 写 staff note | ❌ | ✅ | ❌ | ❌ |
| 写 clinician note | ❌ | ❌ | ✅ | ❌ |
| 编辑他人 role 的 note | — | ❌ | ❌ | ❌ |
| comment / resolve | ❌ | ✅ | ✅ | ❌ |
| highlight accept/reject/pin | ❌ | ✅ | ✅ | ❌ |
| 跨 clinic 任何访问 | ❌ | ❌ | ❌ | ❌ |

补充边界：

- patient 只可访问 `User.patient_id` 对应的本人记录，不可读取同 clinic 的其他患者；
- M3 现有类型中，patient 可见 artifact 仅明确包括 `patient_instruction`。不得把 `ai_*_summary`、`raw_conversation` 或 `transcript` 为了方便误标成 patient-facing；未来如需患者摘要，应新增明确的 patient-facing artifact type；
- Glance 是 clinician/staff 工作视图；patient 不得调用 glance、highlight provenance 或 highlight status API；admin 在本阶段只读 oversight，不执行 note/comment/highlight 写操作；
- patient 可读的 Event 列表中，`artifact_count` 必须按 patient 可见 artifact 计算，不能泄露隐藏 artifact 数量。

实现要求：

- 一个 `authorize(action, resource)` 依赖函数集中判定，禁止各端点各自手写 if；
- 每个 patient-scoped 查询强制同时验证 `clinic_id`；patient role 还要验证 `ctx.patient_id == resource.patient_id`；
- 同院但无动作权限返回 403；跨 clinic / 非本人资源一律返回 404；
- list endpoint 必须在查询层过滤不可见数据，不能先取出完整 ORM 对象再靠 response model 隐藏；direct resource endpoint 对不可见资源返回 404；
- UI 隐藏仅作 UX，测试必须直接打 API 验证拒绝。

---

## 5. 并发策略

- 所有可编辑 artifact 的写接口必须带 `expected_version`；
- `expected_version != 当前 version` → **409 Conflict**，返回当前版本号与最新内容摘要，不静默覆盖；
- 乐观锁必须使用单条条件更新（`WHERE artifact_id=? AND version=?` 并检查 affected row count）或等价的 atomic compare-and-swap；“先 SELECT 比较、再 UPDATE”不足以证明真实并发安全；
- 不同 section（不同 artifact / 不同 author-owned note）的并发写天然隔离，测试证明互不覆盖；
- 同 section 冲突的 deterministic strategy = reject stale write（可审计，AuditLog 记录 conflict 事件）。

---

## 6. API 契约（新增）

```text
POST   /api/events/{event_id}/notes
       body: { artifact_type: staff_note|clinician_note, content }
       -- author_role 取 role context，不许客户端伪造

PATCH  /api/artifacts/{artifact_id}
       body: { content, expected_version }
       -- 409 on stale; 403 on role 越权

POST   /api/artifacts/{artifact_id}/revert
       body: { to_version, expected_version }
       -- 产生新版本（revert 也是一次版本递增，不改历史）

GET    /api/artifacts/{artifact_id}/versions
GET    /api/artifacts/{artifact_id}/diff?since={version}
       -- unified diff 文本

POST   /api/comments            { anchor_type, anchor_id, parent_comment_id?, body, mentions? }
POST   /api/comments/{id}/resolve    /unresolve
GET    /api/events/{event_id}/comments
GET    /api/events/{event_id}/audit
```

所有端点（包括 M1/M2 已有 read/status endpoints）都过统一授权。patient 对本人 Event 的可见列表使用查询级过滤；patient 调 comment / revision / audit / glance / provenance / highlight status 等内部端点 → 403，同 clinic 之外或非本人目标 → 404。

---

## 7. 前端

- **Note 编辑**：clinician / staff 各自 note 的编辑框，保存时带 `expected_version`；409 时提示"他人已修改，刷新后重试"并展示当前版本；
- **Comment 线程**：锚在 Event 或 Artifact 上，支持回复、resolve/unresolve、同 clinic staff/clinician 的 `@` mention 下拉；
- **Revision UI**：版本列表 + 选择两版本出 diff（最简前后对照即可）+ revert 按钮；
- **Audit UI**：在 Event detail 内展示 metadata-only activity list（actor / action / time / target / version），不展示原始 clinical content；
- **Role 切换器**保留，切换后 patient 应看到内部内容**从 API 层面消失**（不是前端藏）。

---

## 8. 任务分解（串行，每步一个 commit）

| # | 任务 | 难度 | 产出 |
|---|------|------|------|
| 1 | User→Patient 映射、三张新表、v1 快照/backfill + note 创建接口 | L3 | 身份与 revision 基线成立 |
| 2 | **可信 role context + RBAC authorize + 全部新旧端点接入** | **L4** | 角色不可伪造，规则矩阵逐条生效 |
| 3 | **版本 + revert + diff + 乐观锁 409** | **L4** | 编辑链路完整可审计 |
| 4 | `test_rbac_scope.py` | **L4**（断言即规格） | required test 1 |
| 5 | `test_revision_history.py` + `test_concurrent_edits.py` | L3 | required test 2、3 |
| 6 | 前端：编辑 / 评论线程 / revision / audit UI | L2 | Scenario B 核心可走 |
| 7 | 四角色人工走查 + AGENTS 状态更新 | L1 | 验收签字 |

任务 2、3、4 是本阶段核心，建议放在精力最好的时段连续完成，中间不插别的任务。

---

## 9. 滑期预案（预先批准，来自开发计划 Phase 3）

如需砍 scope，严格按此顺序：

1. ~~assignment / task 分派~~（本任务卡已直接排除）；
2. diff UI 简化为最朴素的前后版本对照（保留 `GET .../diff` 数据能力）；
3. admin 角色专属 UI（保留 server-side admin scope 规则）。

**不得砍**：server-side RBAC、version / revert、concurrency 确定性策略、三个 required tests。

---

## 10. 测试要点（断言即规格，逐条对照 brief）

### `test_rbac_scope.py`

- staff 不能创建/编辑 clinician note（403）；
- clinician 不能创建/编辑 staff note（403）；
- `X-User-Id=usr_patient_01` 搭配 `X-Role=clinician` 不得提权；未知/缺失 user 不得访问受保护资源；
- patient 只能访问映射到本人的记录，同 clinic 另一患者也必须拒绝；
- patient 调 internal comments endpoint → 403；
- patient 的 artifact list 中不得出现 raw AI-scribed note / transcript；若增加 direct artifact read，则对这些不可见资源返回 404；
- patient 的 artifact list 只含 allowlist 类型，且 `artifact_count` 不泄露隐藏数量；
- patient 不能读取 glance / provenance，不能变更 highlight status；
- 跨 clinic 资源统一表现为 404；
- 全部直接打 API，不经过 UI。

### `test_revision_history.py`

- 编辑后 version +1 且旧版本仍可读；
- fixture / 新建 note 都存在 version 1 快照；
- revert 后内容回到目标版本（且自身产生新版本）；
- stale `expected_version` 的 revert 同样返回 409；
- AuditLog 记录 actor / action / time / target（metadata only，不含全文）。

### `test_concurrent_edits.py`

- staff 编辑 staff note + clinician 同时编辑 clinician note → 两者都保留；
- 同 artifact 两个 expected_version=3 的写 → 第一个成功（v4），第二个 409；
- 409 事件进 AuditLog。

测试隔离要求：当前测试数据库是 session-scoped，M3 的写测试不得依赖执行顺序。每个测试必须通过重建/重 seed、事务回滚或等价机制获得确定的初始状态。

---

## 11. 验收（Exit Gate）

1. 人工走一遍四角色行为（含 patient 直接 curl 内部端点被拒）；
2. 三个 required tests 全绿，且全部 pytest 无回归；
3. Scenario B 链路可演示：staff note → `@clinician` comment → clinician 编辑 plan → version+1 → diff → revert → audit trail 可见。
4. 明确做一次 header 提权负测、同 clinic 非本人访问负测、跨 clinic 负测；结果分别符合上文状态码与不泄露规则。

**如果 Patient 能通过 API 拿到 forbidden data，即使 UI 隐藏成功，也判定失败。**

---

## 12. 风险与注意

- **authorize 集中实现**是防止 RBAC 漏洞发散的关键，review 时只认这一个函数；
- `X-Role` 不是权限来源；数据库 User 才是权限来源。demo role switcher 仍可发送匹配 header，但后端必须校验而非信任；
- revert 语义 = 追加新版本，**不删历史**——测试和 UI 都要体现这一点；
- note ownership 在 M3 定义为同 clinic 的 role-owned section：staff 只能编辑 `staff_note`，clinician 只能编辑 `clinician_note`；保留原始 `author_id`，实际修改者写入 Version/Audit。不得把跨 role 编辑伪装成新作者；
- comment 的 `mentions` 只做存储和展示，不做通知系统；
- 编辑接口必须拒绝客户端传 `author_role`，作者身份只能来自 role context；
- demo 前重新 seed（当前 dev 库里 highlight status 被手动测试改过）；
- 时间吃紧先看 §9，不要牺牲测试换 UI。
