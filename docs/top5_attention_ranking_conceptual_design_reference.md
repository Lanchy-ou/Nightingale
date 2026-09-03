# 医疗协作系统 Top 5 Attention Ranking：整体设计思路

## 1. 我们真正要解决的问题

这个功能不是普通的信息推荐系统，也不是简单地把数据库里的记录按照时间或者严重程度排序。

它真正解决的问题是：

> 在当前患者状态、当前时间和当前工作人员角色下，从大量异构医疗与工作流信息中识别出“这个人现在最应该注意的事项”，并按照优先级展示 Top 5。

因此，我们最终希望学习的不是：

\[
Score(\text{event})
\]

而更接近：

\[
\boxed{
Score(i,u,p,t)
}
\]

其中：

- \(i\)：当前待排序的 Attention Item；
- \(u\)：当前用户及其角色，例如 doctor / nurse / patient；
- \(p\)：患者当前整体上下文；
- \(t\)：当前时间和工作流状态。

也就是说：

> 同一个事项，在不同时间、不同患者状态、不同角色眼中，可以拥有完全不同的优先级。

---

# 2. 最底层：现实世界产生大量异构 Event

医疗系统的信息天然不是统一的。

例如：

- Patient reports headache
- Patient sends a message
- Doctor writes a note
- Doctor creates a CT task
- Task assigned to nurse
- Nurse acknowledges task
- CT performed
- CT result generated
- Lab result abnormal
- Doctor reviews result
- Medication changed
- Follow-up appointment created
- Appointment overdue

这些都可以统一称为：

\[
Event
\]

但它们只是“发生了什么”的事实记录，不应该直接全部拿去竞争 Top 5。

因此数据库底层应该尽可能完整地保留 event log。

一个基础事件至少可以拥有：

```text
event_id
event_type
timestamp
patient_id
actor
actor_role
related_entity
status
content
source
```

不同事件还可以拥有自己的特殊字段。

例如：

```text
SymptomReport
TaskCreated
TaskAssigned
TaskCompleted
LabResult
Message
Appointment
MedicationChange
ClinicalNote
...
```

这一层的目标不是排序，而是保留事实。

---

# 3. Event 之间不是孤立的，而是形成 Patient / Workflow Graph

这是整个设计中特别重要的一层。

例如：

```text
患者报告头痛加重
        ↓
医生进行评估
        ↓
医生创建 CT Task
        ↓
Task 指派给护士
        ↓
护士执行检查
        ↓
生成 CT Result
        ↓
医生查看结果
```

从业务角度看，这不是六件完全无关的事情。

它们属于同一条临床和工作流链：

```text
Headache Episode
      │
      ├── Symptom Report
      ├── Doctor Assessment
      ├── CT Task
      │      └── Assigned to Nurse
      ├── CT Result
      └── Follow-up Decision
```

因此系统内部应该能够表达：

```text
Event A related_to Issue X
Task B created_for Issue X
Task B assigned_to Nurse Y
Result C produced_by Task B
Result C waiting_for Doctor Z
```

可以把它理解成一个动态的：

> Clinical + Workflow Graph

或者更简单：

> Patient State Graph

这样，一个事件除了拥有自己的属性，还拥有上下文关系。

---

# 4. Issue / Episode 和 Attention Item 是两个不同概念

我们一开始讨论时把 Headache 当作排序对象，但后来发现这样过于粗糙。

因此需要区分：

## Issue / Episode

表示一个持续存在的较大问题。

例如：

```text
Headache Episode
Hypertension
Post-operative recovery
Medication issue
```

它负责把相关事件组织到一起。

但是 Top 5 不一定直接排列 Issue。

---

## Attention Item

真正参与 Top 5 排序的是：

\[
\boxed{AttentionItem}
\]

它的定义是：

> 当前状态下，有可能需要某个用户投入注意力、判断或行动的对象。

Attention Item 可以是：

```text
Clinical Issue
Task
Abnormal Result
Patient Message
Pending Decision
Follow-up
Alert
Missing Information
Escalation
...
```

所以：

> Top 5 排序对象不需要全部属于同一种业务实体，但在进入排序系统之前，它们必须被统一转换为 Attention Item。

这是整个系统的核心抽象。

---

# 5. 同一个 Episode 可以为不同角色产生不同 Attention Item

例如：

```text
患者头痛加重
↓
医生创建 CT
↓
CT Task 指派给 Nurse
```

从整体患者视角：

```text
Issue = Headache
```

但是护士现在真正应该看到的 Attention Item 是：

```text
CT examination task pending
```

医生此时可能根本不需要再次看到这个任务，因为：

```text
Doctor already reviewed
Task delegated
Waiting for nurse
```

因此：

```text
Nurse Top5:
CT Task waiting for completion
```

而 Doctor Top5 可能暂时不包含它。

但是，如果三天以后：

```text
CT Task overdue
Patient symptoms worsening
```

那么医生端可能重新出现：

```text
Delegated CT task overdue — escalation required
```

所以同一个底层对象的排名不是固定的。

这就是：

\[
Score(i,u,p,t)
\]

的意义。

---

# 6. Top 5 之前首先应该构造 Role-specific Candidate Set

不应该把系统中的所有事项全部交给模型评分。

首先应该判断：

\[
Candidate(i,u)
\]

也就是：

> 这个 Attention Item 对当前用户有没有资格成为候选事项？

例如数据库当前生成了 100 个 Attention Items。

其中：

```text
Doctor-related: 37
Nurse-related: 24
Patient-related: 18
```

那么 Nurse Ranking Model 根本没必要看到另外 76 个。

因此流程应该是：

```text
All Attention Items
        ↓
Role-specific Candidate Filtering
        ↓
Relevant Candidate Set
        ↓
Ranking
        ↓
Top 5
```

候选过滤可以依赖：

```text
assigned_to
responsible_role
requires_action_from_role
requires_review_from_role
waiting_for_role
created_by_role
escalation_to_role
visibility_policy
```

这样既减少噪声，也让后续排序任务简单很多。

---

# 7. Attention Item 如何转化成模型输入

Attention Item 最终需要被转换成一个统一的特征向量：

\[
x\in\mathbb{R}^{d}
\]

但是这个向量不应该简单理解为“把所有医疗字段全部堆进去”。

我们的设计应该是：

\[
\boxed{
x=
[
x_{shared},
x_{type},
x_{role},
x_{context},
x_{semantic}
]
}
\]

---

## 7.1 Shared Features

这些特征描述事项本身的通用状态，原则上所有角色和多数 Attention Item 都可以使用。

例如：

```text
urgency
severity
unresolved
requires_action
recent_change
worsening
time_since_created
time_since_last_update
time_to_deadline
overdue
parent_issue_priority
evidence_quality
staleness
```

这些特征回答：

> 这件事情客观上现在是什么状态？

---

## 7.2 Type-specific Features

因为 Task、Result、Message 本身还是不同的实体，所以允许它们拥有自己的专有特征。

Task：

```text
task_status
task_overdue
task_dependency
task_blocking
requires_acknowledgement
task_type
```

Result：

```text
result_abnormal
result_reviewed
change_from_baseline
result_criticality
```

Message：

```text
message_unread
repeat_contact
patient_reported_worsening
time_since_message
```

Clinical Issue：

```text
symptom_worsening
new_issue
recurrence
clinical_uncertainty
```

因此并不是所有 Attention Item 都拥有完全一样的原始特征。

统一发生在更高一级的 Attention Item interface 上。

---

# 8. Role-specific Features

同一个对象对不同角色意味着不同事情，因此需要额外加入：

\[
x_{role}
\]

例如：

```text
current_role
assigned_to_current_user
assigned_to_current_role
requires_action_from_me
requires_decision_from_me
waiting_for_my_role
created_by_me
delegated_by_me
requires_escalation_from_me
```

例如一个 CT Task：

```text
pending = 1
deadline_in_4h = 1
parent_issue_severity = 0.8
```

这些属于比较客观的 Shared / Task Features。

护士看到时：

```text
assigned_to_me = 1
requires_action_from_me = 1
```

因此可能：

\[
Score_{nurse}=0.92
\]

医生看到时：

```text
assigned_to_me = 0
requires_action_from_me = 0
waiting_for_other_role = 1
```

因此：

\[
Score_{doctor}=0.25
\]

后来 task overdue：

```text
delegated_task_overdue = 1
requires_escalation = 1
```

医生的分数又可能变成：

\[
Score_{doctor}=0.86
\]

因此：

> Attention Item 没有一个绝对固定的 Priority Score。

Priority 是 item、role、patient context、time 的联合函数。

---

# 9. Parent Context 必须进入子事件表示

即使我们排序的是一个非常小的 Task，也不能完全脱离它为什么产生。

例如系统不能只告诉模型：

```text
CT Task
Pending
4 hours remaining
```

而最好表示：

```text
CT Task
created because of worsening headache
assigned to current nurse
pending
deadline in 4 hours
parent issue severity = high
patient symptoms still unresolved
```

因此一个 Task 的向量实际上应该包含：

\[
x_{task}
=
[
x_{task\ itself},
x_{parent\ issue},
x_{workflow},
x_{role},
x_{time}
]
\]

这解决了“小事件和大事件之间的关系”。

Task 可以独立参与排名，但能够继承上游 clinical context。

---

# 10. Event 本身和 State 必须区分

另外一个核心思想是：

> Event 是历史事实，而 State 是当前状态。

例如：

```text
9/1 Patient reports headache
9/1 Doctor creates CT task
9/2 CT still pending
```

这些是三个 Event。

但是到了 9 月 2 日，系统需要计算：

```text
Headache:
worsening = 1
doctor_reviewed = 1
investigation_ordered = 1
investigation_pending = 1
unresolved = 1
```

因此：

\[
Events_{1:t}
\rightarrow
CurrentState_t
\]

排名算法应该高度依赖 Current State，而不仅仅依赖原始 Event。

一个 Event 发生以后，它的影响可能持续很久；另外，一个旧 Event 的含义也可能因为后续事件发生变化。

---

# 11. State Transition 是整个系统非常自然的表达

例如：

```text
Headache reported
```

状态：

```text
unreviewed
unresolved
```

医生查看：

```text
reviewed
unresolved
```

创建 CT：

```text
reviewed
investigation_ordered
investigation_pending
```

检查超时：

```text
investigation_overdue
unresolved
```

检查完成：

```text
result_available
result_unreviewed
```

医生看结果：

```text
result_reviewed
follow_up_decision_pending
```

最后：

```text
resolved
```

也就是说，很多所谓“小事件”实际上是：

\[
State_t
\xrightarrow{Event}
State_{t+1}
\]

这也是为什么医疗系统不适合简单做“数据库记录排序”。

它实际上是一个动态系统。

---

# 12. Missing Information 也必须显式表示

医疗数据中一个非常重要的问题是：

> Unknown 不等于 False。

例如：

```text
worsening = 0
```

可能表示：

> 已明确患者没有恶化。

也可能表示：

> 根本没有这方面的信息。

这两个含义完全不同。

因此需要类似：

```text
worsening = 0
worsening_known = 0
```

表示“不知道”。

而：

```text
worsening = 0
worsening_known = 1
```

才表示“明确没有 worsening”。

所以 feature engineering 时应该考虑：

```text
value
+
missing / known mask
```

数据缺失本身有时甚至可以成为一个 Attention Item：

```text
Critical information missing
```

---

# 13. 文本和非结构化信息如何进入系统

医疗系统里有大量：

```text
Doctor notes
Patient messages
Nursing notes
Free-text descriptions
```

这些不能全部靠人工字段覆盖。

因此 LLM / NLP 在系统里非常有价值，但职责应该明确。

LLM 可以负责：

### Candidate extraction

例如从：

```text
“My headache has become much worse over the past two days.”
```

抽取：

```text
problem = headache
trajectory = worsening
duration = 2 days
patient_reported = true
```

### Relationship extraction

识别：

```text
CT task
related_to
headache
```

### State extraction

识别：

```text
worsening = true
symptom_present = true
```

### Semantic representation

文本还可以生成 embedding：

\[
e=[0.12,-0.38,0.71,\dots]
\]

然后：

\[
x=[
x_{structured},
x_{semantic}
]
\]

但是第一版不应该采用：

```text
Entire medical record
↓
Embedding
↓
Black-box model
↓
Top5
```

因为可解释性和安全性太弱。

更合理的是：

```text
LLM/NLP
↓
提取结构化信息 + semantic embedding
↓
Attention Item / State
↓
Ranking Model
```

LLM 更适合作为：

> representation / extraction / explanation layer

而不是独自掌控最终临床优先级。

---

# 14. 第一版 Ranking 不需要直接做复杂 AI

我们目前形成的开发路线是：

## V0：Expert Rule-based Ranking

首先由团队定义一个透明的评分函数：

\[
Score=
w_1Urgency+
w_2Severity+
w_3Overdue+
w_4Actionability+
w_5Unresolved+
...
\]

例如：

```text
Doctor weights:
severity             0.30
urgency              0.25
requires_decision    0.25
overdue              0.10
...
```

Nurse：

```text
assigned_to_me       0.30
deadline             0.25
urgency              0.20
task_blocking        0.15
...
```

这些权重第一版完全可以人工制定。

此时系统已经能够运行，而且每一次排名都可以解释。

---

# 15. 不同角色最初可以有不同的 Fixed Rule

Doctor / Nurse 的：

```text
Candidate Filter
Feature Usage
Rule Weight
```

都可以不同。

但是不要建立两套完全互不相关的数据结构。

应该保持：

\[
SharedFeatureOntology
\]

也就是底层共同的 Feature Schema。

然后：

```text
Shared Features
+
Type-specific Features
+
Role-specific Features
```

这样未来模型才容易统一、扩展和训练。

---

# 16. V1：从人工权重变成可学习权重

第一版：

\[
Score=w^Tx
\]

其中：

\[
w
\]

是开发者和专家人工指定。

后面收集医生、护士反馈以后：

\[
w
\]

可以由数据自动学习。

例如原本：

```text
severity = 0.35
urgency = 0.25
change = 0.15
```

后来发现工作人员经常把变化快速的事项提升优先级。

模型可能学习成：

```text
severity = 0.27
urgency = 0.23
change = 0.29
```

于是产生：

\[
Score=w_{\theta}^{T}x
\]

这就是最朴素的 self-learning ranking。

第一批模型完全可以使用：

```text
Linear model
Logistic regression
Pairwise linear ranking
```

重点不是模型复杂度，而是闭环是否正确。

---

# 17. 更适合最终任务的学习方式是 Learning-to-Rank

真正的任务不是：

> A 的绝对重要性是不是 7.3？

而更接近：

> 对当前护士来说，A 和 B 哪一个应该先看到？

所以未来训练数据非常适合设计成：

\[
A>B
\]

例如：

```text
Context:
Nurse
Patient X
Time T

Attention A:
CT task pending

Attention B:
Routine follow-up call

Label:
A > B
```

于是模型学习：

\[
P(A>B|u,p,t)
\]

这就是 Learning-to-Rank。

之后可以考虑：

```text
LambdaMART
LightGBM Ranker
XGBoost Ranking
Neural Ranking
```

而不是一开始直接上 RL。

---

# 18. Role-specific Training：标签必须区分，但模型不一定必须完全分开

这里需要保持一个重要区别。

Doctor 数据：

> 对医生来说，A 和 B 哪个更重要？

Nurse 数据：

> 对护士来说，A 和 B 哪个更重要？

这两个 Label 应该分开理解。

但是模型架构有三种选择。

### 完全独立

```text
Doctor Model
Nurse Model
Patient Model
```

优点简单，缺点是数据被分散。

### 一个统一模型

把：

```text
role
```

作为特征：

\[
Score=f(x,role)
\]

共享全部训练数据。

### Shared Backbone + Role-specific Head

未来数据足够后：

```text
Attention Item
      ↓
Shared Representation
      ↓
 ┌────┼────┐
Doctor Nurse Patient
 Head   Head   Head
```

即：

\[
h=g(x_{shared})
\]

然后：

\[
Score_{doctor}=f_d(h,x_{doctor})
\]

\[
Score_{nurse}=f_n(h,x_{nurse})
\]

这是比较成熟的架构。

但是现在不需要决定最终采用哪一种。

当前应该：

> 数据结构统一、标签按角色保存、业务逻辑按角色区分，模型以后根据数据量决定合并还是拆分。

---

# 19. Self-learning 到底学习什么

类似抖音会收集：

```text
watch time
skip
rewatch
like
share
```

医疗 Top5 可以收集：

```text
item opened
evidence expanded
priority promoted
priority demoted
item dismissed
item resolved
task created
task reassigned
clinical action taken
time to action
```

但是这些反馈价值不同。

最可靠的是显式反馈：

```text
Promote priority
Demote priority
Resolved
Not relevant
Already handled
Wrong owner
Duplicate
Outdated
Incorrect information
Remind later
```

然后是工作流行为：

```text
created task
changed medication
requested test
contacted patient
escalated
reviewed result
```

最后才是：

```text
click
view
dwell time
```

因为医生看得久并不一定说明重要，也可能说明界面难懂。

所以不能简单复制抖音：

\[
Longer\ dwell\ time=better
\]

医疗场景下需要多种反馈联合判断。

---

# 20. 必须记录 Impression，而不只是 Click

以后训练 ranking model 时，不能只保存：

```text
Doctor clicked item A
```

因为 A 可能只是因为排第一才被点击。

应该保存：

```text
candidate set
features
model score
displayed position
items not displayed
current role
patient context
model version
subsequent action
feedback
final resolution
```

也就是说：

> 每一次 Top5 展示本身都应该成为一条训练日志。

否则以后会严重受到 position bias 的影响。

---

# 21. Self-learning 应该是离线、可控制的，而不是在线乱更新

生产系统不应该：

```text
Doctor click
↓
立即修改模型参数
```

而应该：

```text
Production Model v1
        ↓
Collect Feedback
        ↓
Offline Dataset
        ↓
Train Candidate Model v2
        ↓
Offline Evaluation
        ↓
Shadow Mode
        ↓
Human / Clinical Review
        ↓
Controlled Deployment
```

模型版本必须：

```text
versioned
auditable
rollback-able
```

因此所谓 self-learning 更准确的说法应该是：

> Controlled continuous learning loop

而不是一个模型自己在线改变规则。

---

# 22. 临床安全规则和学习模型必须分层

这是最重要的安全边界之一。

整体结构应该是：

```text
Clinical Safety Rules
        ↓
Candidate / Priority Tier
        ↓
Learned Ranking
        ↓
Top 5
```

例如某些条件被定义为：

```text
P0 Critical
```

那么机器学习模型不能因为：

```text
Doctors usually don't click this
```

就自动降低它。

所以：

> 模型可以学习同一个安全层级内怎样排序，但不能随意改变安全底线。

---

# 23. Top 5 不应该成为硬性的“最多只能显示五件事”

如果患者当前存在：

```text
6 Critical Attention Items
```

不能为了 UI 的 Top5 而隐藏第六个。

更合理的逻辑是：

```text
Critical Items
→ 全部显示

Top 5 Attention Items
→ 从剩余候选中选择最值得关注的五项
```

反过来，如果真正有意义的只有三个：

```text
3 meaningful items
```

也不要为了凑五个而加入垃圾提醒。

目标是：

> Attention management，而不是数字 5 本身。

---

# 24. Top 5 还需要避免重复

例如：

```text
Headache worsening
CT ordered
CT pending
CT overdue
Patient asks about CT
```

如果它们全部进入 Top5，医生实际上看到五遍同一个问题。

所以除了单项分数：

\[
Score_i
\]

还需要考虑：

\[
Redundancy(i,j)
\]

最终选择可以理解成：

\[
\max_{S,|S|\le5}
\sum_{i\in S} Score_i
-
\lambda
\sum_{i,j\in S}Redundancy(i,j)
\]

也就是说：

> Top5 应该尽可能覆盖五个真正不同的注意力需求，而不是五条重复记录。

但 Critical Item 不应该因为 diversity constraint 被隐藏。

---

# 25. Top 5 Card 最终需要能够解释为什么出现

每个 Attention Item 最好可以回答：

```text
What happened?
Why does it matter now?
What is its current status?
What evidence supports it?
What is missing / uncertain?
Who should act?
What is the next action?
```

例如护士看到的：

```text
CT examination pending

Why now:
Assigned to you
Due in 4 hours
Patient reports worsening headache

Status:
Not acknowledged

Context:
Requested by Dr. X because of worsening symptoms
```

这样用户看到的不只是：

```text
Priority Score = 8.7
```

而是一个真正可以理解和行动的 Attention Item。

---

# 26. Feature Engineering 是当前比模型更重要的工作

因此我们目前真正需要设计好的并不是：

> 用 Logistic Regression 还是 XGBoost？

而是：

\[
\boxed{
Attention\ Item\ Representation
}
\]

也就是定义：

```text
什么叫 Event？
什么叫 Issue？
什么叫 Attention Item？
它们之间如何关联？
State 如何更新？
什么叫 Candidate？
有哪些 Shared Features？
有哪些 Type-specific Features？
有哪些 Role-specific Features？
Missing information 如何表达？
Feedback 如何记录？
```

这些定义稳定以后：

```text
Linear Model
XGBoost
Learning-to-Rank
Neural Model
```

都只是后续可以替换的 ranking engine。

反过来，如果 representation 不稳定，再高级的模型也没有意义。

---

# 27. 整个系统最终可以抽象成这一条链

\[
\boxed{
Raw\ Heterogeneous\ Data
}
\]

↓

\[
\boxed{
Events
}
\]

记录现实中发生的所有事实。

↓

\[
\boxed{
Clinical/Workflow\ Graph
}
\]

建立 Event、Issue、Task、Result、User 等实体之间的关系。

↓

\[
\boxed{
Current\ State
}
\]

根据事件历史计算当前状态。

↓

\[
\boxed{
Attention\ Item\ Generation
}
\]

从当前状态产生真正值得参与注意力管理的候选对象。

↓

\[
\boxed{
Role-specific\ Candidate\ Filtering
}
\]

筛选出与当前医生、护士或者患者相关的事项。

↓

\[
\boxed{
Contextual\ Feature\ Vector
}
\]

构造：

\[
x=
[x_{shared},x_{type},x_{role},x_{context},x_{semantic}]
\]

↓

\[
\boxed{
Safety\ Rules
}
\]

保证不能遗漏不可被学习算法降级的关键事项。

↓

\[
\boxed{
Ranking\ Model
}
\]

从固定权重逐渐演化到 learned ranking。

↓

\[
\boxed{
Top5\ Selection
}
\]

同时考虑：

```text
priority
diversity
redundancy
critical override
```

↓

\[
\boxed{
Role-specific\ Top5
}
\]

↓

\[
\boxed{
User\ Feedback+Workflow\ Outcome
}
\]

↓

\[
\boxed{
Training\ Dataset
}
\]

↓

\[
\boxed{
Offline\ Learning+Validation
}
\]

↓

回到新的 Ranking Model。

---

# 28. 推荐的实际演化路线

### V0 — Rule-based Prototype

当前就可以实现：

```text
Unified AttentionItem Schema
Shared Feature Schema
Role-specific Candidate Rules
Role-specific Fixed Weights
Critical Safety Rules
Top5
Feedback Logging
```

这一版最重要的是“整个数据链能够运行”。

---

### V1 — Learnable Linear Ranking

有少量专家和用户数据以后：

```text
same feature schema
+
doctor/nurse feedback
↓
learn weights
```

从：

\[
Score=w_{manual}^{T}x
\]

变成：

\[
Score=w_{learned}^{T}x
\]

---

### V2 — Non-linear Ranking

数据增加以后：

```text
LightGBM
XGBoost
```

开始学习：

```text
urgency × overdue
severity × worsening
role × task_type
```

这样的非线性交互。

---

### V3 — Learning-to-Rank

训练：

\[
P(A>B|context)
\]

让模型直接学习不同 Attention Items 之间的相对顺序。

---

### V4 — Contextual / Multi-role Ranking

进一步引入：

```text
patient context
role
specialty
workflow stage
time
historical state
```

并可能发展成：

```text
shared backbone
+
role-specific heads
```

---

# 29. 最终设计原则

整个方案可以浓缩成几个原则。

第一：

> **不要直接给杂乱的医疗记录排序，而要先建立统一的 Attention Item abstraction。**

第二：

> **Event 是事实，State 是当前状态，Attention Item 是当前值得某个角色关注的对象。三者必须分开。**

第三：

> **大的 Clinical Issue 和小的 Task / Message / Result 可以同时存在。小事件可以继承大 Issue 的上下文，但仍然可以独立参与排序。**

第四：

> **Feature 不需要完全统一，而应该由 Shared Features + Type-specific Features + Role-specific Features 构成。**

第五：

> **不同角色应该拥有不同 Candidate Set、不同 ranking objective 和不同反馈标签，但底层 representation 应尽可能共享。**

第六：

> **Role-specific training 不等于必须训练完全独立的模型。第一版可以分权重，未来根据数据决定采用独立模型还是 shared model。**

第七：

> **模型不是一开始就需要复杂。第一版固定规则本身就是整个未来学习系统的 bootstrap。**

第八：

> **所谓 self-learning，本质上是逐渐把人工决定的 ranking policy 转变成从医生、护士实际判断和工作流结果中学习出来的 policy。**

第九：

> **Clinical safety constraints 不应该由模型自行学习或删除。模型学习的是安全边界内部的注意力分配。**

第十：

> **最终真正有价值的资产不只是 ranking model，而是整个从 Event → State → Attention Item → Feature → Feedback → Training Data 的数据闭环。**

因此，我们最终构建的不是简单的：

\[
Data\rightarrow AI\rightarrow Top5
\]

而是：

\[
\boxed{
Heterogeneous\ Events
\rightarrow
Dynamic\ Patient/Workflow\ State
\rightarrow
Role-specific\ Attention\ Items
\rightarrow
Contextual\ Representation
\rightarrow
Safety-constrained\ Ranking
\rightarrow
Top5
\rightarrow
Human\ Feedback
\rightarrow
Controlled\ Learning
}
\]

这就是目前这套 Top5 系统比较完整的 conceptual architecture。