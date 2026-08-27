# D5 任务卡 - Deployment Security, Cross-Role Integration and Usability Gate

> 状态：**D5_AUTOMATED_SECURITY_COMPLETE（2026-08-27）；D5_USABILITY_GATE_BLOCKED_EXTERNAL_OBSERVERS；D5 / Phase D NOT COMPLETE**
>
> 对应总计划：`docs/phase_d_product_completion_plan.md`
>
> 本卡不新增产品功能；它把已有功能部署、验证并收口为可使用的产品级 Demo。

---

## 1. 目标

把 TLS、encryption at rest、session security、三角色 E2E 和可用性从文档声明变成可复现证据，并清除实现与 README 不一致。

---

## 2. 开工 Decision Gates

### DG1 - Deployment database

在以下方案中选择并记录理由：

- PostgreSQL deployment + SQLite unit tests（推荐）；
- encrypted SQLite/SQLCipher deployment（仅单机 Demo）；
- 其他方案需说明并发、backup、encryption 和迁移成本。

不得把普通 SQLite 文件称为 encrypted at rest。

### DG2 - At-rest scope

明确记录：

- database/volume encryption；
- backup encryption；
- 密钥由谁管理、放在哪里、如何轮换；
- 是否额外加密 IC/phone 等字段；
- 哪些内容仍会以明文存在于进程内存；
- 搜索、provenance、migration 的影响。

不要同时仓促实现多套重叠加密。

### DG3 - TLS termination

选择 Caddy/Cloudflare/hosting platform/managed load balancer 之一，并明确 TLS 在哪里终止、内部连接是否可信、HTTP 如何跳转 HTTPS。

---

## 3. Security 实施范围

### TLS / transport

- public/demo URL 只通过 HTTPS；
- HTTP -> HTTPS redirect；
- session cookie `Secure + HttpOnly + SameSite`；
- 合理的 HSTS（确认不会破坏本地开发后启用）；
- API 不在公网暴露独立不受保护的 HTTP 入口；
- TLS certificate/issuer/expiry 可验证。

### At rest

- 当前数据库存储有真实加密证据；
- backup/export 同样加密或明确禁用；
- key/credential 在 secret manager/env，不入 repo/DB/log；
- raw database/backup inspection 证明保护层存在；
- restore 测试证明授权应用可以恢复和读取；
- 如果实施字段加密，使用标准 AEAD、随机 nonce、版本化 envelope；不得自创算法。

### Web/session hardening

- CSRF strategy 与 cookie auth 一致；
- CORS 只允许部署 frontend origin；
- login/register/invite 基础 rate limit；
- security headers；
- request size limits 覆盖 transcript；
- error body 不含 stack、SQL、secret、token、raw provider payload；
- sanitized logs 和 AuditLog 抽查；
- dependency/license 更新到 ATTRIBUTION。

---

## 4. 三条 E2E Journey

### Clinician

```text
Invite -> Register -> Login -> Patient Glance
-> Transcript Preview -> Confirm Consult
-> AI Summary -> Exact Source
-> Clinician Note -> Task -> Patient Instruction -> Logout
```

### Patient

```text
Invite -> Register -> Login -> Today/Care Plan
-> Start Task -> Report Done
-> Submit Check-in -> View Visit Summary -> Logout
```

### Staff

```text
Login -> Open patient
-> Review reported_done Task
-> Verify completed -> Comment/@clinician
-> Confirm Glance update -> Logout
```

每条 journey 使用独立 session；禁止通过 demo Role selector 完成。

---

## 5. Usability Gate

使用 5-8 位未参与开发的观察者，synthetic data only。记录任务完成而非主观好评。

核心任务：

- clinician 10 秒内指出当前最重要问题与下一行动；
- clinician 找到一条 AI 事实的 exact source；
- clinician 完成 transcript import 并识别一个 ambiguous segment；
- patient 说明自己下一步需要做什么；
- patient 报告 Task 完成且理解“等待诊所确认”；
- staff 找到并确认 reported_done Task；
- 三角色都能正确退出并无法返回受保护内容。

记录：成功/失败、完成时间、误解点、阻塞点。测试中出现的产品问题按 severity 修复；不能只修改演示话术掩盖。

---

## 6. 自动化验证

建议新增：

```text
tests/integration/test_auth_care_journey.py
tests/integration/test_patient_staff_task_journey.py
tests/security/test_session_cookie_policy.py
tests/security/test_log_sanitization.py
tests/security/test_cross_patient_sentinels.py
```

以及部署检查脚本/文档，覆盖：

- HTTPS/redirect/certificate；
- secure cookie；
- CORS/CSRF；
- encrypted storage/backup evidence；
- database restore；
- no secret committed；
- production config 禁用 demo auth；
- PostgreSQL integration migration（若采用）；
- SQLite unit tests 与全部历史 tests；
- frontend production build；
- D3/D4 eval 重跑与 frozen hash 校验。

---

## 7. Exit Gate - Phase D Product Demo Complete

1. D1-D4 Exit Gate 全部通过；
2. 部署只提供 HTTPS，session cookie/security headers 符合合同；
3. database 与 backup 的 at-rest protection 有可复现证据和 restore 结果；
4. 三角色 E2E 不依赖 Role selector；
5. patient anti-leak、cross-clinic、cross-patient sentinel 全绿；
6. transcript holdout 与 Copilot evidence eval 结果可复现；
7. usability tasks 完成，阻塞级问题清零；
8. 全量 tests、integration tests、security checks、frontend build 全绿；
9. README/AGENTS/ATTRIBUTION 与实际实现一致；
10. 明确声明这是 synthetic-data product Demo，不是 production medical system。

---

## 8. 非目标与停止条件

非目标：新增业务功能、Voice、self-learning、data decay、真实患者试用、production capacity claim、外部诊断工具。

停止条件：

- 只有 README 声明，没有 TLS/at-rest 实际证据 -> 不通过；
- 为通过 E2E 使用 demo headers/Role selector -> 不通过；
- 可用性失败只通过培训用户或修改演示脚本规避 -> 不通过；
- production config 暴露 secret、debug stack 或未保护 API -> 停止发布并修复。

---

## 9. Implementation Evidence（2026-08-27，未宣称 Complete）

- D1-D4 已在 clean `main` 基线独立重验：324 backend tests、D3 corpus/runtime、D4 frozen eval、pip check 与 frontend production build 通过。
- DG1 选择任务卡允许的 SQLCipher 单机 Demo；普通 SQLite 仅保留为 unit-test/development path。production startup 对 plain SQLite fail closed。
- DG2 落地整库 SQLCipher + 独立 backup key + restore 时换 DB key；database/backup/restore 三把 key 必须 32+ 字符且两两不同，production/startup 与 backup/restore scripts 对缺钥、短钥、同钥、错钥 fail closed。实际原始文件检查均为 `plaintext_header=false` / `plain_reader_blocked=true`，SQLCipher 4.12.0，database/backup/restore 均 13 tables，restore 可读回 2 patients / 14 artifacts 对应 schema/data。
- DG3 选择 Caddy 2.11.4：FastAPI 仅绑定 `127.0.0.1:8000`；Caddy 在 8080/8443 提供 HTTP→HTTPS、SPA 与 `/api/*` reverse proxy。实际 TLS chain 验证 `OK`（TLSv1.3 / TLS_AES_128_GCM_SHA256），certificate issuer/expiry/fingerprint 已读取。
- `backend/app/security.py` 已实现 strict Origin CSRF、exact-origin CORS、login/register/invite 基础限流、actual-body size limit、HSTS/CSP/security headers、generic 500 与 metadata-only error log；cookie create/clear 都锁定 `Secure + HttpOnly + SameSite=Lax`。
- integration/security tests 使用真实 session 且不使用 `X-User-Id/X-Role`。Clinician journey 已合并为同一个新邀请账号、同一个 Cookie 完成 Invite → Register → Login → Glance → Transcript → AI Summary → Exact Source → Note → Task → Patient Instruction → Logout；另有 patient/staff journey、patient/cross-clinic sentinel、log sanitization、cookie/CORS/CSRF/rate/body 与 encrypted backup/restore tests。
- `backend/scripts/check_no_secrets.py`、SQLCipher init/backup/restore scripts 与 `verify_secure_demo.py` 已实际运行通过；部署决策和命令见 `docs/d5_deployment_security_decisions.md`，观察者协议见 `docs/d5_usability_protocol.md`。
- invite preview 已改为 `POST /api/auth/invites/preview`，raw token 只在 JSON body；旧 URL-token endpoint 已删除。后端离线 Caddy 故障测试用虚构 token 验证 502 response、Caddy stdout/stderr 与未运行应用的 log sink 均无 token。Uvicorn `--no-access-log` 与 Caddy 不启用 production access log 继续作为 defense in depth。
- D5 修正后最终回归：backend **342 passed**；security/integration **17 passed**；D3 corpus/runtime、D4 frozen eval、pip check、secret scan、Caddy validate、frontend production build 与 `git diff --check` 均通过；实际 listener 全部为 loopback（Caddy 127.0.0.1:8080/8443，FastAPI 127.0.0.1:8000）。
- Caddy 设置 `skip_install_trust`；本轮没有安装或绕过本地 CA。TLS verifier 通过显式 `--ca-file` 验证链路。
- **D5_USABILITY_GATE_BLOCKED_EXTERNAL_OBSERVERS**：当前无法获得 5-8 位未参与开发观察者；`docs/d5_usability_protocol.md` 保持空白，无模拟参与者或虚假结果。因此最多声明 `D5_AUTOMATED_SECURITY_COMPLETE`，不得声明 D5 / Phase D COMPLETE。
