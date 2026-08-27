# E3 Task Card — Hybrid Storage and Data Decay

> 状态：**PLANNED — IMPLEMENTATION NOT STARTED**
>
> 对应总计划：`docs/phase_e_capability_enhancement_plan.md`
>
> 依赖：E2 的 `base + adaptive + decay = final` score schema/contract 冻结。

---

## 1. 目标

使用少量、有明确时间的 synthetic longitudinal data，实现可解释、确定性、可恢复的 Data Decay：

```text
old + resolved + low-value
-> leaves the hot path
-> gets bounded negative decay adjustment / cold tier
-> remains available in Timeline
-> raw content and exact provenance remain recoverable
```

本卡要证明“旧低价值信息安静退到后台”，而不是删除历史病历。

---

## 2. 核心不变量

- Event 仍存在于主 Timeline；
- Artifact raw content 不被 summary/archive stub 覆盖；
- Version、Comment、AuditLog、Task、Highlight 与 Span 不删除；
- high-risk、unresolved、clinician-confirmed、pinned、needs_review 不允许衰减；
- Cold 数据仍受相同 RBAC/clinic scope；
- Cold source 必须继续解析 exact quote；
- policy 只使用 server-side facts，不信任前端 tier/age/reason；
- policy 结果可重复、可解释、可审计；
- Demo 不声称生产对象存储或真实存储节省，除非有当前部署证据。

---

## 3. 开工 Decision Gates

### DG1 — Time windows

使用注入的 `as_of` 与明确常量，建议初始策略：

```text
Hot window:  0-30 days
Warm window: 31-365 days
Cold age:    >365 days, only if no protection applies
```

阈值必须在代码、测试和 Brief 中一致；不得依赖运行机器当前日期使 fixture 漂移。

### DG2 — Protection precedence

冻结优先顺序：

```text
protection facts
-> tier decision
-> decay adjustment
```

任何 age rule 都不能覆盖：

- `explicit_risk=true`；
- real unresolved Task；
- `clinician_confirmed=true`；
- `status=pinned`；
- `review_status=needs_review`；
- provenance/round-trip 未验证；
- current patient instruction 或其他明确保留类型。

### DG3 — Archive proof level

E3 采用安全的 shadow archive proof：

- authoritative `Artifact.content` 保留；
- Cold candidate 生成 canonical JSON hash；
- 同时生成压缩 payload 与 size metadata；
- 解压后必须 hash-equivalent；
- 不在 E3 删除 authoritative hot copy。

该设计证明 schema、压缩、恢复与 provenance-preserving migration readiness，但不得声称当前 DB 已减少总字节或已迁移到外部 cold storage。

### DG4 — Decay effect

建议 bounded adjustment：

```text
Hot  =  0
Warm = -1
Cold = -2
```

被保护项目的 `decay_adjustment` 强制为 0。最终 score 继续由 server write path 预计算。

---

## 4. 数据模型

新增 `artifact_storage_state`（名称可按现有风格调整）：

```text
artifact_id              # PK/FK
tier                     # hot | warm | cold
reason_codes             # controlled metadata list
policy_version           # e.g. decay-v1
evaluated_as_of
evaluated_at
source_sha256
codec                    # null or zlib-json-v1
compressed_payload       # nullable BLOB
original_bytes
compressed_bytes
roundtrip_verified_at
```

要求：

- `reason_codes` 使用受控代码，不复制 clinical content；
- canonical JSON serialization 固定 key order、UTF-8 与 separators；
- hash 与压缩只作用于授权进程内已有 Artifact content；
- payload 在 SQLCipher Demo 中受整库加密；若未来外置，必须重新完成 at-rest Decision Gate；
- 旧 DB migration/reseed 路径明确；不得假设 `create_all` 自动添加列/表。

Highlight 使用 E2 已冻结字段：

```text
base_importance_score
adaptive_adjustment
decay_adjustment
importance_score
```

E3 不得把 tier、reason 或 age 从前端写入 Highlight。

---

## 5. Deterministic Policy Service

新增单一 domain module，例如：

```text
backend/app/data_decay.py
```

最低输入：

```text
artifact/event timestamps
injected as_of
related Highlight flags/status/review_status
related real Task status
unresolved Comment presence if adopted
artifact type / authority
provenance integrity state
```

最低输出：

```text
tier
controlled reason_codes
decay_adjustment
archive eligibility
```

示例：

```text
2025-04-15 old historical, resolved, no risk -> cold / -2
2026-02-06 older relevant context            -> warm / -1
2026-08 current episode                      -> hot / 0
old item + unresolved task                   -> hot / 0
old item + clinician confirmation            -> hot / 0
```

Policy 不调用 LLM，不使用自由文本判断 pending/risk，不把 `"pending"` 字样当 Task state。

---

## 6. Policy Runner

新增可重复命令：

```text
python scripts/apply_storage_policy.py --as-of 2026-08-26 --dry-run
python scripts/apply_storage_policy.py --as-of 2026-08-26 --apply
```

Dry-run 必须只读并报告：

- Hot/Warm/Cold count；
- artifact id、tier 与 reason codes；
- protected count 与保护原因；
- archive candidate count；
- original/compressed bytes 与 ratio；
- round-trip/hash status；
- policy version/as_of；
- 不输出 raw content、quote、patient name 或 PHI。

Apply 必须：

- 幂等；
- 在 transaction 内写 state/payload；
- 不删除/覆盖 Artifact content；
- archive/hash 失败时 fail closed 为 Hot 或 blocked，不半归档；
- 记录 metadata-only audit/evidence（按卡内选择）。

---

## 7. Glance 与 Timeline 行为

### Glance

- 新候选或 policy recompute 后保存 final score；
- protected item decay=0；
- old low-value item 可因 -1/-2 退出 Top 5；
- pinned 仍按现有 deterministic ordering first；
- rejected 仍排除；
- GET Glance 不实时执行 policy 或解压 archive。

### Timeline/Event Detail

- 不隐藏整个 Event；
- 可对 Warm/Cold Artifact 显示轻量标签，例如：

```text
Archived context
Older low-priority record - exact source retained
```

- 点击后继续通过授权 API 打开 authoritative content/exact source；
- Patient View 不返回 storage tier、hash、codec、payload 或内部 retention reason。

---

## 8. Synthetic Data

不需要大量新数据。优先复用当前纵向故事：

```text
2025-04-15 historical event
2026-02-06 historical review
2026-08 current episode
```

只在 test fixture 中增加最小对照：

- old low-value；
- old high-risk；
- old unresolved Task；
- old clinician-confirmed；
- old needs-review；
- archive corruption case。

不得为了让 policy 看起来有效而修改 canonical clinical facts 或删除 protected relationships。

---

## 9. Automated Tests

必须新增：

```text
backend/tests/test_data_decay_policy.py
backend/tests/test_archive_roundtrip.py
```

至少覆盖：

- injected `as_of` 下 Hot/Warm/Cold 边界；
- future timestamp fail safe；
- 2025 low-value -> Cold；
- 2026-02 -> Warm；
- current -> Hot；
- old explicit risk -> Hot；
- old unresolved real Task -> Hot；
- old clinician-confirmed/pinned -> Hot；
- old needs-review -> Hot；
- protected item decay=0；
- ordinary Warm/Cold adjustment 为 -1/-2；
- final score 保留 E2 adaptive adjustment；
- policy 重跑幂等；
- original Artifact content/version/count 完全不变；
- canonical hash 稳定；
- compress/decompress round-trip；
- corrupted payload fail closed；
- restored content 上 exact Span/quote 仍相同；
- cross-clinic authorization 不变；
- Patient View exact key/sentinel anti-leak 继续通过；
- Glance read path 不执行 policy/decompression/LLM；
- D5 encrypted storage/backup/restore 包含新表且仍通过。

---

## 10. 性能与证据

- policy/archive 属于 write/maintenance path，不加入 warm Glance request；
- 分别测量 policy dry-run、apply、archive round-trip，不与 Glance P95 混合；
- 重新运行 Glance/events/patient-view baseline；
- 报告真实 original/compressed bytes，但明确 shadow copy 仍保留 authoritative content；
- 不把压缩率称为总数据库节省；
- 不把 synthetic time cases 称为长期生产 retention validation。

---

## 11. 文件边界

预期允许范围：

```text
backend/app/models.py
backend/app/highlights.py
backend/app/data_decay.py                  # new
backend/app/schemas.py
backend/app/api/events.py                  # tier metadata only if approved
backend/app/api/highlights.py              # preserve final score semantics
backend/scripts/apply_storage_policy.py    # new
backend/seed/fixture.py                    # minimal bounded data if needed
backend/tests/test_data_decay_policy.py
backend/tests/test_archive_roundtrip.py
backend/tests/test_read_path_no_llm.py
backend/tests/test_patient_view.py
backend/tests/security/test_encrypted_storage.py
frontend/src/types.ts
frontend/src/components/ClinicalEventDetail.tsx
frontend/src/index.css
```

不得修改 AI extraction/prompt、RBAC semantics、Task lifecycle 或 raw Artifact update path 来实现 decay。

---

## 12. Exit Gate — E3 Complete

1. 少量 synthetic dates 产生稳定、可解释的 Hot/Warm/Cold 结果；
2. old low-value item 得到 bounded decay 并可退出热路径；
3. high-risk、unresolved、confirmed、pinned、needs-review 全部受保护；
4. Artifact raw content、Version、Comment、Audit、Task、Span 零删除/覆盖；
5. Cold shadow archive hash/压缩/恢复通过；
6. restored content 上 exact provenance 与原内容一致；
7. Patient View 不泄漏 archive/internal retention metadata；
8. Glance GET 保持 precomputed、zero-LLM、无 policy/decompression；
9. SQLite 与 SQLCipher Demo/backup/restore 全绿；
10. 全量历史 tests/evals/build/security regression 通过，Brief 诚实说明 shadow archive 限制。

---

## 13. 非目标与停止条件

非目标：删除 raw records、生产 S3/object storage、跨 region archive、自动法律 retention、真实患者长期验证、LLM summarization-as-compression、对所有旧数据一刀切。

停止条件：

- 需要删除/覆盖 raw Artifact 才能展示 Bonus -> 停止；
- risk/task/confirmation 可被 age rule 降权 -> 停止；
- archive 恢复后 exact source 不一致 -> 停止；
- policy 读取自由文本猜测 Task/risk -> 停止；
- 把 shadow archive 描述为已实现生产存储节省 -> 停止并修正文档。
