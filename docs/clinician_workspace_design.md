# Nightingale Clinician Workspace 前端设计方案

> 状态：**C2 核心范围已实现（2026-08-26）**；Tasks / AI Assistant / assignment / production auth 仍明确后置  
> 决定日期：2026-08-26  
> 适用范围：Clinician 桌面端工作台与单患者临床工作区  
> 设计依据：Candidate Brief、项目执行合同、M1–M6 现有实现，以及 2026-08-26 的产品讨论

## 1. 文档目的

本文档系统记录 Nightingale 医生端页面的目标信息架构、页面区域、交互路径、数据边界、权限边界、响应式行为和实施验收标准。

本文档不是在宣布新页面已经完成。它用于指导后续前端重构，并明确哪些能力可以复用、哪些能力仍需实现。

核心产品原则保持不变：

> Timeline = what happened.  
> Glance = what matters now.  
> Patient View = what the patient needs to know and do.

医生端必须同时满足两个核心问题：

1. 医生能否在 10 秒内理解当前患者最重要的状态和下一步行动？
2. 医生能否快速核查每一条重要信息来自哪个 Event、Artifact 和准确 source span？

## 2. C2 前基线页面的性质与主要问题

以下内容记录 C2 实施前的基线。当前 clinician 已改由 `frontend/src/pages/ClinicianWorkspacePage.tsx` 渲染；`PatientPage.tsx` 仅保留给 staff/admin 的最小演示路径。

C2 前的 `frontend/src/pages/PatientPage.tsx` 是一个用于验证功能链路的单患者临床工作区垂直切片，并不是完整的医生产品外壳。

当前页面已经证明以下功能成立：

- Glance 可以读取预计算 Highlights；
- `View source` 可以解析 Event → AI Summary → Source Artifact → exact span；
- Timeline 按 `Event.started_at` 展示患者历史；
- Event 可以加载其 Artifacts；
- clinician/staff notes、评论、@mention、revision、revert 和 audit 已有交互基础；
- RBAC 和 clinic scope 在服务端执行，而不是依赖前端隐藏；
- patient 使用独立 `PatientViewPage`，不是临床工作区的裁剪版。

当前页面的主要 UX 问题：

- 登录后直接进入固定患者 `pat_001`，缺少医生管理多个患者的工作台；
- 页面被限制在约 860px 宽度，并将模块从上到下连续堆叠；
- Glance、Ingest Transcript、Provenance 和 Timeline 缺少清晰的主次层级；
- `Ingest transcript` 是演示/输入流程，却被放在阅读主干中；
- Timeline 视觉上是折叠卡片列表，不足以表达纵向诊疗过程；
- Event 展开后，Artifact、评论、版本和 audit 全部纵向堆叠，信息密度失控；
- 来源核查会在主内容流中插入新面板，打断医生当前阅读上下文；
- 缺少医生身份、患者列表、工作事项和跨患者协作入口；
- 当前没有医生端 AI Assistant；
- 当前角色切换器仅用于 Demo，不能出现在正式产品中。

## 3. 已确定的产品结构

采用“医生工作台优先 + 患者工作区优先”的组合方案：

```text
真实登录
  ↓
医生工作台
  ├─ 今日待处理
  ├─ 待审核内容
  ├─ @mentions
  ├─ 患者列表
  └─ 最近访问患者
       ↓ 选择患者
单患者临床工作区
  ├─ Glance
  ├─ Timeline
  ├─ Notes
  └─ 右侧上下文：AI Assistant / Source Viewer
```

医生首次登录进入工作台。选择患者后进入该患者工作区；左侧患者列表持续存在，使医生可以快速切换患者。页面可恢复医生上次查看的患者，但必须始终保留明确的“返回工作台”入口。

## 4. 桌面端整体区域划分

### 4.1 三栏桌面布局

目标桌面端采用三栏布局：

```text
┌────────── 左侧导航 ──────────┬──────────── 中央工作区 ────────────┬──────── 右侧上下文 ────────┐
│ 医生身份卡                   │ 患者标题与主要操作                 │ AI Assistant              │
│ 工作台 / Tasks / Mentions    │ Glance | Timeline | Notes          │ 或                        │
│ 患者搜索与患者列表           │ 当前主视图                         │ Source Viewer              │
└──────────────────────────────┴────────────────────────────────────┴───────────────────────────┘
```

推荐宽度仅作为实施起点，不是不可调整的像素合同：

- 左侧导航：240–280px；
- 中央工作区：弹性占用剩余空间，保证长文本和时间线可读；
- 右侧上下文：320–380px；
- 典型目标视口：1280px 及以上。

### 4.2 左侧导航

左侧顶部放置医生身份卡，而不是角色切换器。身份卡应清楚展示：

- 头像；
- 医生姓名；
- 当前角色；
- 所属 clinic；
- Profile / Settings 入口。

身份卡可以比普通头像菜单稍大，但不能占据过多垂直空间，因为患者切换才是高频任务。

左侧工作入口包括：

- My Dashboard；
- Tasks；
- Mentions；
- My Patients。

患者列表至少支持：

- 搜索；
- 最近查看；
- 分配给我的患者；
- 需要处理；
- 全部授权患者。

单个患者行建议显示：

- 患者姓名；
- 是否有新更新或待处理事项；
- 当前选中状态；
- 必要时显示最近更新时间。

左侧列表不得展示过多详细病情，以降低共享屏幕环境中的不必要暴露。优先使用“2 items need review”“updated today”等低敏感度状态，而不是直接展示完整症状。

### 4.3 中央工作区

中央顶部显示：

- 当前患者姓名；
- 必要的低密度患者识别信息；
- clinic / current care episode；
- 最近更新时间；
- Add note；
- New consult。

中央主导航暂定为：

```text
Glance | Timeline | Notes
```

不使用 `Overview` 替代 `Glance`。Glance 是 Candidate Brief 和本项目的核心产品概念。

### 4.4 右侧上下文区域

右侧区域是上下文工具，不是第四个信息仓库。C2 只展示已经实现的：

```text
Source | Comments | Versions | Audit
```

AI Assistant 尚未实现，因此 C2 没有显示占位或假入口。切换上下文不会复制或修改正式病历。

## 5. Glance 设计

### 5.1 目标

Glance 只回答：

> 医生现在最需要关注什么？

Glance 不再包含 `Recent Timeline`。Timeline 已有独立主视图，重复展示会削弱 Glance 的聚焦性。

### 5.2 Highlight 内容

每条 Highlight 至少显示：

- `text`；
- `risk_reason`；
- 必要的状态/来源摘要；
- `View source`；
- accept / reject / pin 能力；
- clinician-confirmed / needs-review 等状态。

accept / reject / pin 是现有产品合同的一部分，视觉重构不得删除。它们可以通过紧凑操作组、hover action 或 overflow menu 呈现，但必须保持可发现、可操作和可审计。

Glance 的排序仍使用服务端预计算结果；前端不得重新计算或偷偷改变排名。

### 5.3 View source

点击 `View source` 后：

1. 中央 Glance 保持原位；
2. 右侧自动切换到 Source Viewer；
3. 展示 Highlight → Derived Artifact → Source Artifact → exact span；
4. 准确原文被高亮；
5. 展示作者角色、Event 时间和 Artifact 创建时间；
6. 如存在冲突，提供跳转到 clinician-authored artifact 的入口。

来源核查不得只展示装饰性 metadata，也不得把 `UNKNOWN` 或 unresolved span 伪造成准确来源。

## 6. Timeline 的多层结构

### 6.1 第一层：患者主 Timeline

主 Timeline 主要显示现实世界中发生的临床 Event，而不是所有 Artifact 和审计活动。

示例：

```text
2026-08-20  Registration & AI pre-consult
2026-08-21  Hospital visit
2026-08-24  Patient follow-up
2026-08-26  Clinician review
```

每个大事件显示：

- 日期/时间；
- 事件名称；
- 一句简短概述；
- 参与角色；
- Artifact 数量；
- 是否有未解决评论、任务或冲突。

### 6.2 Hospital Visit 的视觉分组

现有数据模型将 `nurse_consult` 和 `doctor_consult` 保存为独立 Events。前端可以将同一次到院过程视觉分组为一个 `Hospital visit`，但不能在数据层静默合并它们。

```text
Hospital visit · 21 Aug
  ├─ Nurse consultation
  └─ Doctor consultation
```

这样可以同时满足：

- 用户以一次真实到院经历理解历史；
- nurse/doctor 的作者、时间、权限和 Artifacts 保持独立；
- 不破坏 Event 作为 canonical timeline unit 的合同。

正式实现不应仅凭“同一天”自动合并 Events，因为同一天可能发生多次无关诊疗。生产设计应使用显式 encounter/visit 分组标识；Demo 可以对 canonical fixture 使用明确、可审计的映射。

### 6.3 第二层：Event Detail / 生命周期时间线

点击大事件后，中央区域进入 Event Detail，而不是在主 Timeline 中无限向下展开。

页面提供明确返回入口：

```text
← Back to Timeline
```

Event Detail 使用小时间线展示该 Event 或视觉分组内部的信息生命周期：

```text
09:10  Consultation recording
09:18  Transcript
09:24  AI doctor consult summary
09:35  Clinician assessment & plan
10:02  Nurse supplement
later  Comments / revisions / review actions
```

该时间线主要按 Artifact 的 `created_at` 排列；主 Timeline 仍按 Event 的 `started_at` 排列。不得混淆两条时间轴。

后续修改仍属于原 Event，不得因为修改发生在另一天就制造新的医疗事件。

### 6.4 第三层：Artifact / Span

点击 Artifact 后进入详细阅读状态。长 transcript、正式 note 或 AI summary 应在中央可读区域展示，不应被压缩进狭窄侧栏。

右侧上下文可以同步展示：

- Comments；
- @mentions；
- Provenance；
- Versions / diff；
- Audit metadata。

Artifact 是评论和批注的主要锚点；需要讨论整个事件时，Comment 也可以锚定 Event。

最小来源单位仍是 Span：

- message；
- paragraph；
- transcript segment；
- timestamp range；
- structured section。

## 7. Notes 与协作

必须区分以下概念：

| 概念 | 含义 | 权威性/用途 |
|---|---|---|
| Clinician Note | 医生正式记录 | 代表 clinician-authored assessment/plan |
| Staff Note | staff/nurse 的独立记录 | 不得被医生覆盖为自己的内容 |
| Comment | 围绕 Event/Artifact 的协作讨论 | 可 reply、resolve、@mention |
| Highlight | Glance 的优先信息 | 必须有来源，可 accept/reject/pin |

顶层 `Notes` 是当前患者范围内的聚合投影，可以汇总：

- Clinician Notes；
- Staff Notes；
- 与当前患者有关的 comments；
- @mentions；
- unresolved discussions；
- 最近版本变化。

内容的 canonical 位置仍在原 Event/Artifact 中。点击 Notes 中的聚合项必须返回原始锚点，不能创建第二份脱离来源的副本。

医生工作台的 `Mentions` 是跨患者收件箱；患者工作区的 `Notes` 只显示当前患者范围。

## 8. Tasks 的定位

Task 不是普通个人待办，而是与患者照护有关的可追溯行动，例如：

- 追踪血液检查结果；
- 安排 follow-up；
- 护士回电；
- 审核 AI summary；
- 确认用药剂量。

Task 至少需要：内容、负责人、状态、截止时间、创建者和来源 Event/Artifact。

当前后端尚未实现正式 Task 表，因此设计原型中的 Tasks 不代表已经完成。

现阶段不将患者级 `Tasks` 设为与 Glance、Timeline、Notes 同级的主标签。Task 应出现在：

- 医生工作台：跨患者待处理列表；
- Glance：当任务足够重要时；
- 对应 Event/Artifact：显示任务从哪里产生。

当真实任务数量和工作流复杂度增加后，再评估独立患者级 Tasks 页面。

## 9. AI Assistant

医生端 AI Assistant 的定位是 patient-record copilot，而不是无边界医疗聊天机器人。

允许的核心用途：

- 比较症状随时间的变化；
- 查找未完成事项；
- 汇总某段时间内的记录；
- 找到支持某个陈述的所有证据；
- 帮助导航到 Event、Artifact 和 source span。

必须遵守：

- 只访问当前登录用户有权查看的患者数据；
- 患者切换后彻底清除前一患者上下文；
- 回答中的关键事实附来源；
- 明确区分原始事实、AI 总结和 AI 推断；
- 不覆盖 clinician-authored artifacts；
- 默认不把对话自动写入正式病历；
- 如需把 AI 内容提升为 note，必须经过明确的 clinician review/confirm 流程；
- 不直接执行医疗决定或外部医疗动作。

当前 AI Assistant 尚未实现。现有 M4 pipeline 是 source ingestion、redaction、extraction、summary 和 highlight pipeline，不能被描述成已完成的医生对话助手。

## 10. New Consult 与 transcript ingestion

当前 `Ingest transcript (demo)` 不再放在 Glance 和 Timeline 之间。

目标入口为患者标题区的：

```text
New consult
```

该入口可以进入独立流程或 modal：

1. 选择/创建 consult Event；
2. 录音或导入 source；
3. raw source 先持久化；
4. PHI redaction；
5. provider processing；
6. 生成 AI summary/highlight candidates；
7. clinician review；
8. 返回 Event Detail。

UI 调整不得改变现有安全合同：raw source 必须先保存；AI summary 独立存储；redaction 在 LLM egress 前执行；failed span anchoring 必须 drop，不能模糊伪造。

## 11. 身份、角色与多患者管理

### 11.1 正式产品不得显示角色切换器

当前 `Viewing as` 仅是 Demo 工具。正式产品中：

- 登录系统确定 `user_id`；
- 服务端数据库确定 role、clinic scope 和 patient/care-team scope；
- 前端根据身份进入对应 shell；
- 前端不得自行选择或提升角色。

前端隐藏按钮不构成安全边界，所有访问仍由后端 `authorize(...)` 执行。

### 11.2 患者切换安全

点击另一患者时必须清除：

- 当前 provenance/source；
- Event/Artifact 详情；
- AI Assistant 对话上下文；
- Comments/revision 缓存；
- 未保存草稿，或先明确提示用户处理草稿；
- 与前一患者相关的异步请求结果。

建议用 `patientId` 作为临床工作区根组件的 remount key，并对异步请求使用取消或 stale-response 防护。

### 11.3 Care-team assignment 缺口

当前后端主要实现 clinic scope，还没有完整的 patient ↔ care-team assignment 模型。正式的“My Patients”需要后端明确回答：

- 哪些患者被分配给当前医生；
- primary clinician 是谁；
- covering clinician 是谁；
- 多名医生共同管理患者时各自的访问权限；
- handover 和 assignment history。

在该模型完成前，不能把 clinic 内可访问患者等同于“分配给我的患者”。

## 12. 响应式与宽度策略

第一版窄原型不是专门设计的手机版，而是受到对话内预览宽度限制。其响应式重排可以作为窄屏方向参考，但桌面宽版才是本设计的主要基准。

建议断点行为：

### ≥ 1280px

- 完整三栏；
- 左侧患者导航持续显示；
- 中央内容使用主要宽度；
- 右侧 AI/Source 持续显示。

### 1024–1279px

- 左侧可保持较窄宽度；
- 右侧上下文可折叠为 drawer；
- 中央区优先保证 Timeline 和 Artifact 可读性。

### 768–1023px

- 左侧导航折叠；
- 患者列表通过 drawer 打开；
- 右侧上下文以 overlay/drawer 展示；
- 中央仍保持 Glance/Timeline/Notes 主导航。

### < 768px

- 视为临床移动端的简化布局，而不是把三栏机械压缩；
- 患者切换、Source Viewer 和 AI Assistant 使用全屏 sheet；
- 重要操作保持足够触控尺寸；
- 长 transcript 优先进入独立阅读页面。

移动端不是当前 MVP 的主要实现目标，因此不得为了移动端视觉完善而延迟 required gates 或桌面 Demo 主场景。

## 13. 可访问性与交互细节

后续实现至少应满足：

- 所有导航、Tab、Event、Artifact 和操作均可键盘访问；
- 使用语义化 `nav`、`main`、`aside`、`button`、heading；
- Tab 使用正确的 selected 状态；
- 不只依赖颜色表达风险、状态或作者类型；
- focus 样式清晰；
- Source Viewer 打开后有合理的焦点管理；
- drawer/modal 可用 Escape 关闭并把焦点返回触发按钮；
- loading、error、empty、no-permission 和 conflict 状态均有明确表现；
- 日期、角色、Artifact 类型使用稳定且一致的标签；
- accept/reject/pin 等图标必须有可读 label 或 accessible name；
- 动画尊重 `prefers-reduced-motion`。

## 14. 前端状态与路由建议

建议的页面/状态关系：

```text
/clinical
  └─ DoctorDashboard

/clinical/patients/:patientId
  └─ ClinicianShell
       ├─ PatientSidebar
       ├─ PatientWorkspace
       │    ├─ GlanceView
       │    ├─ TimelineView
       │    ├─ EventDetail
       │    ├─ ArtifactReader
       │    └─ NotesView
       └─ ContextPanel
            ├─ AiAssistant
            └─ SourceViewer
```

页面 URL 应能表达至少患者和主视图，例如：

```text
/clinical/patients/pat_001/glance
/clinical/patients/pat_001/timeline
/clinical/patients/pat_001/events/evt_doc_0821
```

这样可以支持刷新恢复、浏览器前进/后退、可审计深链接和从 Mentions 跳到准确位置。

前端不得把 role 或 clinic 作为可信 URL 参数传入后端进行授权。

## 15. 与现有实现的对应关系

| 目标能力 | C2 后状态 | 实现位置 |
|---|---|---|
| Glance 数据与反馈 | 已完成宽版集成 | `GlancePanel.tsx`；保留服务端排序与 accept/reject/pin |
| Provenance 解析 | 已迁移到右栏 | `ProvenancePanel.tsx`；exact span `<mark>`，unresolved fail closed |
| Event / encounter Timeline | 已完成 | `ClinicalTimeline.tsx`；仅显式非空 `encounter_id` 分组 |
| Event Detail / Artifact Reader | 已完成 | `ClinicalEventDetail.tsx`；双时间轴与生命周期 |
| Comments / @mentions | 已集成右栏 | `CommentThread.tsx`；Event/Artifact anchor、reply、resolve |
| Revision / diff / revert | 已集成右栏 | `RevisionPanel.tsx`；只对 note 展示 |
| Audit metadata | 已集成右栏 | `AuditList.tsx`；不进入主 Timeline |
| New Doctor Consult | 已完成 | `NewDoctorConsult.tsx`；strict parser/preview/C1 endpoint |
| 医生工作台 | 已完成 factual MVP | `ClinicianWorkspacePage.tsx`；无 fake Tasks/Mentions |
| Clinic Patients | clinic-scoped 已完成 | `ClinicianSidebar.tsx` + `GET /api/patients`；不称 My Patients |
| Notes 跨 Event 汇总 | 已完成安全客户端投影 | `ClinicalNotesView.tsx`；点击返回 canonical anchor |
| patient/role isolation | 已完成 | role/patient remount key + AbortController/stale guard |
| AI Assistant | 未实现/不显示 | 后续需 grounded query contract |
| Task / assignment | 未实现/不显示 | 后续需正式 schema 与权限 |
| 正式登录 | 未实现 | Demo toolbar 明确位于 product shell 外，DB role 仍为服务端权威 |

## 16. 建议实施顺序

该设计应分层实施，避免一次性改写所有功能：

1. **Clinical shell**：宽屏三栏、医生身份卡、患者区域占位、移除页面主干中的 demo switcher；
2. **Glance 重构**：保留现有功能，将 Source Viewer 移到右栏，移除重复 Recent Timeline；
3. **Timeline master/detail**：主 Event 时间轴、Event Detail、小时间线；
4. **Artifact reader**：Comments、Revision、Audit、Provenance 的上下文化展示；
5. **Notes 聚合**：当前患者 Notes 与跨患者 Mentions 分离；
6. **New Consult 流程**：迁移 IngestPanel，不改变 M4 ingestion/redaction 合同；
7. **医生工作台与患者列表**：在 assignment 权限模型明确后接入；
8. **AI Assistant**：在 grounded query、来源和写入边界明确后实现；
9. **响应式与视觉精修**：桌面主场景稳定后补足较窄屏幕。

## 17. 验收标准

完成医生端重构时，至少应验证：

### 使用场景

- 医生登录后能看到自己的身份和工作台；
- 医生可以搜索并切换授权患者；
- 进入患者后 10 秒内可从 Glance 理解当前重点；
- Glance 不被 Timeline 或 ingest 表单干扰；
- 点击 Highlight 可在右侧看到准确来源；
- Timeline 清楚显示大事件；
- 点击大事件可进入 Event 内部生命周期；
- 点击 Artifact 可查看内容、评论、版本和来源；
- @mention 可以从工作台/Notes 跳回准确锚点；
- New Consult 不占据默认阅读主干。

### 安全与正确性

- 正式页面没有角色切换器；
- 切换患者后不残留前一患者内容；
- 前端无权访问时不能通过隐藏路由或直接 API 获取数据；
- patient 永远不进入 clinical shell；
- clinician/staff 内容保持独立作者身份；
- AI summary 不覆盖 clinician note；
- 来源解析失败时不伪造 span；
- audit/activity 不被误显示为新的医疗 Event。

### 回归

- 现有 RBAC、revision、provenance、concurrency、patient-view 和 ingestion 测试继续通过；
- Glance warm read path 不引入同步全历史 LLM 调用；
- 重构不得降低当前服务端授权强度。

## 18. Staff、Nurse 与 Admin 的后续讨论边界

当前 `staff` 是一个较宽泛的 clinic support role；Demo 中主要用 nurse 工作流表达它，但它不必永久等同于 nurse。真实产品中可能包含：

- nurse；
- medical assistant；
- care coordinator；
- clinic operations staff。

因此不能简单复制医生工作区并只替换名称。Nurse 可能更关注 triage、vital signs、患者沟通、handover 和 task execution；clinician 更关注 assessment、plan、review 和最终临床权威。

后续讨论 Staff/Nurse 页面时，需要先决定：

1. `staff` 是否继续作为宽角色；
2. 是否新增明确 `nurse` 角色；
3. 不同 staff subtype 的写入权限和患者 assignment；
4. 哪些模块复用 clinical shell，哪些模块需要角色特有的默认视图。

`admin` 当前表示 clinic-scoped oversight，不是医疗权威角色。Admin 更适合处理用户、角色、clinic 配置、合规/audit oversight 和运营信息，不应默认拥有以 clinician 身份修改临床内容的能力。

## 19. 暂不纳入本次设计决定

本文件暂不决定：

- Patient View 的最终视觉和聊天交互；
- Staff/Nurse 的最终首页与专属工作流；
- Admin 信息架构；
- Task 数据模型的最终 schema；
- care-team assignment 的最终 schema；
- AI Assistant 的具体模型/provider；
- 生产认证供应商；
- 高级语音录入和 diarization。

这些内容需要在不破坏 provenance、RBAC 和纵向患者记录模型的前提下分别讨论。
