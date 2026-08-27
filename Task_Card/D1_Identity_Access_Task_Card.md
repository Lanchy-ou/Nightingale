# D1 任务卡 - Identity, Invite, Login and Session

> 状态：**COMPLETE（2026-08-27 审查修复后重验）**
>
> 对应总计划：`docs/phase_d_product_completion_plan.md`
>
> 前置：M3 server-side RBAC 已完成；现有 DB `User` 仍是 role/clinic/patient identity authority。
>
> 完成验证：222 pytest 绿（161 legacy 零回归 + 60 个 auth 测试 + 1 seed 完整性断言）；frontend production build 绿；uvicorn + curl 真实验证 invite → register → login → session → logout、patient 绑定、cross-clinic 404、四角色登录。审查修复额外锁定了安全 422、登录等成本验证、并发 invite 单次消费及 revoke/audit 原子性。实现记录见 `AGENTS.md` §24。

---

## 1. 目标

用真实 Demo 身份流程替代产品中的 Role header 模拟：

```text
Invite -> Register -> Login -> Session -> Authorized product shell -> Logout
```

D1 只解决身份进入和 session，不在本卡重做 Patient UI、Task、Transcript 或 Copilot。

---

## 2. 已冻结决策

- clinician/staff/admin 只能通过 clinic invite 注册；
- patient invite 必须预先绑定 `clinic_id + patient_id`；
- 注册者不能修改 invite 中的 role、clinic 或 patient binding；
- Demo 不发送真实邮件，Admin 可以复制一次性邀请链接；
- 密码只存强哈希；session token 只以 hash/opaque id 持久化；
- browser 使用 `HttpOnly` cookie；非开发产品请求不再接受 `X-User-Id/X-Role` 作为身份；
- legacy demo headers 只允许显式 `NANTINGALE_DEMO_AUTH=true` 的测试/开发模式，默认关闭；
- 单用户单 clinic；MFA/SSO/跨 clinic membership 后置。

---

## 3. 最小数据模型

### Invite

```text
invite_id
clinic_id
email
role                 # patient|staff|clinician|admin
patient_id           # patient invite required; clinical roles null
token_hash
expires_at
used_at
created_by
created_at
```

### UserCredential

```text
user_id
email_normalized
password_hash
created_at
password_changed_at
disabled_at
```

### Session

```text
session_id
user_id
token_hash
created_at
expires_at
revoked_at
last_seen_at
```

不把 password、raw invite token 或 raw session token 写入 AuditLog。

---

## 4. Backend 范围

最小端点：

```text
POST /api/auth/invites                   # admin; clinic-scoped
POST /api/auth/invites/preview           # token in JSON body; no sensitive enumeration
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/session                   # current identity
```

要求：

- password hashing 使用维护中的标准库（优先 Argon2id；最终依赖与 license 写入 ATTRIBUTION）；
- login/register 返回通用错误，不能暴露 email 是否存在；
- invite token 至少 128-bit 随机，只持久化 hash；
- invite 使用和 User/UserCredential 创建在一个 transaction；
- session cookie 至少 `HttpOnly`、`SameSite=Lax`；部署 HTTPS 后必须 `Secure`；
- logout 原子 revoke 当前 session；
- disabled/expired/revoked session 统一 401；
- session identity 进入现有 `RoleContext`，继续复用 `authorize`；
- Admin 只能邀请本 clinic 用户；不能指定其他 clinic；
- patient invite 的 patient 必须属于同 clinic；
- AuditLog 记录 invite_created、register、login_success、login_failure metadata、logout、session_revoked，不记录秘密或密码。

---

## 5. Frontend 范围

新增最小页面：

- Login；
- Accept Invite / Register；
- Invalid/Expired/Used Invite；
- Admin Invite form/list；
- Unauthorized session recovery；
- Logout。

路由行为：

- 未登录访问临床/患者页面 -> Login；
- 登录 clinician/staff/admin -> clinic shell；
- 登录 patient -> Patient shell；
- 403 不切换到其他角色；
- 401 清除客户端敏感状态并回 Login；
- 产品 shell 不显示 Role selector；development toolbar 由显式 env flag 控制；
- 刷新页面通过 `/api/auth/session` 恢复身份，不从 localStorage 信任 role。

---

## 6. 必须测试

建议新增：

```text
tests/test_auth_invites.py
tests/test_auth_sessions.py
tests/test_auth_routing_scope.py
```

覆盖：

- admin 创建同 clinic clinician/staff/patient invite；
- staff/clinician/patient 不能创建 invite；
- admin 不能邀请到其他 clinic；
- patient invite 必须绑定同 clinic patient；
- invite token 单次使用、过期拒绝、篡改拒绝；
- 注册请求不能覆盖 invite role/clinic/patient_id；
- password DB 值不是明文且正确/错误密码行为确定；
- login 创建 session，logout/revoke 后立即 401；
- cookie flags 在测试配置中符合合同；
- session user 的 DB role 变化后不允许旧 header 提权；
- patient session 仍无法访问 comments/raw AI notes；
- cross-clinic 仍返回统一 404；
- legacy demo headers 默认关闭，仅测试 flag 开启时可用；
- 登录错误响应不泄漏账户存在性；
- 全部既有 RBAC tests 零回归。

Frontend 至少验证：

- production build；
- refresh session restore；
- logout 清空 patient/source/comment/copilot draft 状态；
- clinician 与 patient 登录后进入不同 shell。

---

## 7. Exit Gate - D1 Complete

1. 四角色均能通过 invite/register/login 进入正确视图；
2. 产品身份完全来自 server-side session 和 DB User；
3. 非开发模式下 Role selector 与 demo headers 不可用；
4. patient invite 不会创建第二份 disconnected Patient 记录；
5. 密码、invite token、session token 不以明文落库/入日志；
6. logout、过期、revoke 立即生效；
7. 新 auth tests、全量 backend tests、frontend build 全绿；
8. README 写明 Demo auth 与 production identity verification 的边界。

---

## 8. 明确非目标

- MFA、SSO、OAuth；
- 真实邮件/SMS；
- forgot-password provider（可先保留 admin revoke/reinvite）；
- 用户自行创建 clinic；
- 一个用户多个 clinic；
- production KYC/clinician license verification；
- 患者按姓名/IC 搜索并认领记录。

---

## 9. 停止条件

- 需要重新把 role 放回前端/请求头作为权限权威 -> 停止；
- patient 注册会创建第二条纵向记录 -> 停止；
- raw token/password 需要写入日志用于调试 -> 禁止；
- 为快速登录而放松现有 clinic scope/404 anti-enumeration -> 停止并修复设计。
