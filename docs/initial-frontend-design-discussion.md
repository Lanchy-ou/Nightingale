# 前端设计的初步讨论

> 讨论日期：2026-08-26  
> 项目：Nightingale 72 Hour Build  
> 文档用途：保存本轮前端产品讨论的背景、推理过程、已确认决定和后续问题，便于在新对话中连续工作。  
> 状态：初步设计共识，不代表相关页面已经在产品代码中全部实现。

## 1. 新对话建议阅读顺序

新对话中的 agent 应按以下顺序建立上下文：

1. `AGENTS.md`：产品合同、数据模型、RBAC、provenance 和当前阶段状态；
2. 本文件：理解本轮讨论是如何形成设计共识的；
3. `docs/clinician_workspace_design.md`：医生端详细实施规范；
4. `docs/patient_experience_design.md`：患者端详细复刻规范；
5. 当前前端代码，尤其：
   - `frontend/src/App.tsx`
   - `frontend/src/pages/PatientPage.tsx`
   - `frontend/src/pages/PatientViewPage.tsx`
   - `frontend/src/components/GlancePanel.tsx`
   - `frontend/src/components/Timeline.tsx`
   - `frontend/src/components/EventCard.tsx`
   - `frontend/src/components/ProvenancePanel.tsx`
   - `frontend/src/components/CommentThread.tsx`

不要只看交互原型或本文档就假设代码已经完成重构。

## 2. 讨论开始时的页面状态

本轮讨论开始时，用户在本地浏览器查看的是当前 React/Vite Demo：

```text
http://127.0.0.1:5173/
```

页面默认以 Clinician 视角显示固定患者 Alice Tan，并提供 Demo-only 角色切换器。

当前页面从上到下大致为：

```text
Viewing as 角色切换器
Patient header
Glance
Ingest transcript
Provenance（按操作出现）
Timeline
展开后的 Artifacts / comments / revisions / audit
```

这一版的主要目标是证明 M1–M6 的功能和安全链路成立，不是最终产品视觉设计。

## 3. 关于角色切换与正式登录的初步确认

用户首先确认：当前页面可以切换角色，但正式上线后每个用户只能看到自己的页面，不能保留这种角色切换标识。

讨论达成以下共识：

- 当前 `Viewing as` 是 Demo 工具；
- 正式产品必须移除；
- 正式登录由 Session/JWT 等认证机制确定用户；
- 服务端数据库确定 role、clinic scope 和 patient/care-team scope；
- patient 登录后进入独立 Patient App；
- clinician 登录后进入 Clinical App；
- staff/admin 根据各自权限进入对应工作区；
- 前端路由和页面裁剪不能替代后端 RBAC；
- 当前后端已经以 DB User 为身份/角色权威，`X-Role` 只是 Demo 一致性断言，不能提权。

同时澄清：当前页面主体可以作为对应角色页面的功能基础，但不能“原封不动上线”。至少需要移除 Demo switcher、接入真实认证和建立完整的产品 shell。

## 4. 用户对当前 Clinician 页面提出的核心问题

用户从真实网站使用体验出发，认为当前医生页面过于粗糙、简陋和杂乱。具体意见包括：

1. 医生页面缺少个人身份信息，例如头像、个人资料和登录信息；
2. Glance 基础功能可用，但整体视觉设计过于粗糙；
3. 用户不理解 `Ingest transcript` 的作用，也不理解它为什么插在 Glance 和 Timeline 之间；
4. 页面完全从上到下排列，模块之间没有主次；
5. Timeline 更像折叠列表，不像真正的时间轴；
6. 展开 Timeline 后，Artifact、评论、修改等信息全部向下堆叠，导致杂乱；
7. `View source` 功能成立，但来源展示方式不够精美、清晰；
8. 医生需要 AI Chat/Copilot，不能只依赖 Glance；
9. 当前页面像单个患者档案，而真实医生需要管理多个患者；
10. 两名医生可能共同管理同一患者，因此需要考虑协作与 assignment；
11. 医生登录后应该先看到自己的工作环境和患者列表，再进入单患者工作区；
12. Patient View 虽然功能较少，但视觉重点不清楚；
13. 当前患者 AI 输入像表单，不像愿意持续使用的聊天产品；
14. 患者是重要用户，Patient View 必须简单、清楚并具有对话吸引力。

这次批评被判断为正确且重要：问题不只是颜色、圆角和阴影，而是页面信息架构和真实使用场景没有完整表达。

## 5. 对当前 Demo 性质的重新定位

讨论中形成了一个关键判断：

> 当前 `PatientPage` 是“单患者临床工作区的功能垂直切片”，不是医生每天使用的完整产品。

它已经证明：

- Glance 排名与反馈；
- Provenance 解析；
- Event/Artifact 数据组织；
- clinician/staff note 隔离；
- comments 和 @mentions；
- revision、revert、audit；
- server-side RBAC；
- patient-safe independent view。

但它缺少：

- 医生工作台；
- 多患者导航；
- care-team assignment；
- 正式认证；
- 成熟的信息架构；
- 医生 AI Assistant；
- 患者连续聊天；
- 完整响应式设计。

因此后续方向不是推翻现有数据和权限能力，而是为已有能力建立正确的产品外壳。

## 6. 医生登录后的总体结构讨论

讨论了三种医生登录体验：

1. 工作台优先；
2. 患者搜索优先；
3. 患者工作区优先，并在左侧持续显示患者列表。

用户选择“第三种 + 第一种”的组合：

- 医生首次登录进入工作台；
- 进入患者后，左侧患者列表持续存在；
- 医生可以在患者之间快速切换；
- 页面刷新可恢复最近患者，但必须有返回工作台入口。

用户进一步明确左侧边栏的设想：

- 最上方是医生本人信息；
- 医生身份区域面积可以稍大；
- 下方是工作台入口；
- 再下方是患者列表；
- 点击患者进入该患者工作区；
- 继续点击其他患者可切换。

最终建议的医生端基本框架：

```text
左侧导航                    中央患者工作区              右侧上下文
医生身份卡                  患者标题                    AI Assistant
My Dashboard                Glance                      或
Tasks / Mentions            Timeline                    Source Viewer
患者搜索与列表              Notes
```

### 6.1 医生身份卡

医生身份卡应显示：

- 头像；
- 姓名；
- role；
- clinic；
- Profile / Settings。

身份卡应比普通头像菜单更清楚，但不能占据过多空间，因为患者切换是高频任务。

### 6.2 患者列表

患者列表不能只是一串姓名，应支持：

- 搜索；
- 最近查看；
- 分配给我的患者；
- 需要处理；
- 全部授权患者。

患者行可以显示低敏感度状态，例如：

- `2 items need review`；
- `updated today`；
- `no new updates`。

不建议在共享屏幕环境中直接展示过多病情细节。

### 6.3 患者切换安全

切换患者时必须清除：

- 前一患者的 Source Viewer；
- Event/Artifact detail；
- AI conversation context；
- comments/revisions 缓存；
- 未完成请求；
- 前一患者草稿，或明确提醒用户先处理草稿。

否则会产生患者信息串线风险。

## 7. Clinician 工作区的核心设计决定

### 7.1 主导航

中央主导航暂定为：

```text
Glance | Timeline | Notes
```

不再使用 `Overview` 替代 `Glance`。

`Glance` 是项目核心产品术语，必须保留。

### 7.2 Glance

Glance 只回答：

> 医生现在最需要关注什么？

用户认为第一版原型中的 `What matters now` 不应该替代 Glance。讨论采纳该意见。

Glance 内不再放 `Recent Timeline`，因为：

- Timeline 已有独立页面；
- 重复内容会削弱 Glance 的重点；
- Glance 应专注于最高价值 Highlights。

每条 Highlight 继续保留：

- text；
- risk reason；
- View source；
- accept / reject / pin；
- clinician-confirmed / needs-review 等状态。

### 7.3 View source

点击 `View source` 后：

- 中央 Glance 不离开；
- 右侧自动切换到 Source Viewer；
- 显示 Event → Derived Artifact → Source Artifact → exact span；
- 原文准确高亮；
- 显示作者和时间；
- 冲突时可跳到 clinician-authored note。

来源展示不应再插入页面主干，避免打断阅读。

### 7.4 Ingest transcript

用户不理解该模块是合理的，因为它本质上是 Demo/source ingestion 工具，不是医生默认阅读模块。

决定：

- 从 Glance 和 Timeline 之间移除；
- 变成患者标题区的 `New consult`；
- 或在 Event Detail 中提供录音/导入 source 的流程；
- 继续遵守 raw source first、redaction before LLM、derived content separated 等安全合同。

## 8. Timeline 的层级讨论

用户提出了一套“大时间线 → 小时间线 → 最小内容单位”的结构。

这一想法与现有 canonical model 高度一致：

```text
Main Timeline
  ↓
Event Detail / Artifact lifecycle
  ↓
Artifact
  ↓
Span / exact source
```

### 8.1 第一层：大时间线

主 Timeline 按现实世界中的日期或大事件排列，例如：

```text
20 Aug  Registration & AI pre-consult
21 Aug  Hospital visit
24 Aug  Patient follow-up
26 Aug  Clinician review
```

主 Timeline 不展示全部评论、revision 或 audit。

### 8.2 第二层：Event 内部小时间线

点击某个大事件后，进入 Event Detail：

```text
09:10  Consultation recording
09:18  Transcript
09:24  AI doctor consult summary
09:35  Clinician assessment & plan
10:02  Nurse supplement
later  Comments / revisions / review actions
```

讨论决定：不要在主 Timeline 中无限展开，应该进入清晰的 Event Detail，并保留 `Back to Timeline`。

### 8.3 第三层：Artifact / Span

点击某个 recording、transcript、summary 或 note 后，查看：

- 内容；
- 作者；
- 时间；
- comments；
- @mentions；
- versions；
- audit metadata；
- provenance/source span。

长 transcript 或 note 应在中央可读区域展示，不应被压进狭窄侧栏。

### 8.4 Hospital Visit 分组

用户希望一次到院过程作为一个“大事件”，其中包含录音、医生反馈、护士批注和 AI summary。

现有数据库把 `nurse_consult` 和 `doctor_consult` 保存为独立 Events。讨论决定：

- 数据层继续保持独立 Events；
- UI 可以把同一次到院视觉分组为 `Hospital visit`；
- 不得按“同一天”静默合并；
- 正式产品应有明确 encounter/visit grouping id；
- Demo 可对 canonical fixture 使用明确映射。

这样兼顾真实用户理解和 Event/Artifact/权限合同。

## 9. Notes、Comments、Highlights 与 Tasks

讨论中澄清了容易混淆的概念：

| 概念 | 含义 |
|---|---|
| Clinician Note | 医生正式 clinical assessment/plan |
| Staff Note | staff/nurse 的独立记录 |
| Comment | 锚定 Event/Artifact 的协作讨论，可 reply/resolve/@mention |
| Highlight | Glance 中的优先信息，必须有来源 |

顶层 `Notes` 是当前患者范围内的聚合投影，可展示：

- clinician notes；
- staff notes；
- comments；
- @mentions；
- unresolved discussions；
- version changes。

点击聚合内容必须返回原 Event/Artifact 锚点，不能复制一份脱离来源的新内容。

### 9.1 Tasks 的讨论

用户最初不清楚 Tasks 有什么用。讨论澄清：Task 是与患者照护相关的行动，例如：

- 追踪 blood test；
- 安排 follow-up；
- 护士回电；
- 审核 AI summary；
- 确认 medication dose。

当前后端尚未实现正式 Task table。

阶段性决定：

- 不把患者级 Tasks 与 Glance、Timeline、Notes 设为同级主标签；
- 重要 Task 可以进入 Glance；
- Task 在对应 Event/Artifact 中保留来源；
- 医生工作台提供跨患者 Tasks；
- 数据量和工作流成熟后再评估独立患者级 Tasks 页面。

## 10. 医生 AI Assistant 的定位

用户认为医生需要 AI Chat，不能只依赖 Glance。该方向被采纳，但职责被收紧。

医生 AI Assistant 应是 patient-record copilot，可以：

- 比较症状随时间变化；
- 查找未完成事项；
- 查找支持某个陈述的所有证据；
- 汇总指定时间段；
- 导航到 Event、Artifact 和 exact span。

它不应该：

- 成为无边界诊断机器人；
- 覆盖 clinician note；
- 自动写入正式病历；
- 隐藏 AI inference；
- 直接执行医疗决定。

右侧栏在 `AI Assistant` 和 `Source Viewer` 之间切换被认为合理。

## 11. Clinician 交互原型反馈

第一版交互原型包含：

- 医生身份卡；
- 左侧患者列表；
- Overview / Timeline / Notes / Tasks；
- 右侧 Source / AI Assistant；
- Glance cards；
- 简化时间线。

用户提出进一步修改：

- `Overview` 改为 `Glance`；
- 不用 `What matters now` 替代 Glance；
- 移除 Glance 中的 Recent Timeline；
- View source 使用右侧上下文；
- Timeline 采用大事件和 Event 内部小时间线；
- Notes 聚合 comments/@mentions；
- Tasks 暂不作为同级主页面。

第二版宽屏原型按这些意见调整，用户评价：

> “算是很不错的一版了；设计方案我认为就可以暂时这样定下来。”

因此 Clinician 设计被记录到：

```text
docs/clinician_workspace_design.md
```

## 12. 关于窄版和移动端的澄清

对话内第一版原型看起来较窄。需要保留的事实是：

- 它不是专门设计的手机版；
- 主要是受到对话内 visualization 宽度限制；
- 它有响应式重排，因此可以作为窄屏方向参考；
- 第二版宽屏原型才是 Clinician 桌面端基准。

医生端主要桌面目标为 1280px 及以上的三栏布局。

## 13. Patient View 的讨论与确认

用户要求患者界面必须简单、清楚。

患者端没有复用医生三栏布局，而是设计为：

```text
顶部导航
  Home | AI Assistant | Help | Patient profile

Home
  1. What you need to know
  2. Next appointment
  3. Your next steps
  4. AI Assistant CTA
  5. Instructions from your doctor

AI Assistant
  独立连续聊天页面
```

### 13.1 Patient Home 的核心原则

- 第一眼只有一个主要重点；
- 不展示患者版完整 Timeline；
- 不展示 internal provenance；
- 不展示 clinician/staff comments；
- 不展示 raw AI-scribed notes；
- 只展示 patient-facing summary、instructions、follow-up 和本人 sessions；
- 宽屏使用两栏，但信息层级仍然简单；
- 手机端自然堆叠。

### 13.2 Home 的优先顺序

```text
1. 当前最需要知道的事
2. 下一次明确安排
3. 下一步行动
4. 报告变化的 AI 入口
5. 历史医生说明
```

### 13.3 Patient AI Assistant

用户此前不喜欢 textarea + Send 的表单式交互，因此设计为独立聊天页：

- 明确 opening prompt；
- quick replies；
- 左右消息气泡；
- 持续 composer；
- Enter 发送；
- Back to Home；
- 非急诊用途提示；
- 不冒充医生；
- 不声称医生已阅读，除非后端有真实状态。

Patient 交互原型完成后，用户评价：

> “perfect；我没什么好说的，非常符合我现在的想象。”

因此 Patient 设计被记录到：

```text
docs/patient_experience_design.md
```

## 14. Patient 原型中必须记住的“视觉不等于能力”

Patient 原型为了表达最终体验，包含了以下视觉状态：

- 结构化 Next appointment；
- 可以勾选的 checklist；
- 多轮 AI conversation；
- clinician display name；
- Contact clinic 按钮。

但当前 M6 后端并没有全部对应能力：

- `follow_up` 当前主要是自由文本，不是结构化 appointment；
- 尚无 Task model 和持久化完成状态；
- 当前 session POST 是一次 patient update ingestion，不是完整连续聊天 API；
- patient-view 当前未返回 clinician display name；
- Contact clinic 尚未连接真实渠道。

后续实现必须选择：

1. 先补齐安全、权威的后端能力；或
2. 在能力未完成时使用明确降级 UI。

禁止通过客户端解析、猜测或本地状态伪装成 authoritative clinical data。

## 15. Staff、Nurse 与 Admin 的初步讨论

用户询问 `staff` 是否就是护士，并指出如果是护士，页面可能和医生不同。

当前结论：

- 现有 `staff` 是宽泛的 clinic support role；
- Demo 主要通过 nurse workflow 表达；
- 它不一定永久等同于 nurse；
- 真实产品可能包含 nurse、medical assistant、care coordinator、operations staff；
- Staff/Nurse 不应简单复制医生工作区并只替换名称；
- Nurse 可能更关注 triage、vital signs、patient communication、handover 和 task execution；
- Clinician 更关注 assessment、plan、review 和最终临床权威；
- 后续需要决定是否新增明确 `nurse` role 或 staff subtype。

Admin 当前含义：

- clinic-scoped oversight；
- 用户/角色/clinic 配置；
- compliance/audit oversight；
- 运营信息；
- 不代表 clinical authority；
- 不应默认能以 clinician 身份修改正式临床内容。

Staff/Nurse 和 Admin 的详细页面尚未讨论完成。

## 16. 已形成的专项文档

### Clinician

```text
docs/clinician_workspace_design.md
```

包含：

- 三栏结构；
- 医生身份卡和患者列表；
- Glance；
- 分层 Timeline；
- Notes；
- Tasks 定位；
- AI Assistant；
- Source Viewer；
- New Consult；
- routing/state；
- responsive；
- accessibility；
- 当前实现映射；
- 实施顺序；
- 验收标准。

### Patient

```text
docs/patient_experience_design.md
```

包含：

- Home 页面复刻规范；
- AI Assistant 独立对话页面；
- 颜色、字体、间距、圆角；
- 桌面/平板/手机断点；
- 当前 API 映射；
- patient-safe whitelist；
- loading/empty/error；
- accessibility；
- 安全合同；
- 实施顺序；
- 复刻验收清单。

## 17. 本轮未实施的内容

本轮工作主要是产品讨论、交互原型和 Markdown 设计记录。

没有完成以下产品代码改造：

- 没有把现有 Clinician 页面改成三栏 shell；
- 没有移除产品代码中的 Demo role switcher；
- 没有实现医生工作台；
- 没有实现患者列表/assignment；
- 没有实现医生 AI Assistant；
- 没有实现 Patient 连续聊天；
- 没有实现结构化 appointment；
- 没有实现 Task table；
- 没有实现 Staff/Nurse/Admin 专属页面。

原型用于确认设计方向，不是生产实现。

## 18. 新对话应从哪里继续

如果下一轮继续产品讨论，建议顺序：

1. Staff/Nurse 是否拆分角色；
2. Nurse 工作台的核心场景；
3. Admin 的最小合理范围；
4. care-team assignment；
5. Task model 和任务工作流；
6. AI Assistant 的真实数据与安全合同；
7. 选择 Clinician 或 Patient 页面开始实际重构。

如果下一轮开始实现，必须先明确实施范围，例如：

- 只做 Clinician shell；
- 只做 Glance + Source Viewer；
- 只做 Timeline master/detail；
- 或只做 Patient Home 视觉重构。

不要一次性同时实现 Clinician、Patient、Staff、Admin、Task、assignment 和 AI Assistant。应按专项文档中的实施顺序逐步完成，每一步保留现有 RBAC、provenance 和 required tests。

## 19. 本轮最终共识摘要

```text
Clinician
  登录先有工作台
  左侧医生身份 + 患者列表
  中央 Glance | Timeline | Notes
  Timeline = 大事件 → Event 内小时间线 → Artifact → Span
  右侧 AI Assistant | Source Viewer
  Ingest transcript 移入 New Consult

Patient
  独立、简单、行动优先
  Home = 当前说明 + 预约 + 下一步 + AI 入口 + 医生说明
  AI Assistant = 独立连续对话页面
  永不暴露内部临床工作区

Staff/Nurse/Admin
  尚待专项讨论

Implementation
  当前只是设计共识和原型
  后续必须区分已有后端能力与目标体验
```
