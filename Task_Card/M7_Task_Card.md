# M7 任务卡 — Performance + Core Hardening

> 状态：**COMPLETE（2026-08-26）**
> 对应：`Nightingale_72H_Development_Plan.md` Phase 6（§10）+ `AGENTS.md` §10 Performance。
> 前置状态：M1–M6 + C1/C2 全部 Complete。
> 完成验证：161 pytest 绿；frontend production build 绿；Glance Layer A P95 ≈ 3.8 ms（`backend/docs/perf_baseline.md`）。
>
> **历史阶段边界说明**：本卡只做 warm-path 性能取证 + 核心硬化，不加新功能。M7 完成后原计划进入 Milestone 6；该后续安排已被 owner 的产品可用性复核更新为 Phase D Product Completion，见 `docs/phase_d_product_completion_plan.md`。M7 本身的范围与完成证据不变。

---

## 1. 目标与成功定义

把 Glance 从"设计上应该是 warm-path read"变成"**有诚实的、可复现的测量证据**的 warm-path read"：

```text
目标：warm-path Glance P95 <= 300 ms
```

成功必须同时满足：

- 测量方法写清楚：样本量、环境、warm-up 方式、计时口径（in-process handler 时间 / HTTP 往返 / 是否含渲染）、近似方法的局限；
- 测量脚本可重复运行，结果落盘为 `backend/docs/perf_baseline.md`（或等价文档），供 Technical Brief 直接引用；
- 确认 Glance / patient-view 读路径**零 LLM、零 extraction、零 pipeline import**（把 M4 的 module 检查扩展到全部读端点）;
- 核心硬化项清零（§5）：排序确定性、写后读一致性、并发状态更新的确定行为；
- 若实测 P95 超标，只许用 §4 列出的最小手段修复，并在文档中如实记录修复前后数值；
- 156 个既有测试零回归。

---

## 2. 现状基线（已核实，开工时复核）

- Glance 读路径（`backend/app/api/highlights.py::get_glance`）：单条 `SELECT highlights WHERE patient_id=? AND status!='rejected'`（`patient_id` 已有索引）→ Python 内排序 → 取 `GLANCE_LIMIT=5`。**无 LLM、无 extraction**，分数全部 write-time 预计算（M2/M4 合同）；
- 排序 key：`(status != 'pinned', -importance_score, created_at)` —— **无最终 tiebreak**，同分时顺序依赖 DB 返回序，不满足确定性合同（§5 硬化项 H1）；
- 无任何 cache 层；SQLite 单文件，demo 数据量（单患者 ~8 Event / ~15 Artifact / ~10 Highlight）；
- patient-view 端点（M6）为显式 projection 的只读聚合，同样无 LLM；
- C1/C2 后 clinician workspace 首页数据路径 = patient header + glance + events 三个端点。

---

## 3. 范围

### In Scope

- 测量脚本 `backend/scripts/measure_glance.py`（或等价）：对 warm-path 端点重复采样并输出 P50/P95 + 环境信息；
- 计时口径分层（至少报两层，见 §4.1）；
- 读路径零-LLM 静态守卫测试扩展到 glance / patient-view / events / patient header；
- §5 硬化项 H1–H4；
- 视测量结果决定是否加复合索引（不预优化）；
- `perf_baseline.md` + README 性能段落 + Technical Brief 性能章节的素材段落（Brief 正式成文在 Milestone 6）。

### Out of Scope（不得顺手实现）

- 任何新功能 / 新端点 / 新页面；
- cache 层、Redis、后台预计算 worker（只有当 §4 最小手段用尽仍超标时才评估，且需 owner 决策）；
- 前端渲染性能优化、bundle 优化、懒加载（测量含渲染时如实记录，但不本卡优化）；
- 数据库换引擎（PostgreSQL 等）；
- self-learning / voice / data decay（Phase 7，严格后置）；
- 压测 / 多用户负载测试（单用户 warm-path 即可，不假装做容量验证）。

---

## 4. 测量合同

### 4.1 计时口径（两层必报）

```text
Layer A — handler time（in-process）:
  FastAPI TestClient / 直接调用，计端点函数耗时；
  口径 = 应用逻辑 + SQLite 查询；不含网络、不含渲染。
  → 这是"P95 <= 300 ms"的主判定层。

Layer B — HTTP round trip（local）:
  真实 uvicorn 起服务，HTTP 客户端计时；
  口径 = Layer A + ASGI/序列化/本地回环开销。
  → 作为参考层报告，说明与 Layer A 的差值来源。
```

### 4.2 方法要求

- 样本量 ≥ 100 次/端点/层；前 10 次作为 warm-up 不计入统计，文档中写明；
- 测量端点（至少）：`GET /patients/{id}/glance`、`GET /patients/{id}/patient-view`、`GET /patients/{id}/events`；
- 固定使用 reseed 后的 demo DB；测量前记录 DB 行数（events/artifacts/highlights），数据量变化需重测；
- 环境记录：OS、CPU、Python 版本、SQLite 版本、是否其他重负载进程；
- 输出：P50 / P95 / max / mean + 上述全部元信息，写入 `backend/docs/perf_baseline.md`；
- 诚实条款：本地 SQLite + 单用户的数字**不得**外推声称生产性能；文档必须写"该测量证明的是架构路径不含同步 LLM/全量历史扫描，而非分布式扩展性"。

### 4.3 超标时的最小手段（按顺序）

1. 确认慢在查询还是序列化（在脚本里加分段计时）；
2. 查询慢 → 加复合索引（如 `highlights(patient_id, status)`），重测记录前后值；
3. 序列化慢 → 检查 `model_validate` 热路径，裁剪响应字段（不得裁掉合同字段）；
4. 仍超标 → 停止，向 owner 报告实测数据与选项（cache / 分页），不得静默引入 cache。

---

## 5. 核心硬化项（H1–H4）

| # | 项 | 现状 | 验收 |
|---|---|---|---|
| H1 | Glance 排序确定性 | 无最终 tiebreak | 排序 key 末尾加 `highlight_id`；同分同 pinned 同 created_at 时顺序稳定；新增测试锁定 |
| H2 | 写后读一致 | accept/pin/reject 为 write-time 重算 score | 状态变更后**同一请求连接内**重新 GET glance 立即反映新分数/排序；新增测试 |
| H3 | 并发状态更新 | M3 已处理 note 并发；highlight 状态更新未见乐观锁 | 复核 highlight 状态 mutation 的并发行为；若有 last-write-wins 静默覆盖，用确定性策略（状态机校验已存在则拒绝或明确顺序）并测试 |
| H4 | 零-LLM 读路径守卫 | M4 仅有 glance module 检查 | 静态/导入级守卫覆盖 glance + patient-view + events + patients 四个读端点模块；测试断言这些模块 import 图不含 `ai_pipeline` / `llm_client` |

H3 处理原则：highlight status 状态机（`status_transitions`）已是确定性来源；并发冲突时的行为必须**可解释、可测试**，不允许"碰巧没出问题"。

---

## 6. 任务分解（串行，每步一个 commit）

| # | 任务 | 验证 |
|---|---|---|
| 1 | H1 排序 tiebreak + 测试 | 新测试绿；156 无回归 |
| 2 | H2/H3 写后读 + 并发状态复核（如需修复则修复） | 新测试绿 |
| 3 | H4 读路径零-LLM 守卫扩展 | 守卫测试绿 |
| 4 | 测量脚本 + Layer A/B 采样 + `perf_baseline.md` | 脚本可重复运行；P50/P95 落盘 |
| 5 | （条件触发）超标修复：分段计时 → 索引/字段裁剪 → 重测 | 前后数值都记录 |
| 6 | README 性能段落 + Brief 素材段落 + AGENTS.md §19 追加 M7 状态 + 全量回归 | 156+ 测试绿；文档与实际一致 |

---

## 7. 测试矩阵

### 新增 `test_glance_ordering.py`（或并入既有 highlight 测试）

- 同分、同 pinned、同 `created_at` 的多条 highlight → 返回顺序按 `highlight_id` 稳定；
- pinned 仍优先于非 pinned，不受 tiebreak 影响。

### 新增写后读 / 并发用例

- accept → GET glance：该条 score 含 clinician_confirmed 加分且排序即时生效；
- pin → GET glance：置顶即时生效；
- （按 H3 复核结果）并发 status mutation 的行为符合确定策略。

### 读路径守卫（扩展 M4 现有检查）

- glance / patient-view / events / patients 四个模块的 import 图不含 `ai_pipeline`、`llm_client`、`extraction`；
- patient-view 响应序列化全文不含 highlight 内部字段（与 M6 泄漏测试互补，不重复）。

### 回归

- 156 既有测试零回归；
- frontend production build 通过；
- 测量脚本在干净 reseed DB 上可重复运行两次，P95 偏差可解释。

---

## 8. Exit Gate — Performance + Hardening Complete

1. `perf_baseline.md` 存在且包含：样本量、环境、warm-up、Layer A/B 的 P50/P95、口径说明、近似局限、诚实条款；
2. Layer A Glance P95 ≤ 300 ms（或超标后有完整修复记录与修复后达标值）；
3. H1–H4 全部有测试锁定；
4. 全部测试 + frontend build 绿；
5. 文档（README / AGENTS 状态）与实际一致。

通过后声明：

> **M7 / Performance + Core Hardening Complete**
>
> 至此当时定义的工程 Core Complete（以 M1–M7 + C1/C2 全部 exit gate 与 required tests 全绿为准）。原“立即进入 Milestone 6 feature freeze”安排已被后续 owner 产品可用性复核取代，当前执行 Phase D。

---

## 9. 停止条件与风险

- 测量 P95 超标且 §4.3 三步用尽 → 停止，带数据向 owner 报告，不静默加 cache；
- 为提速而删合同字段 / 关 RBAC / 跳审计 → 禁止，回退；
- 把本地 SQLite 数字写成"生产级性能" → 违反诚实条款，文档必须限定口径；
- 本卡内出现任何新功能冲动（cache、worker、前端优化）→ 越界，停止；
- H3 复核发现 highlight 并发有静默覆盖 → 必须先修再过 gate，不得绕过。

---

## 10. 完成记录（2026-08-26）

- H1：Glance 排序增加 `highlight_id` 最终 tiebreak；`tests/test_glance_ordering.py` 锁定同分/pinned 优先/tiebreak。
- H2/H3：`update_status` 改为 `WHERE status = old_status` 原子条件更新，冲突返回 409 + 仅 metadata 的 conflict audit；写后读与并发确定性均有测试。
- H4：`tests/test_read_path_no_llm.py` 用干净子进程检查 glance/patient-view/events/patients 的 transitive import 图不含 ai_pipeline/llm_client/extraction/redaction/deterministic_pipeline/conflicts。
- 测量：`backend/scripts/measure_glance.py`（Layer A in-process + Layer B HTTP，100 samples / 10 warm-up）落盘 `backend/docs/perf_baseline.md`；Glance Layer A P95 ≈ 3.8 ms，无需加索引/cache。
- 文档：README §10.1 实测段落、AGENTS §23、perf_baseline.md 已就位；全量 **161 passed**，frontend build 绿。

---

## 11. 历史后续安排（已由 Phase D 取代）

> 以下是 M7 完成时的原始交付安排，保留作为历史记录；当前不得据此跳过 Phase D D1-D5。

M7 之后不再有功能开发，剩余全部留给交付物：

1. **Technical Brief（2–3 页）**：架构图 + schema 映射（Entries/Events ↔ Artifacts ↔ Comments ↔ Versions ↔ Highlights ↔ Provenance ↔ AI-scribed notes ↔ learning mechanism，按 AGENTS §2.1 显式给出）+ 假设/第一性原理/trade-offs + 性能测量方法（引用 `perf_baseline.md`）+ redaction 入口 + RBAC 执行位置；
2. **demo video**：Scenario A（Glance + AI + Provenance）/ B（Collaboration + Audit）/ C（Longitudinal Context）正式走查录制；
3. **`ATTRIBUTION.txt` 核对**：确认 anthropic SDK 等全部依赖与 license 已列；
4. **回归 + clean commit history + 最终打包**；
5. **邮件提交**：`irakumar@ntngale.com`，CC `frank.ng@ntu.edu.sg`、`carrene.teo@ntu.edu.sg`，主题 `Nightingale 72HR Build -- <Your Name>`，**2026-08-28 17:30 SGT 前送达**；
6. Bonus（self-learning / voice / data decay）：仅在 1–4 全部完成后且仍有明确余量时启动，永不阻塞提交。
