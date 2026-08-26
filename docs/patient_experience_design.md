# Nightingale Patient Experience 前端复刻规范

> 状态：阶段性设计决定（目标设计，尚未全部实现）  
> 决定日期：2026-08-26  
> 适用范围：Patient Home 与 Patient AI Assistant  
> 优先级：患者安全与清晰度 > 行动可理解性 > 对话吸引力 > 视觉装饰

## 1. 文档目的

本文档是患者端前端设计的 canonical implementation specification。后续 agent 应能够仅依据本文档，复刻 2026-08-26 确认的患者端交互原型，同时保持 M6 已实现的 patient-safe 数据白名单、服务端 RBAC 和 AI ingestion 安全合同。

本文档明确区分：

- **当前已实现能力**：现有 API、RBAC、安全投影和单次 patient session ingestion；
- **目标前端设计**：确认的主页布局、视觉系统、独立 AI 对话界面和响应式交互；
- **尚缺后端能力**：结构化 appointment、可完成 Task、连续 conversation/session API。

不得为了复刻视觉效果而伪造后端状态、扩大患者可见字段或绕过服务端权限。

## 2. 患者端产品原则

Patient View 只回答：

> 我现在需要知道什么、做什么，以及如何向诊所报告变化？

患者端不是医生工作区的简化复制，也不是完整病历浏览器。设计必须做到：

1. 第一眼有唯一重点；
2. 下一步行动明确；
3. 医生说明容易找到；
4. AI 对话入口明显且愿意使用；
5. 不暴露内部 clinical content；
6. 不要求患者理解 Event、Artifact、provenance、revision 等内部术语；
7. 桌面端充分利用宽度，移动端自然重排而不是机械缩小。

## 3. 患者可见范围：永久安全边界

患者端只允许展示服务端 patient-safe projection 返回的内容。

当前允许：

- patient-facing summary；
- clinician-authored patient instructions；
- 明确存在的 follow-up 文本；
- 本患者自己的 patient AI session 列表；
- 患者本人提交的新 recovery update。

当前禁止：

- internal clinician comments；
- internal staff comments；
- raw AI-scribed clinical notes；
- clinician/staff 的内部 reasoning；
- Highlight importance score、entity key、review status；
- provenance pointer、source span；
- audit logs、revision history；
- 其他患者数据；
- 未经服务端白名单允许的 Artifact content。

前端不得请求 clinical Timeline、Glance、comments、audit、revisions 后再自行过滤。患者页面只调用 patient-safe endpoint 和患者 session endpoint。

## 4. 页面结构总览

患者端采用一个简单的顶部导航和两个主要页面：

```text
Patient App Shell
  ├─ Home
  │   ├─ Greeting
  │   ├─ What you need to know
  │   ├─ Next appointment
  │   ├─ Your next steps
  │   ├─ AI Assistant CTA
  │   └─ Instructions from your doctor
  │
  └─ AI Assistant
      ├─ Conversation context
      ├─ Safety message
      ├─ Message stream
      ├─ Quick replies
      └─ Persistent composer
```

建议路由：

```text
/patient/home
/patient/assistant
```

如果 MVP 暂不引入路由库，也必须确保浏览器刷新、前进/后退和页面状态不会导致患者看到 clinical shell。

## 5. 顶部导航

### 5.1 桌面结构

顶部导航横跨页面，白色/深色主题表面，底部一条轻边界。

左侧：

- Nightingale logo；
- 产品名称。

右侧：

- Home；
- AI Assistant；
- Help；
- 患者头像；
- 患者姓名；
- My profile。

不得出现：

- role switcher；
- clinic staff controls；
- patient selector；
- clinician-only navigation；
- Demo 权限说明。

### 5.2 导航状态

当前页面使用柔和绿色背景和更深文字标记 selected state。不得仅依赖图标或颜色，按钮必须有文字和正确的 active/pressed 状态。

### 5.3 移动端

小于 560px 时：

- 保留 logo mark；
- Home、AI Assistant 和 Help 可只显示图标，但必须有 accessible name；
- 头像保留；
- 患者姓名文字可以隐藏；
- 不使用汉堡菜单隐藏唯一关键入口 AI Assistant，除非后续导航显著增加。

## 6. Home 页面

### 6.1 内容宽度

桌面端 Home 内容最大宽度约 1080px，水平居中。

推荐：

```css
width: min(1080px, calc(100% - 40px));
margin-inline: auto;
```

不要恢复当前 `.app { max-width: 860px }` 的窄页面限制。

### 6.2 Greeting

页面顶部显示：

- 当前日期；
- `Good morning, Alice` 或本地化问候；
- 一句页面目的：`Here is what you need to know and do next.`；
- `Contact clinic` 次要操作。

Greeting 负责建立个人感和页面方向，不应堆叠医疗事实。

### 6.3 第一视觉层：What you need to know

这是患者 Home 的最高优先级区域，位于 Greeting 下方左侧，占第一行主要宽度。

桌面第一行比例：

```text
What you need to know : Next appointment ≈ 1.55 : 0.8
```

内容：

- 小标签 `What you need to know`；
- 一句清晰的当前结论；
- 一段必要的解释；
- 最近更新时间；
- clinician display name（仅当 patient-safe API 明确返回；当前 API 未返回 author name，不得客户端猜测）。

示例视觉文案：

```text
Your headache is improving. Continue your current medication
and monitor the morning nausea.

Your blood test result is still pending. The clinic will review it
and contact you if your plan needs to change.
```

数据来源只能是 `current_summary.instruction` 和 `current_summary.follow_up` 的安全投影。原型中的自然语言分段是视觉示例；实际实现不得从 clinician note 或 Glance 补全文案。

当 `current_summary === null`：

- 不显示空白大卡；
- 显示简单 empty state：暂时没有新的说明；
- 提供联系诊所入口；
- 不调用 LLM 即时编造 summary。

### 6.4 Next appointment

右侧卡片显示：

- Next appointment；
- 日期；
- 时间；
- 类型；
- clinician/clinic。

当前 M6 API 只有自由文本 `follow_up`，没有结构化 appointment date/time/clinician。后续 agent 有两个合法选择：

1. 在后端新增 patient-safe structured appointment projection；
2. 在能力未完成前，将该卡降级为 `Upcoming follow-up` 并原样显示 `upcoming[].text`。

禁止从自由文本中静默解析并伪造准确日期、时间或医生身份。

### 6.5 第二视觉层：Your next steps

Next Steps 位于第二行左侧，占主要宽度。

每项显示：

- 动作文本；
- 时间/频率/截止说明；
- 完成状态（仅在正式 Task 能力存在时）。

原型允许点击 checklist，是为了验证交互感。当前后端没有 Task model，因此生产实现不得把本地勾选当作真实完成状态。

在 Task API 完成前：

- 将 `upcoming[].text` 以只读步骤展示；或
- 明确标注状态只保存在当前设备且不代表诊所收到确认，但不推荐此方案。

正式 checklist 需要服务端 Task 至少提供：

- task id；
- status；
- due time；
- patient/clinic scope；
- source Event/Artifact；
- allowed patient action。

### 6.6 AI Assistant CTA

第二行右侧是一块高识别度但不压过当前医疗说明的 AI Assistant 入口。

结构：

- AI/sparkles icon；
- `How are you feeling today?`；
- 一句解释：向助手报告变化，它会帮助整理给 care team；
- 主按钮 `Talk to AI Assistant`。

点击后进入独立 AI Assistant 页面。不得在 Home 卡片里继续使用三行 textarea + Send 的表单式交互。

### 6.7 Instructions from your doctor

位于主页第三层，横跨内容宽度。

列表按 `event_time` 倒序，显示：

- 日期；
- 简短标题；
- patient-facing instruction 摘要；
- 可选 follow-up。

标题如果后端没有提供，可使用中性固定标签，例如 `Doctor's instruction`，不得根据内部 clinical note 推断标题。

点击后可以进入 patient-safe instruction detail，但不能导航到内部 Artifact reader 或 raw source。

## 7. Home 页面信息层级

严格遵守以下顺序：

```text
1. 当前最需要知道的事
2. 下一次明确安排
3. 下一步行动
4. 报告变化的 AI 入口
5. 历史医生说明
```

不添加以下常见但无必要的模块：

- 患者版 Glance；
- 完整 Timeline；
- 统计图表；
- AI 置信度；
- audit/provenance；
- internal care-team comments；
- 新闻、健康文章或运营推广；
- 为填满宽屏而制作的无意义 KPI 卡片。

## 8. AI Assistant 独立页面

### 8.1 设计目的

AI Assistant 应具有成熟聊天产品的连续对话体验，而不是一次性提交表单。

核心感受：

- 容易开始；
- 不需要患者知道应该如何组织医学语言；
- 对话保持上下文；
- 明确告诉患者它不是急救或诊断替代；
- 对话结果如何进入 care record 必须透明。

### 8.2 桌面布局

桌面端使用两栏：

```text
左侧约 245px                右侧弹性
Back to home                Assistant header
AI Assistant                Message stream
用途与安全说明              Quick replies
Conversation/session list   Persistent composer
```

左侧不显示 clinician-only data，也不提供跨患者切换。

### 8.3 Header

显示：

- 在线/可用状态标记；
- `Nightingale AI Assistant`；
- `For non-emergency updates about your care`。

不得使用容易让患者误以为真人医生实时在线的文案，例如 `Your doctor is online`。

### 8.4 Message stream

消息区域宽度约 720px，居中，保留足够留白。

消息样式：

- AI：左侧、柔和浅绿/深绿表面、左下角较小圆角；
- Patient：右侧、品牌绿色填充、右下角较小圆角；
- 最大宽度约 78%；
- 移动端最大宽度约 90%；
- 文本行距约 1.5–1.6；
- 不使用过度头像、时间戳和装饰来增加噪音。

### 8.5 Opening prompt

第一句应具体而容易回答，例如：

```text
Hi Alice. How have your headache and nausea changed since your last update?
```

真实实现只能引用 patient-safe、明确允许用于对话的上下文。若没有安全上下文，使用中性开场：

```text
Hi Alice. How are you feeling today?
```

### 8.6 Quick replies

开场下方提供 2–3 个快捷回复：

- My headache is better；
- I still feel nauseous；
- I have a new symptom。

快捷回复只帮助输入，不直接提交。点击后填入 composer，患者仍可编辑。

### 8.7 Composer

底部 composer 在可视区域内持续可见：

- 多行 textarea；
- placeholder：`Tell me how you are feeling…`；
- Send 按钮；
- 明确提示：`Do not use this for emergencies.`；
- Enter 发送、Shift+Enter 换行；
- 发送中 disabled；
- 失败时保留患者文字并显示可重试错误；
- 不在失败后静默清空输入。

### 8.8 对话结果与医疗安全

AI 可以：

- 询问症状变化；
- 帮助患者用清晰语言描述情况；
- 整理 recovery update；
- 提醒患者按现有 patient-facing instructions 行动；
- 建议联系诊所或急救服务。

AI 不可以：

- 冒充医生诊断；
- 修改 medication plan；
- 隐藏或替代紧急医疗提醒；
- 展示内部 clinical note；
- 自动把生成内容变成 clinician-authored content；
- 声称诊所已经看到消息，除非后端有确切 delivery/acknowledgement 状态。

## 9. 当前 API 与目标界面的映射

当前 endpoint：

```text
GET /api/patients/{patient_id}/patient-view
```

当前返回：

```text
patient_id
display_name
current_summary
instructions[]
upcoming[]
sessions[]
```

映射：

| 目标区域 | 当前数据 | 状态 |
|---|---|---|
| Greeting | `display_name` | 可直接实现 |
| What you need to know | `current_summary.instruction/follow_up` | 可直接实现 |
| Updated date | `current_summary.event_time` | 可直接实现 |
| Clinician name | 当前未提供 | 不得猜测；需安全扩展 API |
| Next appointment | `upcoming[].text` | 只能先做自由文本版本；结构化卡需要扩展 |
| Next steps | `upcoming[]` | 可做只读；完成状态需要 Task model |
| Doctor instructions | `instructions[]` | 可直接实现 |
| Session history | `sessions[]` | 只能显示会话日期/类型 |
| 连续 chat messages | 当前未返回 | 需要新 conversation API |

当前写入：

```text
POST /api/patients/{patient_id}/sessions
```

当前实现把一次输入创建为 patient session source，并运行现有 ingestion pipeline。它不是完整的多轮聊天 API。

后续 agent 不得仅通过前端拼接消息，就宣称连续对话已持久化或已被 care team 阅读。

## 10. 建议组件结构

```text
PatientAppShell
  ├─ PatientTopNav
  ├─ PatientHomePage
  │   ├─ PatientGreeting
  │   ├─ CurrentCareSummary
  │   ├─ UpcomingAppointment
  │   ├─ PatientNextSteps
  │   ├─ AssistantCallToAction
  │   └─ PatientInstructionList
  └─ PatientAssistantPage
      ├─ ConversationSidebar
      ├─ AssistantHeader
      ├─ MessageList
      ├─ QuickReplies
      └─ MessageComposer
```

组件边界必须服务于数据和交互边界，不要为单个静态标签创建无意义组件。

现有 `PatientViewPage.tsx` 可以逐步拆分，不需要一次性引入复杂状态管理框架。

## 11. 视觉系统

### 11.1 颜色基准

目标原型使用克制的医疗绿色，而不是通用蓝色后台模板。

建议 CSS tokens：

```css
--patient-brand: #1e6a57;
--patient-brand-deep: #163e34;
--patient-brand-soft: #e5f4ee;
--patient-page: #f6faf8;
--patient-surface: #ffffff;
--patient-text: #18231f;
--patient-muted: #63766f;
--patient-border: #d9e5e0;
```

深色主题使用相同语义，而不是简单反色：

```css
--patient-page-dark: #111916;
--patient-surface-dark: #19231f;
--patient-text-dark: #edf4f1;
--patient-muted-dark: #9caea7;
--patient-border-dark: #35443f;
```

品牌色用于：

- logo；
- primary CTA；
- patient message；
- completed state；
- active navigation。

不要给每个卡片使用不同颜色。

### 11.2 字体与层级

- 字体：system/Inter 类无衬线；
- 页面问候标题：约 30px desktop / 25px mobile，weight 500；
- 主要 summary：约 23px desktop / 20px mobile，weight 500；
- section heading：18–19px，weight 500；
- body：13–15px；
- secondary metadata：11–12px；
- 不使用 weight 700/800 制造过强视觉噪音。

### 11.3 圆角、边界与阴影

- App shell：约 20px；
- Primary summary / appointment：约 18px；
- ordinary surface：约 17px；
- controls：9–11px；
- message bubble：约 15px；
- 使用轻边界区分表面；
- 阴影只用于 app shell 和 chat composer 等真正悬浮层；
- 不给每个模块堆叠重阴影。

### 11.4 图标

使用一致的线性图标系统，例如 Lucide：

- heart-pulse；
- home；
- message-circle；
- circle-help；
- phone；
- info；
- stethoscope；
- sparkles；
- check；
- arrow-right / arrow-up。

图标是辅助信息，关键操作必须有文字或 accessible label。

## 12. 响应式规则

### ≥ 900px

- Home 第一、二行均为两栏；
- 内容最大宽度 1080px；
- Chat 显示约 245px conversation sidebar；
- Message stream 居中且最大约 720px。

### 600–899px

- Home 两栏按优先级堆叠为一栏；
- What you need to know 位于最上；
- Next appointment 其次；
- Next Steps 后接 AI CTA；
- Chat 隐藏 conversation sidebar；
- Back to Home 移到 chat header 或顶部导航。

### < 600px

- 页面左右 padding 约 14px；
- 顶部导航文字按规则隐藏；
- Home 标题缩小但不低于可读层级；
- 所有卡片单列；
- Instructions 日期列缩小；
- Message bubble 最大宽度约 90%；
- composer 距屏幕左右约 14px；
- 触控目标至少约 44px；
- 不产生横向滚动。

窄屏版是患者产品的重要正式场景，但不得向移动端暴露桌面端隐藏的额外数据。

## 13. Loading、Empty、Error 与权限状态

每个区域必须有明确状态：

### Initial loading

- 使用稳定 skeleton，避免页面大幅跳动；
- 不显示 clinician workspace 的 loading fallback。

### Empty

- 无 current summary：显示“暂无新的照护说明”；
- 无 upcoming：不显示空 checklist，可显示“暂无待办安排”；
- 无 instructions：显示简单说明，不制造假记录；
- 无 sessions：AI Assistant 仍可开始新的安全对话。

### Error

- patient-view 加载失败：提供重试；
- message 发送失败：保留输入并允许重试；
- 不向患者展示内部 endpoint、stack trace 或 raw authorization reason。

### Authorization

- 401：引导重新登录；
- 403/404：使用非泄漏式通用页面；
- 前端不得根据错误差异推断其他患者是否存在。

## 14. 可访问性

必须满足：

- 语义化 `header`、`nav`、`main`、`section`、heading；
- Home/AI tab 有 active state；
- checklist 使用 button/checkbox 正确表达状态；
- 消息新增区域使用适度 `aria-live="polite"`；
- 不朗读每个打字动画；
- Send 按钮有 accessible name；
- keyboard 用户可以操作 quick replies 和 composer；
- focus 样式清晰；
- 颜色不是唯一状态表达；
- 文本与背景满足可读对比度；
- 动画尊重 `prefers-reduced-motion`。

## 15. 安全与隐私实现要求

### 15.1 身份

正式产品由登录会话确定 patient identity。不得通过 URL、localStorage 或可编辑 header 自报 patient id/role。

### 15.2 写入

患者消息是医疗相关敏感信息。发送前后必须遵守现有合同：

- source 先保存；
- LLM egress 前执行 PHI redaction；
- provider 只能接收 `RedactedContent`；
- placeholder mapping 不持久化；
- AI-derived Artifact 与 raw conversation 分开；
- 日志不记录 raw patient content；
- span anchoring 失败时 drop，不做 fuzzy fabrication。

### 15.3 页面切换

退出登录或身份变化时，必须清除：

- patient-view data；
- chat messages；
- draft；
- pending request state；
- cached session result。

Patient App 必须与 Clinician App 使用不同根组件，继续保持当前 role-level binary render 的安全原则。

## 16. 当前实现与目标设计对照

| 能力 | 当前 M6 | 目标 |
|---|---|---|
| 独立 Patient View | 已实现 | 保持 |
| patient-safe projection | 已实现并测试 | 保持 exact whitelist |
| 当前说明 | 已实现 | 升级视觉层级 |
| upcoming | 自由文本 | 清晰展示；结构化 appointment 待扩展 |
| 医生说明列表 | 已实现 | 改为更易浏览的列表 |
| AI 输入 | textarea + 单次发送 | 独立连续 chat 体验 |
| chat history | 只有 session 元数据 | 需要 conversation/message API |
| patient task completion | 未实现 | Task model 后再启用真实 checklist |
| 联系诊所 | 未实现 | 后续接入明确渠道，不能用假按钮上线 |
| responsive visual system | 非常基础 | 按本文档实施 |

## 17. 建议实施顺序

1. **Patient App Shell**：顶部导航、Home/AI 页面边界、移除窄容器限制；
2. **Home 信息层级**：CurrentCareSummary、Upcoming、Instructions；
3. **响应式布局**：先完成桌面和手机两个明确状态；
4. **AI Assistant UI**：先做真实 session 状态与错误处理，不伪装持久化能力；
5. **连续会话 API**：明确 message schema、session ownership、patient-safe context；
6. **结构化 appointment**：仅在后端有权威数据后启用完整卡片；
7. **Task completion**：Task model、权限和 audit 完成后启用 checklist；
8. **可访问性与视觉 QA**：键盘、窄屏、深浅主题、错误状态；
9. **安全回归**：patient-view whitelist、RBAC、session ingestion 测试全部通过。

## 18. 复刻验收清单

### Home

- [ ] 患者登录后只进入 Patient App；
- [ ] 顶部没有角色切换器；
- [ ] 页面第一重点是 What you need to know；
- [ ] 当前说明来自 patient-safe projection；
- [ ] Next appointment 不伪造结构化信息；
- [ ] Next Steps 在无 Task API 时不伪造完成状态；
- [ ] AI Assistant CTA 清晰但不压过当前说明；
- [ ] Doctor Instructions 是患者可读文案；
- [ ] 页面没有 clinician comments、AI scribed notes 或 provenance metadata；
- [ ] 宽屏充分利用约 1080px 内容区；
- [ ] 手机端无横向滚动。

### AI Assistant

- [ ] AI Assistant 是独立对话页面；
- [ ] 有 Back to Home；
- [ ] 有非急诊用途提示；
- [ ] 有清晰 opening prompt；
- [ ] quick replies 只填充输入，不自动提交；
- [ ] Enter/Shift+Enter 行为正确；
- [ ] 发送失败保留输入；
- [ ] 不声称消息已被医生阅读，除非有真实状态；
- [ ] AI 不展示内部临床内容；
- [ ] 写入继续经过 source-first、redaction-first pipeline。

### Regression

- [ ] `tests/test_patient_view.py` 的 exact-key 与 leak tests 继续通过；
- [ ] patient 不能访问 clinical endpoints；
- [ ] staff/clinician/admin 不能通过 Patient View endpoint 越权；
- [ ] patient session 只属于本人；
- [ ] role change remount 清除敏感状态；
- [ ] 未引入前端-only authorization。

## 19. 明确不做的事情

本患者端设计不包含：

- 完整 EHR Timeline；
- clinician/staff workspace；
- 患者自行编辑 clinician instructions；
- AI diagnosis；
- 自动 medication changes；
- 未经确认的 emergency triage workflow；
- internal provenance browser；
- 患者之间的社交功能；
- 为填充页面而添加的健康资讯流。

## 20. 后续 agent 的执行约束

后续 agent 实施本设计时必须：

1. 先阅读 `AGENTS.md`、本文档和现有 `PatientViewPage.tsx`；
2. 先运行 patient-view tests，确认基线；
3. 把视觉重构与后端 schema 扩展分开提交/验证；
4. 每次新增患者可见字段都增加 exact-key 和 sentinel leak tests；
5. 不因原型中出现 appointment、checklist 或 multi-turn chat，就假定后端能力已存在；
6. 不把 mock data 或客户端推断当成 authoritative clinical data；
7. 不复用 Clinician App shell；
8. 用真实 patient-safe API 状态验证桌面和手机布局；
9. 对 Home、AI Assistant、loading、empty、error 做视觉 QA；
10. 在安全与数据合同不完整时 fail closed，并在交付说明中明确缺口。
