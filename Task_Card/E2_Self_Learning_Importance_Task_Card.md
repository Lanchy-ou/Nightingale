# E2 Task Card — Self-Learning Importance

> 状态：**PLANNED — IMPLEMENTATION NOT STARTED**
>
> 对应总计划：`docs/phase_e_capability_enhancement_plan.md`
>
> 依赖：E1 role/authority matrix 冻结；当前 Glance/provenance baseline 全绿。

---

## 1. 目标

实现 PDF Bonus 所要求的最小、真实、可解释 Self-Learning 闭环：

```text
explicit review of an AI-derived Highlight
-> metadata-only feedback
-> bounded clinic-level preference
-> future similar Highlight gets changed priority
-> exact provenance and clinical safety remain intact
```

Self-Learning 学习 Glance 的软排序偏好，不学习 Summary 写法、诊断、处方或临床事实。

---

## 2. 成功定义

必须区分以下两个行为：

```text
Pin current Highlight
-> current row appears first                     # existing behavior

Pin/Confirm/Reject a type of Highlight
-> a future similar candidate gets adjustment   # E2 learning behavior
```

如果系统只完成第一种，不得称为 Self-Learning。

---

## 3. 开工 Decision Gates

### DG1 — Learning scope

第一版固定为 clinic-scoped：

- 不跨 clinic；
- 不做全局 learning；
- 不做 per-user model（数据过少且不稳定）；
- patient interaction 不训练 clinical ranking；
- Admin oversight action 不训练 clinical ranking。

### DG2 — Similarity key

第一版优先使用受控 `entity_type`：

```text
symptom | medication | task | risk | allergy | follow_up | other
```

不得直接使用 raw text、患者姓名或自由生成 embedding 作为 learning key。若现有 extraction entity types 不完整，必须先冻结 allowlist 与 `other` 的 fail-safe 行为。

### DG3 — Feedback signals

第一版直接改变权重的信号仅限：

- `pinned`：强正向；
- `accepted`：中等正向；
- `rejected`：负向。

Comment/Edit 只记录为观察信号，不直接改变 weight。原因：Comment 可能是纠错，Edit 可能代表 Summary 质量差，不能自动解释为“更重要”。

### DG4 — Adjustment caps

冻结简单整数与限幅，例如：

| Signal | Clinician | Staff/Nurse |
|---|---:|---:|
| accepted | +1 | +1 |
| pinned | +2 | +1 |
| rejected | -1 | -1 |

建议总 adjustment 限制在：

```text
-2 <= adaptive_adjustment <= +3
```

实际常量必须写入透明代码和 Technical Brief，不从 provider 或前端传入。

---

## 4. 数据模型

新增 append-only metadata table，例如 `importance_feedback`：

```text
feedback_id
highlight_id
clinic_id
actor_id
actor_role
feedback_key       # controlled entity_type
status             # accepted | pinned | rejected
signal_value
created_at
```

要求：

- 不保存 Highlight text、risk_reason、quote、Comment body 或 Artifact content；
- FK/ownership 可追溯到原 Highlight；
- cross-clinic feedback 不可聚合；
- 只有成功的 Highlight status compare-and-set 后才能写 feedback；
- status no-op 和 409 conflict 不产生 feedback；
- 保留全部事件用于 audit，但计算时每个 `(actor_id, highlight_id)` 只取最新有效反馈，防止 toggle inflation。

Highlight 增加或明确区分：

```text
base_importance_score
adaptive_adjustment
decay_adjustment      # E3 reserved, default 0
importance_score      # final stored score
learning_metadata     # counts/reason only; no clinical text
```

数据库迁移/重建策略必须兼容 SQLite tests 与 SQLCipher Demo。不得只依靠 `create_all` 假装旧 DB 自动迁移。

---

## 5. Learning Service

新增单一 domain module，例如：

```text
backend/app/importance_learning.py
```

职责：

1. 将 authorized status transition 转换为 feedback event；
2. 解析每个 actor/highlight 的 latest effective signal；
3. 聚合同 clinic、同 feedback key 的 signal；
4. 应用 role weight 与 cap；
5. 返回 `adaptive_adjustment + explanation metadata`；
6. 不读取其他 clinic；
7. 不调用 LLM/provider/network；
8. 不修改 raw Artifact、Task、Note 或 provenance。

写入新 Highlight 时：

```text
base = current deterministic compute_score(flags)
adaptive = learning_service.adjustment(clinic_id, entity_type)
decay = 0  # until E3
final = base + adaptive + decay
```

Clinician accept/pin 对当前 row 的 `clinician_confirmed` 逻辑保留，但重算 final score 时不得覆盖已有 adaptive/decay adjustment。

---

## 6. Hard Safety Rules

Self-Learning 永远不能：

- 删除或改写 Highlight fact；
- 生成新的 clinical assertion；
- 让 staff action 成为 clinician confirmation；
- 降低 hard-risk/unresolved/needs-review 项的最低保护；
- 把 rejected feedback 应用于其他 clinic；
- 修改 Task status；
- 使缺少 exact provenance 的 candidate 进入 Glance；
- 在 GET Glance 时做全历史聚合或 LLM call。

建议对以下类型设置 adjustment floor 或保护：

```text
explicit_risk
unresolved_task
clinician_confirmed
status == pinned
review_status == needs_review
```

具体保护必须用测试锁定，不只写注释。

---

## 7. API 与 UI

继续复用：

```text
POST /api/highlights/{highlight_id}/status
```

不允许前端提交 `signal_value`、`adaptive_adjustment`、`feedback_key` 或 score；全部由服务器从 DB Highlight 与 RoleContext 派生。

`HighlightOut` 可新增：

```text
base_importance_score
adaptive_adjustment
decay_adjustment
learning_metadata
```

UI 仅在非零调整时显示简短解释，例如：

```text
Learned priority +2
Based on 3 clinic reviews of similar symptom items
```

禁止显示其他患者、actor identity、原始评论或受保护文本。Review help 必须说明：feedback 只影响未来相似建议的软排序，不创建/修改临床笔记。

---

## 8. Synthetic Evaluation Protocol

外部普通 Transcript 不能代替 importance feedback。E2 使用受控 synthetic cases：

1. 建立两个 base score 相同的 future candidates；
2. 对已有同类 AI-derived Highlight 执行 clinician pin/accept；
3. 持久化新的相似 candidate；
4. 验证 adaptive adjustment 和最终排序变化；
5. 创建不同 entity type control，证明不被错误提升；
6. 在 Clinic B 创建相同 candidate，证明不受 Clinic A feedback 影响；
7. 执行 reject/toggle/concurrent update，证明 latest-only、CAS 和 cap。

所有 synthetic facts 必须 exact-span anchor；不得只插入无来源 score row。

---

## 9. Required Bonus Test

必须新增：

```text
backend/tests/test_self_learning_importance.py
```

至少覆盖：

- clinician pin AI-scribed Highlight -> future similar item score rises；
- current pinned ordering 与 future learned boost 是两个独立断言；
- reject -> future similar item bounded decrease；
- same-base control 不改变；
- clinic isolation；
- staff signal works but never clinician-confirmed；
- patient/admin action produces no learning；
- actor/highlight latest-only 防重复刷分；
- CAS conflict/no-op 不产生 feedback；
- adjustment caps；
- hard-risk/unresolved protection；
- feedback/audit metadata-only；
- future learned Highlight exact provenance resolves；
- read path does not import/query learning aggregation；
- deterministic final tiebreak remains stable。

另建议扩展：

```text
backend/tests/test_glance_ordering.py
backend/tests/test_glance_status.py
backend/tests/test_read_path_no_llm.py
backend/tests/test_rbac_scope.py
```

---

## 10. 性能与可重复性

- feedback aggregation 只在 feedback write 或 candidate write path；
- Glance GET 仍只读取 precomputed score；
- 重跑 warm-path measurement，单独报告 pre/post P50/P95；
- 注入 deterministic `as_of`/IDs，测试不得依赖 wall clock 顺序；
- 评价报告分开写 base score、adaptive adjustment、final score；
- 不把一次 synthetic test 称为真实 clinician usability 或 learned clinical correctness。

---

## 11. 文件边界

预期允许范围：

```text
backend/app/models.py
backend/app/highlights.py
backend/app/importance_learning.py       # new
backend/app/api/highlights.py
backend/app/ai_pipeline.py               # only candidate persistence hook
backend/app/schemas.py
backend/app/db.py                        # only explicit migration support if selected
backend/seed/fixture.py                  # bounded demo feedback/future candidate
backend/tests/test_self_learning_importance.py
backend/tests/test_glance_*.py
backend/tests/test_read_path_no_llm.py
frontend/src/types.ts
frontend/src/components/GlancePanel.tsx
frontend/src/index.css
```

不得修改 LLM prompts/provider、clinical conflict authority、Patient View projection、auth/session 或 Task lifecycle 来实现 learning。

---

## 12. Exit Gate — E2 Complete

1. 一个显式 clinician feedback 能使未来相似 AI-derived candidate 发生可解释分数变化；
2. 变化是 clinic-scoped、bounded、latest-only；
3. current pin 与 future learning 已被测试区分；
4. staff feedback 不成为 clinician authority；
5. hard-risk/unresolved/confirmed/needs-review 保护通过；
6. feedback 与 AuditLog 不含 clinical content；
7. learned candidate 仍有 exact provenance；
8. Glance GET 保持 precomputed、zero-LLM、无 feedback aggregation；
9. required bonus test 与全部历史 tests/evals/build/security regression 通过；
10. UI 与 Technical Brief 能解释 base/adaptive/final，且不声称真实医生验证。

---

## 13. 非目标与停止条件

非目标：模型训练、fine-tuning、learning-to-rank neural model、embedding similarity、跨 clinic/global profile、个体医生画像、学习 Summary/诊断/处方、自动使用 Comment/Edit 权重。

停止条件：

- 只有 current pin 排序变化，没有 future candidate 变化 -> 不通过；
- 需要 raw text/PHI 作为 clinic-wide learning key -> 停止；
- learning 可压过硬风险保护 -> 停止；
- Glance read path 需要重新扫全历史或调用 LLM -> 停止；
- synthetic labels 被描述为真实 clinician preference -> 停止并修正文档。

