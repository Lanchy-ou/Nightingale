# M1 任务卡 — 最小系统骨架 + Canonical Synthetic Fixture

> 对应：`Nightingale_72H_Development_Plan.md` Phase 1（§5）+ `AGENTS.md` M1。
> 截止目标：**Milestone 1 — 最迟 2026-08-26 上午**。
> 前置状态：git 已初始化（首个 commit `4a9968c`），技术栈已冻结（README §15）。

---

## 1. 目标

系统第一次真正运行起来：一个患者、一条跨日期 Timeline、可展开的 Event、并列共存的 raw / AI / clinician artifacts。

不追求：真实 LLM、Glance 逻辑、协作、RBAC 拦截、权限 UI。

---

## 2. 范围

### In Scope

- 后端 scaffold：FastAPI + SQLAlchemy 2.x + SQLite + Pydantic v2
- M1 数据表：Clinic / User / Patient / Event / Artifact（Span 以 JSON pointer 表达，不单独建表）
- Canonical synthetic fixture + seed 脚本
- 只读 API：patient / timeline / event artifacts
- server-side role context 解析（header 注入，不做认证）
- 前端 scaffold：Vite + React 18 + TS，unified patient page（header / Glance 占位 / Timeline / Event 展开）
- pytest 冒烟测试（schema + fixture 完整性 + provenance 可解析 + API 只读）

### Out of Scope（明确不做）

- 真实 LLM 调用（AI summary 用 fixture 预写内容）
- Highlight / Glance 计算（仅占位）
- Comment / Version / AuditLog / Task 表（Phase 3）
- RBAC 拦截逻辑（Phase 3；M1 只要求 role context 能被解析和测试）
- 写接口（POST/PUT/PATCH）
- 认证 / 登录流程

---

## 3. 目录结构（建议）

```text
Nantingale/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口，挂载 router + role context middleware
│   │   ├── db.py              # engine / session
│   │   ├── models.py          # SQLAlchemy models
│   │   ├── schemas.py         # Pydantic v2 schemas
│   │   ├── role_context.py    # X-User-Id / X-Role header 解析依赖
│   │   └── api/
│   │       ├── patients.py
│   │       └── events.py
│   ├── seed/
│   │   ├── fixture.py         # canonical synthetic truth（唯一事实源）
│   │   └── seed.py            # 建库 + 灌入 fixture
│   └── tests/
│       ├── test_seed_integrity.py
│       ├── test_provenance_resolution.py
│       └── test_read_api.py
├── frontend/
│   ├── src/
│   │   ├── api.ts
│   │   ├── pages/PatientPage.tsx
│   │   └── components/        # PatientHeader / GlancePlaceholder / Timeline / EventCard
│   └── ...
└── docs/（已存在的三份文档保持在根目录）
```

---

## 4. M1 数据模型（最小字段）

### Clinic / User

```text
clinic:  clinic_id, name
user:    user_id, clinic_id, name, role ∈ {patient, staff, clinician, admin}
```

### Event

```text
event_id, patient_id, clinic_id, event_type,
started_at, ended_at,          -- 现实医疗事件发生时间
created_at                     -- 记录产生时间
```

event_type ∈ `patient_ai_preconsult | nurse_consult | doctor_consult | patient_followup | clinician_review | historical_review`

### Artifact

```text
artifact_id, event_id, artifact_type,
author_role,                   -- AI artifact 恒为 "system"
author_id,                     -- AI artifact 为 null / system
content (JSON 或 text),
created_at,
version (默认 1),
provenance_pointer (JSON, 可空)
```

artifact_type 至少支持：

```text
raw_conversation | transcript | clinician_note | staff_note
ai_doctor_consult_summary | ai_nurse_consult_summary | ai_patient_session_summary
patient_instruction
```

### Span（不建表，JSON pointer）

`provenance_pointer` 结构示例：

```json
{
  "event_id": "evt_...",
  "artifact_id": "art_transcript_...",
  "span": {"kind": "segment", "index": 17}
}
```

`span.kind ∈ segment | message | paragraph | timestamp_range | section`，M1 只需能存取并解析回 artifact + 定位符。

### 硬约束（M1 即生效）

- AI artifact 的 `author_role = "system"`，与人工 note 独立成行，任何写入不得覆盖其他 artifact；
- Event 的 `started_at/ended_at` 与 Artifact 的 `created_at` 是两条时间轴，Timeline 排序只用 `started_at`。

---

## 5. Canonical Synthetic Fixture（唯一事实源）

一个诊所、四个用户（每角色一个）、一个主患者。

```text
Patient A
├── 2025-04-15  historical_review（初次头痛主诉，建议观察）
├── 2026-02-06  historical_review（medication review，开始现有用药）
└── 2026-08 当前 episode
    ├── 08-20  patient_ai_preconsult
    │     ├── raw_conversation（患者-AI 对话，含源句
    │     │   "My headaches used to happen once a week, but now they're almost every day."）
    │     └── ai_patient_session_summary（author_role=system，
    │         provenance_pointer 指向 raw_conversation 对应 message）
    ├── 08-21  nurse_consult
    │     ├── transcript（BP 158/96 等）
    │     └── ai_nurse_consult_summary（system，带 provenance）
    ├── 08-21  doctor_consult
    │     ├── transcript（≥ 20 个 segment，第 17 段留给 Phase 2 示例）
    │     ├── ai_doctor_consult_summary（system，带 provenance）
    │     ├── clinician_note（clinician 作者，assessment + plan：
    │     │   blood test ordered、follow-up scheduled）
    │     └── patient_instruction
    └── 08-24  patient_followup
          ├── raw_conversation（headache 3/10 改善、nausea persists）
          └── ai_patient_session_summary（system，带 provenance）
```

**事实清单（不得互相矛盾）**：

1. headache：每周一次 → 接近每天（08-20）→ 7/10 降至 3/10（08-24）
2. morning nausea：08-20 出现，08-24 仍持续
3. BP elevated：08-21 nurse 测得
4. existing medication：2026-02-06 起使用
5. blood test：08-21 开具，仍 pending
6. follow-up：已预约

写 fixture 时逐条核对此清单；任何新增叙述不得与清单冲突。

---

## 6. API 契约（M1 只读）

```text
GET /api/patients/{patient_id}
    → patient 基本信息 + clinic

GET /api/patients/{patient_id}/events
    → 按 started_at 排序的 Event 列表（含 event_type、时间、artifact 计数）

GET /api/events/{event_id}/artifacts
    → 该 Event 的全部 Artifact（含 author_role、type、provenance_pointer）
```

所有请求经 role context 依赖解析 `X-User-Id` / `X-Role` header，注入 request state；M1 不做拒绝，只要求解析结果可被测试断言。

错误格式统一：`{"error": {"code": "...", "message": "..."}}`。

---

## 7. 前端页面（M1）

单页 `PatientPage`：

```text
┌ Patient Header（姓名缩写、clinic、当前 episode 标签）
├ Glance Placeholder（静态文案 "Glance arrives in Phase 2"）
├ Longitudinal Timeline
│   └── Event 卡片（日期、类型、角色徽标）→ 点击展开
│         └── Artifact 列表（type 徽标：RAW / AI / CLINICIAN 颜色区分，
│             AI 条目显示 "System-generated" 标记 + provenance 提示）
```

- 通过 Vite dev proxy 调 `/api`；
- `npm run dev` 必须能透传 host/port 参数（Vite 默认支持 `npm run dev -- --host --port xxx`），保持 Kimi Work 预览兼容；
- 不做登录，用页面顶部一个 role 切换器写入请求 header（仅演示用，注释标明非安全边界）。

---

## 8. 任务分解与建议顺序

串行执行（单人 + LLM 容量），每步一个 commit：

| # | 任务 | 难度 | 产出 |
|---|------|------|------|
| 1 | backend scaffold + db + models | L2 | 能建空库 |
| 2 | `fixture.py` 事实源 + `seed.py` | **L3** | seed 后数据完整，逐条核对事实清单 |
| 3 | role context + 3 个只读 API | L2 | curl 可验证 |
| 4 | pytest 三个冒烟测试 | L2 | 全绿 |
| 5 | frontend scaffold + PatientPage + Timeline 展开 | L2 | 浏览器可见端到端 |
| 6 | README §15 回填真实命令 + 首次 integration | L1 | TBD 全部消除 |

fixture 一致性（任务 2）是 M1 唯一 L3 工作，值得花最多核对时间。

---

## 9. 测试（M1）

- `test_seed_integrity.py`：fixture 事实清单断言（事件数、日期、关键内容存在、AI artifact `author_role=system`）；
- `test_provenance_resolution.py`：每个 AI summary 的 `provenance_pointer` 能解析到存在的 event + artifact + span 定位符；
- `test_read_api.py`：三个只读端点返回 200 且结构正确；role header 解析结果符合注入值。

---

## 10. 验收（Exit Gate，与计划 §5 一致）

从浏览器：

1. 打开一个患者；
2. 看到跨日期 Timeline（2025-04、2026-02、2026-08 × 4）；
3. 展开 Doctor Consult；
4. 看到至少 transcript、AI summary、clinician note 并列存在；
5. raw / AI / clinician authored content 没有互相覆盖，AI 条目有 system 标记。

外加：

6. 三个 pytest 全绿；
7. README §15 的 TBD 全部替换为真实命令（安装 / 启动后端 / 启动前端 / 跑测试 / seed）；
8. commit history 清晰（每任务一个 commit）。

**只有这条跑通才能进入 Phase 2（Glance → Provenance 竖切）。**

---

## 11. 风险与注意

- **不要顺手做 Phase 2/3 的事**：看到"顺便把 highlight 表建了"的冲动要忍住——M1 的价值在于快速打通，不在完备。
- fixture 文字用英文（与 brief 示例一致），AI summary 内容预写但格式按真实 LLM 输出设计，Phase 4 才能无缝替换。
- SQLite 文件不入库（.gitignore 已覆盖 `*.db`）；seed 脚本必须可重复执行（先清库再灌）。
- 加密 / TLS / redaction 在 M1 不实现，但 `models.py` 字段命名不要堵死后续加密的余地（如 content 用 Text/JSON 大字段即可）。
