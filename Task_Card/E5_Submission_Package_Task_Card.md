# E5 Task Card — Final Submission Package

> 状态：**PLANNED — IMPLEMENTATION NOT STARTED**
>
> 对应总计划：`docs/phase_e_capability_enhancement_plan.md`
>
> 依赖：E1–E4 的最终提交范围、状态与观察证据已经冻结。

---

## 1. 目标

把 Nightingale 的实际实现收口为完整、简洁、可复现、无夸大声明的候选提交包：

```text
working repository
+ automated tests
+ README
+ 2-3 page Technical Brief
+ ATTRIBUTION.txt
+ Demo Video
+ final evidence manifest
```

E5 不新增业务功能，不在提交文档中替未完成实现“补故事”。

---

## 2. 开工 Decision Gates

### DG1 — Submission scope freeze

逐项标记：

```text
IMPLEMENTED_AND_VERIFIED
IMPLEMENTED_WITH_LIMITS
DESIGN_ONLY
NOT_INCLUDED
```

特别冻结：

- E1 Nurse/Admin 的实际完成范围；
- E2 Self-Learning 是否达到 future similar candidate；
- E3 Data Decay 是否只有 policy、是否含 shadow archive；
- E4 是 interface/mock、local ASR 还是 live provider；
- DeepSeek/live provider 当前是否实测；
- 哪些结果来自 synthetic fixture、mock、fallback、local deployment。

### DG2 — Candidate identity

确认提交者姓名、repo/zip link、Video link 与邮件字段。不得保留 `<Your Name>`、placeholder、Group XX 或测试地址。

### DG3 — Final claim vocabulary

允许：

- synthetic-data product Demo；
- server-enforced RBAC；
- locally verified TLS/SQLCipher；
- observed local P95；
- mock/fallback/live 分层结果；
- controlled synthetic Self-Learning/Data Decay evidence。

禁止：

- production medical system；
- production capacity；
- real clinician usability validated；
- real patient data；
- live AI/ASR（无当前证据）；
- storage savings（shadow copy 仍保留）；
- learned clinical correctness（仅 synthetic interaction test）。

---

## 3. Repository Gate

最终仓库必须：

- working tree clean；
- clear, scoped commit history；
- 无 secret、token、key、`.env.local`、private DB、recording 或 unlicensed dataset；
- `.gitignore` 覆盖 runtime/private artifacts；
- README 命令从 clean environment 可复现；
- Task Card/AGENTS/README 状态与实现一致；
- 没有 stale file reference、missing test 或不存在的 Bonus claim；
- `git diff --check`、secret scan、dependency/license check 通过。

任何 merge/rebase/push/tag/remote upload 需要 owner 明确授权；E5 文档完成不自动授权发送或发布。

---

## 4. Automated Evidence Manifest

新增 dated final evidence，例如：

```text
docs/final_submission_evidence_2026-08-28.md
```

记录实际命令、环境和结果：

- commit hash / working tree；
- backend test count；
- required micro-tests；
- E1 role tests；
- E2 Self-Learning bonus test；
- E3 Data Decay/archive tests；
- E4 Voice tests（若纳入）；
- D3 corpus/runtime results 与 hashes；
- D4 Copilot frozen eval；
- frontend production build；
- Glance warm-path P50/P95；
- D5 SQLCipher/TLS/security/integration evidence；
- secret/dependency/license scan；
- Demo fixture IDs 与 synthetic status。

命令失败、NOT_RUN、mock、fallback 与 live 必须原样保留，不选择性隐藏。

---

## 5. README Final Pass

PDF 所需内容必须容易找到：

- project goal 与 three views；
- setup/install/run；
- demo accounts 与 synthetic warning；
- automated tests；
- architecture；
- where redaction happens；
- how server-side RBAC works；
- AI provider/fallback behavior；
- provenance chain；
- performance measurement；
- E2/E3/E4 actual status 与限制；
- D5 secure Demo reproduction；
- known non-goals/trade-offs。

README 不代替 2–3 page Technical Brief，不应继续无限扩张。长实现细节可链接到 docs/task cards。

---

## 6. 2–3 Page Technical Brief

最终 PDF 必须严格 2–3 页，建议 3 页：

### Page 1 — Product and Architecture

- clinical problem；
- Glance / Timeline / Patient View；
- architecture diagram；
- Brief Entry -> Event + Artifacts mapping；
- Patient -> Event -> Artifact -> Span；
- Nurse/Clinician/Admin authority boundary。

### Page 2 — Collaboration, AI, Provenance, Security

- AI-scribed notes 与 human notes 分离；
- Highlight -> Summary -> Raw Source -> Exact Span；
- Comments/Versions/Revert/Audit；
- Task lifecycle；
- PHI-before-LLM；
- server-side RBAC；
- TLS/encryption at rest；
- warm-path P95 方法与限制。

### Page 3 — Capability Enhancement and Trade-offs

- Self-Learning feedback -> future similar priority；
- `base + adaptive + decay = final`；
- hard protection/caps/clinic isolation；
- Hot/Warm/Cold policy；
- archive recovery/provenance；
- Voice Adapter 实际状态；
- assumptions、first principles、scope decisions、non-production limits。

Brief 中每个数字必须链接到 evidence 文件/测试，不使用 expected metric 或占位符。

---

## 7. Demo Video

建议 6–9 分钟，按真实用户旅程而非功能清单：

```text
0:00  Login and clinic identity
0:30  Glance in under ten seconds
1:15  Exact source and provenance chain
2:00  Timeline and longitudinal context
2:45  Event detail: Transcript / AI Summary / human Note
3:30  Comment / mention / version diff / revert / audit
4:30  Nurse/Staff role and Nurse Consult
5:15  Patient View anti-leak and Task journey
6:00  Self-Learning: feedback -> future similar candidate
6:45  Data Decay: Hot/Warm/Cold -> cold exact source
7:30  Voice Adapter (only if actually implemented)
8:15  Security/performance/trade-off limits
```

录制要求：

- 使用真实 Session，不用 Role selector/demo header；
- 使用 synthetic patient/audio/transcript；
- 不显示 API key、env、token、private path 或 raw secret；
- 新输入产生新的 Event，不写固定 seed Event；
- AI/ASR 显示 generation method 与 fallback；
- Self-Learning 展示 future candidate，不用 current pin 冒充；
- Data Decay 展示 protected exception 与 exact provenance；
- 未实现内容不通过 Figma/文案冒充 runtime；
- 画面、字体、光标、音量、停顿和讲解清晰。

---

## 8. ATTRIBUTION and Data Licenses

最终 `ATTRIBUTION.txt` 必须包括：

- backend/frontend libraries；
- LLM/ASR providers/models；
- Caddy/SQLCipher；
- audio codec/recording library；
- external synthetic datasets；
- dataset owner、official URL、license；
- 是否只用于 evaluation；
- 未打包的 runtime provider 也需说明。

许可证不清或 source 不明的数据不得进入最终 repo/Video/Brief。

---

## 9. Final Verification Matrix

必须运行并记录：

```text
backend full pytest
required micro-tests by name
E1-E4 targeted tests
D3 corpus validation/runtime evaluation
D4 Copilot frozen evaluation
frontend production build
frontend interaction tests
Glance performance measurement
D5 security/integration subset
SQLCipher init/backup/restore
Caddy validate / secure Demo verification
secret scan
dependency check
git diff --check
```

另做人工只读检查：

- Technical Brief PDF render，无 overflow/裁切/乱码；
- Demo Video 从头到尾播放；
- 所有文档/视频链接可访问；
- zip/repo clone 后命令路径正确；
- PDF 页数 2–3；
- 邮件 To/CC/Subject/附件清单正确。

---

## 10. Submission Bundle

最终清单：

```text
Repository link or verified zip
Technical Brief PDF
Demo Video link/file
README
ATTRIBUTION.txt
Automated tests
Final evidence record
```

正式邮件：

```text
Due: Friday, 28 August 2026, 17:30 SGT/MYT
To: irakumar@ntngale.com
CC: frank.ng@ntu.edu.sg, carrene.teo@ntu.edu.sg
Subject: Nightingale 72HR Build -- <Your Name>
```

E5 可以准备邮件草稿，但不得在未获 owner 明确授权时发送、上传、共享或改变 repository visibility。

---

## 11. Exit Gate — Submission Ready

1. 仓库 clean、可运行、commit history 清晰；
2. required tests 与 E1–E4 纳入范围的 gates 全绿；
3. README setup/redaction/RBAC/limits 与实际实现一致；
4. Technical Brief 为 2–3 页，render QA 通过；
5. Demo Video 清楚完成选定 scenarios 并从头播放验证；
6. ATTRIBUTION 与 data/provider licenses 完整；
7. evidence record 没有伪造、合并或隐藏 NOT_RUN/failure；
8. repo/zip/links 从提交者视角可访问；
9. email fields、subject、附件/link 清单正确；
10. 明确保留 synthetic Demo、非生产医疗、非真人 usability 限制；
11. owner 完成最终人工确认；
12. 只有在 owner 明确授权后才执行发送/上传/公开。

---

## 12. 非目标与停止条件

非目标：E5 新增功能、最后一分钟重构、隐藏失败、制作虚假 provider/usability/storage 证据、未经授权发送邮件或公开仓库。

停止条件：

- Brief/README/Video 声称实现但测试/runtime 不存在 -> 停止并修正；
- PDF 超过 3 页或关键图不可读 -> 停止提交并重排；
- Demo 只展示 seed AI 却声称 live generation -> 停止；
- repo/zip 包含 secret、private DB/audio 或无许可证数据 -> 停止并清理；
- 最终测试与录制使用的 commit 不一致 -> 停止并重新验证；
- owner 尚未授权 external send/upload -> 不执行外部动作。
