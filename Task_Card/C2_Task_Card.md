# C2 任务卡 — Clinician Workspace + Consult Review UX

> 状态：**COMPLETE（2026-08-26）**
> 前置：`C1 — Encounter + Manual Doctor Consult Backend` 已完成。
> 完成验证：156 pytest、TypeScript/Vite production build、1280px Playwright browser QA 全部通过。
> 后续：进入 Phase 6 Performance + Core Hardening。
> 目标：按已确认的 `docs/clinician_workspace_design.md` 重构医生端，并把 C1 的 Manual Doctor Consult 纵向链路嵌入 Timeline、Event Detail、Source Viewer 和 Comment 协作。

---

## 1. 本卡的产品边界

当前主产品角色是 clinician。C2 做一套真实可用的医生工作区，但不假装已经完成 Nurse、Task、assignment、正式认证或 Doctor AI Assistant。

```text
左侧                        中央                              右侧
Clinician identity          Patient header                    Context Panel
Dashboard 返回入口          Glance | Timeline | Notes          Source Viewer
Clinic Patients             New Consult / Event Detail         Comments / Versions / Audit
```

冻结规则：

- 左栏在 assignment 完成前只能叫 `Clinic Patients`，不得叫 `My Patients`；
- Demo role switcher 必须移出产品 shell，作为明确分离的 Demo toolbar；
- Patient 继续 role-level binary render 到独立 Patient View，不能挂载 Clinician Shell；
- Context Panel 只显示已经存在的 Source/Comments/Versions/Audit；未实现的 AI Assistant 不显示假 UI；
- 不展示假的 Tasks、Mentions inbox、appointment 或 care-team 状态；
- Nurse/Staff 保留旧的最小演示路径与服务端能力，不开发 Nurse Workspace；
- 页面主要目标是桌面 1280px+；移动端只保证基本不泄漏/不崩溃，不在本卡追求完整临床移动体验。

---

## 2. 范围

### In Scope

- Clinician Shell、identity、Clinic Patients；
- patient switch + state isolation；
- `Glance | Timeline | Notes` 主导航；
- `New Consult` 独立页面/状态；
- manual transcript paste parser + structured preview；
- C1 Doctor Consult endpoint 接入；
- Clinic Visit explicit encounter grouping；
- Timeline master/detail、Event lifecycle、Artifact Reader；
- Source Viewer 右栏化；
- Comment/Event/Artifact anchor、reply、mention、resolve/unresolve；
- Revision/diff/revert、Audit 在 Artifact 上下文中保留；
- 端到端 Demo scenario；
- frontend type/build、桌面视觉、loading/empty/error/fallback、安全回归；
- README / AGENTS / Development Plan / Technical Brief 后续内容回填。

### Out of Scope

- C1 后端合同重做或第二套 ingestion pipeline；
- Nurse Workspace / Nurse New Consult；
- Doctor AI Assistant；
- Task model、care-team assignment、正式认证；
- Patient Experience 视觉复刻、Patient 连续聊天、structured appointment；
- 录音、ASR、音频上传、OCR、外部 EHR；
- span-level Comment；
- Performance、Self-learning、Data decay、Voice bonus。

---

## 3. New Consult UX 合同

建议路由/页面状态：

```text
/clinical/patients/:patientId/consults/new

Draft
→ Validate / Preview
→ Saving raw source
→ Processing
→ Completed | Completed with fallback | Failed after source saved
```

页面必须：

- 显示当前患者和 consult 时间；
- 提供 `DOCTOR:` / `PATIENT:` 格式帮助；
- 将 paste text 解析成 C1 strict segments 并显示 preview；
- preview 不能识别的行明确报错，不让 AI 猜 speaker；
- 发送中禁止重复提交；
- 失败后保留 textarea，不静默清空；
- 不把 transcript draft 写入 localStorage；
- 明确区分“raw source 已保存”和“AI derived content 已生成”；
- 成功后进入新 Event Detail，刷新 Timeline 与 Glance；
- 不再在 Glance 和 Timeline 之间显示旧 `IngestPanel`。

---

## 4. Timeline / Event Detail / Collaboration 合同

### 4.1 主 Timeline

- 主 Timeline 以现实医疗 Event 为核心；
- 相同非空 `encounter_id` 的 Nurse/Doctor Events 显示为一个 `Clinic Visit` group；
- Doctor-only encounter 可显示为只有一个 Doctor Consult 的 Clinic Visit；
- 不同 encounter 即使同日也必须分别显示；
- Comment、Revision、Audit 绝不成为主 Timeline Event。

### 4.2 Event Detail 小时间线

```text
Consult started
Transcript saved
AI Doctor Summary generated
Clinician Note added
Comment added / replied / resolved
Clinician Note revised / reverted
```

- Event 仍以 `started_at/ended_at` 表示现实时间；
- Artifact/Comment/Audit 使用 `created_at` 表示信息生命周期；
- 后续修改仍属于原 Event；
- 点击 Artifact 后在中央可读区域打开，不在主 Timeline 无限展开。

### 4.3 Artifact / Context Panel

- Transcript、AI Summary、Clinician Note 在中央 Artifact Reader 展示；
- raw Transcript 不提供 Edit/Revert；
- Clinician 只编辑自己的 `clinician_note`；
- Source Viewer 在右栏显示 Highlight → Summary → Source → exact span；
- Comments 可锚定 Event 或 Artifact，reply 保留原 anchor；
- resolve/unresolve 和 mentions 继续走现有后端合同；
- Comment 不是正式临床结论；需要修正计划时创建/编辑 Clinician Note；
- Task 未实现时，不把 unresolved Comment 冒充有 assignee/due date 的 Task。

---

## 5. 三个工作包

### C2.0 — Clinician Shell + Navigation

- 移除 860px 窄容器，建立三栏 shell；
- identity、Clinic Patients、patient header；
- Glance/Timeline/Notes；
- Demo toolbar 与产品 UI 分离；
- patientId remount + request cancellation/stale-response 防护。

验证：桌面信息架构成立；切换患者不会残留前一患者 source/Event/comments/draft；Patient View 无回归。

### C2.1 — New Consult + Master/Detail

- transcript paste/parse/preview/submit；
- processing/fallback/error 状态；
- C1 API 接入；
- Clinic Visit grouping；
- Event Detail、Artifact Reader、lifecycle；
- 成功后 Timeline/Glance refresh。

验证：医生通过 UI 创建新 Event，raw/derived 状态清楚，浏览器返回/刷新不会进入错误患者。

### C2.2 — Context Collaboration + Final Integration

- Source Viewer 右栏化；
- Comment/mention/reply/resolve、revision、audit 上下文化；
- 端到端 demo、视觉/错误 QA；
- full regression + docs 回填；
- C2 Exit Gate 后交接 Performance。

验证：New Consult → Summary → Highlight → exact source → Comment/Clinician Note → Timeline/Glance 可重复演示。

---

## 6. 前端与集成硬门

- TypeScript check + Vite build；
- 1280px 主场景无关键 overflow、重叠或不可读长 transcript；
- loading/empty/error/fallback 状态清楚；
- submit failure 保留 transcript；
- patient role 不请求 clinical Timeline/Glance/comments endpoints；
- patient switch 清除 previous source/Event/comments/pending response；
- Source Viewer exact quote 高亮正确；
- Glance accept/reject/pin 保留；
- Comment reply/anchor/mention/resolve 与 audit 测试回归；
- revision/concurrency/RBAC/provenance/patient leak/full pytest 全绿；
- Glance read path不新增 page-load full-history LLM。

---

## 7. Exit Gate — C2 Complete

只有全部满足时才可声明：

> **C2 / Clinician Workspace + Consult Review UX Complete**

1. Clinician 页面符合已确认的三栏设计，且没有假能力；
2. `New Consult` 从 UI 创建新的 Doctor Consult Event；
3. Doctor Consult 出现在主 Timeline，并可进入 Event 内部生命周期；
4. 相同 encounter 的 Nurse/Doctor Events 可组成 Clinic Visit，独立同日事件不会误合并；
5. Transcript、AI Summary、Clinician Note、Comment 独立显示；
6. Highlight 能从 Glance 回到新 transcript exact span；
7. Comment/@mention/resolve/revision/audit 在 Event Detail 中可用；
8. patient switch 与 role switch 不残留敏感上下文；
9. full pytest、frontend type/build、视觉/错误 QA 通过；
10. README / AGENTS / Development Plan 与实际状态一致。

C2 通过后才进入：

```text
Phase 6 — Performance + Core Hardening
```

---

## 8. 完成记录（2026-08-26）

- `ClinicianWorkspacePage` 已实现独立 Demo toolbar、clinician identity、Clinic Patients 搜索/切换、事实型 Clinic dashboard 与三栏桌面 shell；patient 仍 binary render 到独立 Patient View，staff/admin 保留旧最小路径。
- `Glance | Timeline | Notes`、显式 encounter Clinic Visit grouping、Event Detail lifecycle、中央 Artifact Reader 与右栏 Source/Comments/Versions/Audit 已集成；没有展示 Tasks、My Patients、AI Assistant 或 assignment 假状态。
- `NewDoctorConsult` 已实现 strict `DOCTOR:/PATIENT:` parser、连续 preview、raw/derived processing 状态、fallback/error、stable retry identity 和 C1 endpoint 接入；成功后进入新 Event 并刷新 Timeline/Glance。
- New Consult 生成的 Highlight 已在 browser QA 中从 Glance 回到新 Transcript exact span；Comment/@mention/resolve、Clinician Note、edit/version/revert 与 audit 已在 Event context 中实测。
- patientId/role 使用 remount boundary，clinical loads 使用 AbortController/stale-response guard；browser QA 验证切换患者清除 Source/Event/draft，patient role 只请求 patient-view 而不请求 clinical endpoints。
- 1280×800 与 1440×900 browser QA 无关键横向 overflow；loading/empty/error/fallback 状态均已覆盖。全量后端 **156 passed**，frontend production build 通过。

---

## 9. 停止条件

- 需要假的 Tasks/My Patients/AI Assistant 填充三栏 → 停止并隐藏；
- 需要按日期自动合并 Nurse/Doctor Events → 停止并使用 C1 encounter contract；
- 需要修改 raw Transcript/AI Summary 才能修正事实 → 停止，使用 Comment + Clinician Note；
- 需要录音/ASR/外部数据集才能完成 Demo → 越界；
- 需要放松 RBAC/provenance/patient projection 才能完成 UI → 停止并修复设计；
- C2 未通过就开始 Performance/Bonus → 停止，先完成本卡。
