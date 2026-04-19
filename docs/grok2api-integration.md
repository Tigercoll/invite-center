# grok2api 对接 Invite Center

## 目标

让 `grok2api` 不再自己管理注册/登录，而是信任 `invite-center` 签发的应用 token。

## 推荐方式

### 1. 用户先在 Invite Center 登录

- 用户访问 `https://auth.example.com/login`
- 登录成功后拿到 `session token`

### 2. 前端向 Invite Center 申请 grok2api 专用 token

调用：

```http
POST /api/auth/access-token
Authorization: Bearer <session_token>
Content-Type: application/json

{
  "app_slug": "grok2api"
}
```

返回：

```json
{
  "status": "ok",
  "token": "<app_token>",
  "claims": {
    "email": "user@example.com",
    "slug": "grok2api",
    "role": "member",
    "default_target": "chat",
    "metadata": {
      "webui": "chat"
    }
  }
}
```

### 3. grok2api 校验 app token

两种方式：

#### A. 本地验签

grok2api 持有与 Invite Center 相同的：

- `AUTH_CENTER_APP_TOKEN_SECRET`

然后本地校验签名与过期时间。

#### B. 远程校验

grok2api 调：

```http
GET /api/auth/verify
Authorization: Bearer <app_token>
?app_slug=grok2api
```

## 推荐 JWT Claims

Invite Center 现在 app token 已包含：

- `purpose=app`
- `sub`
- `email`
- `app`
- `role`
- `target`
- `metadata`
- `iat`
- `exp`

## grok2api 应如何使用 claims

### WebUI 路由限制

根据：

- `target`
或
- `metadata.webui`

决定用户能访问：

- `/webui/chat`
- `/webui/masonry`
- `/webui/chatkit`

### 用户识别

使用：

- `email`

作为展示身份和审计主体。

## 环境变量建议

在 `grok2api` 中新增：

```env
AUTH_CENTER_VERIFY_URL=https://auth.example.com/api/auth/verify
AUTH_CENTER_APP_TOKEN_SECRET=change-me
AUTH_CENTER_MODE=remote_verify
```

其中：

- `remote_verify`：每次走远程校验
- `local_verify`：本地验签

## 前端改造建议

`grok2api` WebUI 登录页可简化为：

- “前往统一登录中心”

登录完成后回跳时携带：

- app token

或先写入前端存储，再访问 grok2api。
