# D4 任务卡 - Evidence-Bound Clinician Copilot

> 状态：**BLOCKED BY D2 + D3**
>
> 对应总计划：`docs/phase_d_product_completion_plan.md`
>
> 目标是 patient-scoped clinical record assistant，不是通用聊天机器人或诊断系统。

---

## 1. 目标

在 clinician workspace 右栏提供四类有证据的帮助：

```text
What changed?
What matters now?
Find evidence
Draft an authorized next action
```

Copilot 必须帮助医生更快理解记录和准备草稿，同时保持 clinician authority、RBAC、provenance 和显式确认。

---

## 2. UI 合同

右栏改为：

```text
Copilot | Source | Comments | History
```

History 内含 Versions 和 Audit；已有 Source/Comments/Versions/Audit 能力不得丢失。

Copilot response 结构：

```text
Claims[]
  - text
  - status: supported|inference|unknown
  - evidence_ids[]
Evidence cards
Unknowns / limitations
Suggested draft actions
```

要求：

- 常用问题提供快捷按钮，仍允许受限自由文本；
- Evidence card 显示 Event、Artifact、author role、event time、exact span，并可打开 Source；
- inference 必须标记，不得伪装 source fact；
- 无证据回答 `not found/unknown`；
- draft note/task/instruction 先进入 Preview，用户显式确认后才调用现有写端点；
- patient switch、logout、session expiry 清空问题、回答、evidence 和 drafts；
- patient view 不加载或暴露 clinical Copilot。

---

## 3. Backend 范围

最小端点：

```text
POST /api/patients/{patient_id}/copilot/query
```

可选的 draft 不单独持久化；确认时复用现有 note/task/instruction APIs。

Query pipeline：

```text
session identity + authorize
-> build bounded patient context
-> redact before provider
-> provider structured answer
-> server validates evidence ids/spans
-> drop unsupported claims
-> return answer + evidence + limitations + draft proposal
```

要求：

- 继续通过 `LLMClient` 唯一出口；
- context 只含当前授权 patient，且按 query 类型做 bounded retrieval；
- 不把全历史无差别发送给 LLM；
- Task/Glance/Artifact/Event 读取使用显式 read model；
- provider 不能自行指定可写 endpoint、role、patient_id、artifact author 或 Task completion；
- 服务端重新解析所有 evidence pointer；不存在、跨 patient、跨 clinic、不可见、span 不匹配的 evidence 全部拒绝；
- clinical factual claim 若无有效 evidence，删除或转为 unknown；
- provider failure 明确返回 unavailable/structured fallback，不生成无来源回答；
- query/audit 只记 metadata（actor、patient、query category、provider、latency、success），默认不记录完整问题/回答；
- 第一版仅 clinician 可调用；patient、staff、admin 均不得调用 clinical Copilot。后续扩大角色必须另开权限决策，不能从 clinician 权限推断；
- 服务端对每个 `Claims[]` 元素独立验证 evidence；不能用一条合法 citation 为整个自由文本回答背书；前端按已验证 claims 组合显示。

---

## 4. 第一版 Query categories

### What changed

- 比较最近明确 Event 与前一相关 Event；
- 区分 event time 与 record update time；
- 只陈述有 source 的变化。

### What matters now

- 读取 Glance、open/in_progress/reported_done Task、clinician-confirmed facts；
- 不重新用 LLM 排名整个历史；
- 解释 why now 并引用来源。

### Find evidence

- 查找用户指定症状、药物、任务或陈述；
- 返回 exact source，不存在时明确 not found。

### Draft action

- 仅生成 `clinician_note`、Task 或 `patient_instruction` 的 draft schema；
- preview 显示将写入的类型、Event、author、patient visibility；
- 保存仍走原有 RBAC/version/audit API。

---

## 5. 安全与 prompt injection

- transcript/comment/artifact 中的指令视为患者记录内容，不是系统指令；
- provider 输出不能触发 tool/action；
- evidence ids 必须来自 server-provided candidate set；
- 不允许 URL/file/network retrieval；
- 不允许诊断、处方或改变 clinician-authored fact；
- draft 明确标记 AI-generated until accepted；确认后 human-authored Artifact 的 author 必须是真实 actor，Audit 记录 draft origin；
- 任何 conflict 与现有 clinician note 必须显示 review flag，不静默融合。

---

## 6. 必须测试与 Eval

建议新增：

```text
tests/test_copilot_rbac_scope.py
tests/test_copilot_evidence.py
tests/test_copilot_draft_authority.py
tests/test_copilot_state_isolation.py
backend/evals/copilot/
```

覆盖：

- clinician allow + patient/staff/admin deny 的权限矩阵；
- cross-clinic/not-own-patient；
- provider fabricated event/artifact/span 被拒绝；
- factual claims 100% 有可解析 evidence；
- unverified claim 转 unknown/drop；
- prompt injection 不改变 schema/权限/动作；
- draft 不自动持久化；
- confirmed note/task/instruction 复用既有权限、author、audit；
- provider failure 不产生无来源答案；
- read context bounded 且不含其他 patient sentinel；
- patient/role switch 清空前端状态；
- read path latency 单独报告，不能与 Glance P95 混报。

冻结最小 eval questions，覆盖上述四类 query，并分 mock/deterministic/live provider 报告。

---

## 7. Exit Gate - D4 Complete

1. 四类 query 在 canonical journey 上可用；
2. 所有临床事实 evidence resolver 100% 成功，否则不返回为事实；
3. Copilot 不直接修改记录、不完成 Task、不改变 author；
4. prompt injection/cross-patient fabricated evidence tests 全绿；
5. patient switch/logout 无状态泄漏；
6. Source/Comments/History 原能力零回归；
7. eval、全量 tests、frontend build 全绿；
8. UI 明确区分 source fact、inference、unknown 和 draft。

---

## 8. 非目标与停止条件

非目标：开放式诊断、自动处方、agentic tool execution、长期跨患者记忆、互联网搜索、自动完成任务、患者聊天机器人重构、全历史大型 RAG。

停止条件：

- 回答无法逐事实追溯 -> 停止；
- 为实现 draft 绕过现有 note/task API -> 停止；
- Copilot 需要读取其他 clinic/patient 才能工作 -> 停止；
- 把 provider response 当权限或 provenance 权威 -> 停止。
