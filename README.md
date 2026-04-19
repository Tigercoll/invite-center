# Invite Center

独立的邀请注册 / 登录 / 找回密码中心，可为多个项目提供统一用户体系。

## 功能

- 多应用管理
- 邮箱邀请注册
- 邮箱密码登录
- 忘记密码 / 重置密码
- 邮件 API 发送邀请与重置邮件
- 会话 token
- 应用 access token 签发与校验

## 适用场景

- `grok2api`
- 任意自建 WebUI
- 多项目共享同一套用户中心

## 运行

```bash
cd /root/invite-center
cp .env.example .env
python3 -m compileall app
python3 -m unittest tests.test_core
granian --interface asgi --host 0.0.0.0 --port 8010 app.main:app
```

### Docker Compose

```bash
cd /root/invite-center
cp .env.example .env
# 编辑 .env，至少填好：
# AUTH_CENTER_ADMIN_KEY
# AUTH_CENTER_SESSION_SECRET
# AUTH_CENTER_APP_TOKEN_SECRET
# AUTH_CENTER_BASE_URL
# MAIL_API_TOKEN
docker compose up -d --build
```

## 关键环境变量

- `AUTH_CENTER_ADMIN_KEY`
- `AUTH_CENTER_SESSION_SECRET`
- `AUTH_CENTER_APP_TOKEN_SECRET`
- `AUTH_CENTER_BASE_URL`
- `MAIL_API_URL`
- `MAIL_API_TOKEN`
- `MAIL_FROM_NAME`

## 主要接口

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/access-token`
- `GET /api/auth/verify`
- `POST /api/auth/password/forgot`
- `POST /api/auth/password/reset`
- `GET /api/admin/apps`
- `POST /api/admin/apps`
- `GET /api/admin/invites`
- `POST /api/admin/invites`
- `GET /api/admin/users`

## grok2api 接入建议

后续可以让 grok2api：

1. 跳转到 Invite Center 登录
2. 使用 `POST /api/auth/access-token` 为 `grok2api` 申请 app token
3. grok2api 本地共享密钥验签，或者调用 `GET /api/auth/verify`

详细说明见：

- `docs/grok2api-integration.md`
