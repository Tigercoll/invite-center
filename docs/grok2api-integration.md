# grok2api 对接 Invite Center

## 目标

让 `grok2api` 不再自己管理注册/登录，而是信任 `invite-center` 签发的应用 token。

## 推荐方式

### 1. 用户先在 Invite Center 登录

- 用户访问 `https://auth.example.com/login?app_slug=grok2api`
- 登录成功后，Invite Center 会使用自身的 `HttpOnly` 会话 Cookie

### 2. Invite Center 自动跳转回 grok2api

Invite Center 的 `/launch` 页面会：

1. 向 `POST /api/auth/access-token` 申请 `grok2api` 的 app token
2. 读取该 app 的 `callback_url`
3. 跳转回：

```text
https://grok.example.com/sso/callback#access_token=<app_token>
```

注意：

- 现在 token 在 **URL hash fragment** 中
- 不在 query 参数中
- fragment 默认不会发给服务端，能减少日志泄露风险

### 3. grok2api 前端读取 hash 中的 access token

示例：

```html
<script>
  const hash = new URLSearchParams(location.hash.startsWith('#') ? location.hash.slice(1) : location.hash);
  const accessToken = hash.get('access_token') || '';
  if (accessToken) {
    sessionStorage.setItem('grok2api_access_token', accessToken);
    history.replaceState(null, '', location.pathname + location.search);
  }
</script>
```

建议：

- 读取后立刻清理地址栏中的 hash
- 只在 grok2api 自己的前端短暂保存
- 后续请求通过 `Authorization: Bearer <app_token>` 发送到 grok2api 后端

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
- `callback_url`
- `ver`
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

登录完成后回跳时：

- 从 `hash fragment` 中读取 `access_token`
- 清理地址栏
- 再访问 grok2api 内部页面
