# Invite Center

独立的邀请注册 / 登录 / 找回密码中心，可为多个项目提供统一用户体系。

适合以下场景：

- `grok2api`
- 自建 WebUI / 后台系统
- 多个项目共用一套账号体系
- 需要“申请 -> 审核 -> 开通”流程的内部服务

---

## 功能概览

- 多应用管理
- 邀请注册
- 注册申请与管理员审核
- 邮箱密码登录
- 忘记密码 / 重置密码
- Session Token
- 应用 Access Token 签发与校验
- 邮件 API 发送邀请、审核通知、重置密码邮件
- 内置管理后台页面

---

## 目录结构

```text
invite-center/
├── app/                  # FastAPI 应用与静态页面
├── data/                 # SQLite 数据目录（默认不提交）
├── docs/                 # 接入说明
├── scripts/              # 启动脚本
├── tests/                # 单元测试
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## 核心流程

### 1) 新用户邀请注册

1. 管理员为某个应用创建邀请
2. 用户收到邮件并访问注册链接
3. 用户设置密码并完成注册
4. 系统自动给该用户签发 session token
5. 用户可继续为目标应用申请 access token

### 2) 用户申请开通

1. 用户先在 `/apply` 页面提交申请
2. 管理员在 `/admin` 审核
3. 若用户还没有账号，系统发送注册链接
4. 若用户已有账号，系统直接开通该应用访问权限

### 2.5) 管理员直接给已有用户开通

1. 管理员进入 `/admin`
2. 在“直接给已有用户开通应用”表单中选择应用、填写邮箱
3. 提交后系统直接为该已有账号写入应用权限
4. 如已启用邮件能力，会给该用户发送开通通知

### 3) 应用对接认证中心

1. 前端跳转到 Invite Center 登录
2. 登录成功后调用 `POST /api/auth/access-token`
3. 业务系统本地验签，或调用 `GET /api/auth/verify`

---

## 安全说明

- `.env` 与 `data/` 默认不会提交到 Git
- 密码使用 `PBKDF2-HMAC-SHA256`
- Session Token 与 App Token 使用 HMAC 签名
- 浏览器登录会话改为 `HttpOnly` Cookie 保存，不再放在 `localStorage`
- 应用跳转时，`access_token` 放在 URL `hash fragment` 中，而不是 query 参数
- **已存在账号不能再通过邀请注册链接重设密码**
  - 若邮箱已注册，应直接登录
  - 若需要为已有账号开通新应用，推荐走“申请审核”流程
- 登录 / 忘记密码 / 申请开通接口已增加基础限流

---

## 环境要求

- Python `>= 3.11`
- 推荐使用 Docker / Docker Compose 部署

---

## 本地开发运行

```bash
cd /root/invite-center
cp .env.example .env
python3 -m compileall app
python3 -m unittest tests.test_core
granian --interface asgi --host 0.0.0.0 --port 8010 app.main:app
```

默认访问：

- 登录页：`http://127.0.0.1:8010/login`
- 管理后台：`http://127.0.0.1:8010/admin`
- 健康检查：`http://127.0.0.1:8010/health`

---

## Docker Compose 部署

### 1. 准备配置

```bash
cd /root/invite-center
cp .env.example .env
```

至少修改以下变量：

```env
AUTH_CENTER_SESSION_SECRET=请替换为强随机字符串
AUTH_CENTER_APP_TOKEN_SECRET=请替换为强随机字符串
AUTH_CENTER_ADMIN_KEY=请替换为强随机字符串
AUTH_CENTER_ALLOW_ADMIN_KEY=0
AUTH_CENTER_BASE_URL=https://your-auth-domain.example.com
AUTH_CENTER_PUBLIC_PORT=18010

# 可选但推荐
AUTH_CENTER_ADMIN_EMAILS=admin@example.com
AUTH_CENTER_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
AUTH_CENTER_BOOTSTRAP_ADMIN_PASSWORD=ChangeThisPasswordNow

# 如果要发邮件，必须配置
MAIL_API_URL=https://mail.tigerzsh.com/api/send_mail
MAIL_API_TOKEN=your-mail-api-token
MAIL_FROM_NAME=grok@tigerzsh.com
```

### 2. 启动

```bash
docker compose up -d --build
```

### 3. 查看状态

```bash
docker compose ps
docker compose logs -f invite-center
```

### 4. 停止

```bash
docker compose down
```

数据默认保存在：

```text
./data/auth_center.db
```

---

## 反向代理建议

生产环境建议放在 Nginx / Caddy 后面，并确保：

- `AUTH_CENTER_BASE_URL` 填写外部真实访问地址
- 反向代理转发到容器端口 `8010`
- 对外使用 HTTPS

如果你的外部域名是：

```text
https://auth.example.com
```

那么建议：

```env
AUTH_CENTER_BASE_URL=https://auth.example.com
```

完整示例见：

- `docs/app-integration-guide.md`
- `docs/backend-integration-examples.md`
- `docs/callback-template.html`
- `docs/deployment-onepager.md`
- `docs/reverse-proxy-examples.md`
- `docs/pentest-checklist.md`

---

## 关键环境变量

| 变量 | 说明 |
|---|---|
| `AUTH_CENTER_HOST` | 监听地址，默认 `0.0.0.0` |
| `AUTH_CENTER_PORT` | 容器内监听端口，默认 `8010` |
| `AUTH_CENTER_PUBLIC_PORT` | Compose 对外映射端口，默认 `18010` |
| `AUTH_CENTER_DATA_DIR` | 数据目录 |
| `AUTH_CENTER_DB_PATH` | SQLite 数据库路径 |
| `AUTH_CENTER_SESSION_SECRET` | Session Token 签名密钥 |
| `AUTH_CENTER_APP_TOKEN_SECRET` | App Token 签名密钥 |
| `AUTH_CENTER_ADMIN_KEY` | 管理员静态密钥 |
| `AUTH_CENTER_ALLOW_ADMIN_KEY` | 是否允许使用静态管理员密钥，生产建议为 `0` |
| `AUTH_CENTER_ADMIN_EMAILS` | 管理员邮箱列表，逗号分隔 |
| `AUTH_CENTER_BOOTSTRAP_ADMIN_EMAIL` | 启动时自动创建/更新的管理员邮箱 |
| `AUTH_CENTER_BOOTSTRAP_ADMIN_PASSWORD` | 启动时自动设置的管理员密码 |
| `AUTH_CENTER_SESSION_TTL_HOURS` | Session 有效时长 |
| `AUTH_CENTER_APP_TOKEN_TTL_MINUTES` | App Token 有效时长 |
| `AUTH_CENTER_RESET_TTL_MINUTES` | 重置密码链接有效时长 |
| `AUTH_CENTER_BASE_URL` | 对外访问基地址 |
| `MAIL_API_URL` | 邮件 API 地址 |
| `MAIL_API_TOKEN` | 邮件 API Token |
| `MAIL_FROM_NAME` | 发件人名称 |
| `BOOTSTRAP_APP_SLUG` | 默认初始化应用 slug |
| `BOOTSTRAP_APP_NAME` | 默认初始化应用名称 |

---

## 常用页面

- `/login` 登录页
- `/logout` 退出页
- `/apply` 申请开通页
- `/register` 邀请注册页
- `/forgot-password` 忘记密码
- `/reset-password` 重置密码
- `/admin` 管理后台

---

## 主要 API

### 用户接口

- `GET /api/meta`
- `GET /api/auth/app`
- `GET /api/auth/invite`
- `POST /api/auth/applications`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/access-token`
- `GET /api/auth/verify`
- `POST /api/auth/password/forgot`
- `GET /api/auth/password/reset/verify`
- `POST /api/auth/password/reset`

### 管理接口

- `GET /api/admin/me`
- `GET /api/admin/apps`
- `POST /api/admin/apps`
- `PATCH /api/admin/apps`
- `GET /api/admin/applications`
- `POST /api/admin/applications/approve`
- `POST /api/admin/applications/reject`
- `GET /api/admin/invites`
- `POST /api/admin/invites`
- `POST /api/admin/invites/resend`
- `DELETE /api/admin/invites`
- `GET /api/admin/users`
- `POST /api/admin/users/grant`
- `PATCH /api/admin/users`
- `DELETE /api/admin/users`

---

## 测试

运行测试：

```bash
cd /root/invite-center
python3 -m unittest tests.test_core
```

---

## grok2api 接入建议

可以让 `grok2api`：

1. 跳转到 Invite Center 登录
2. 使用 `POST /api/auth/access-token` 为 `grok2api` 申请 app token
3. `grok2api` 从回跳 URL 的 `hash fragment` 中读取 `access_token`
4. `grok2api` 本地共享密钥验签，或调用 `GET /api/auth/verify`

详细说明见：

- `docs/grok2api-integration.md`
