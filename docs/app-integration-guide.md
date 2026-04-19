# 通用 App 接入 Invite Center 说明

这份文档面向 **任意业务应用**，不局限于 `grok2api`。

目标是让你的 App 不再自己维护注册 / 登录 / 找回密码，而是统一接入 `Invite Center`。

---

## 适用场景

适用于：

- 单页应用（SPA）
- 前后端分离系统
- 传统服务端渲染应用
- 内部管理后台
- 多个系统共用一套账号体系

---

## 核心概念

Invite Center 里有两类 token：

### 1. Session Token

- 由 Invite Center 自己管理
- 用于用户在 Invite Center 内部保持登录状态
- 现在通过 **HttpOnly Cookie** 保存
- 业务 App 不需要自己解析这个 token

### 2. App Token

- 由 Invite Center 为某个具体 App 签发
- 只包含该 App 需要的身份和权限信息
- 业务 App 只信任这个 token

---

## 接入总流程

### 标准流程

1. 用户访问你的 App
2. 你的 App 发现用户未登录
3. 跳转到 Invite Center 登录页：

```text
https://auth.example.com/login?app_slug=your-app
```

4. 用户在 Invite Center 登录成功
5. Invite Center 根据 `your-app` 的配置签发 app token
6. Invite Center 跳转回你配置的 `callback_url`
7. App 在回跳页中读取：

```text
#access_token=...
```

8. App 自己校验 token，或调用 Invite Center 远程校验
9. App 建立自己的业务会话

---

## 在 Invite Center 中需要配置什么

管理员需要先在 Invite Center 中创建应用：

- `slug`：应用唯一标识，例如 `your-app`
- `name`：应用名称
- `callback_url`：登录成功后跳回的地址

例如：

```text
slug: your-app
name: Your App
callback_url: https://app.example.com/auth/callback
```

> 建议 `callback_url` 使用固定可信地址，不要使用通配或动态拼接地址。

---

## App 侧推荐接入方式

## 方案 A：浏览器前端跳转接入（推荐）

适合：

- SPA
- 管理后台
- WebUI

### 步骤 1：未登录时跳转到 Invite Center

```js
function goLogin() {
  const url = new URL('https://auth.example.com/login');
  url.searchParams.set('app_slug', 'your-app');
  location.href = url.toString();
}
```

### 步骤 2：在回调页面读取 hash 中的 `access_token`

```js
const hash = new URLSearchParams(location.hash.startsWith('#') ? location.hash.slice(1) : location.hash);
const accessToken = hash.get('access_token') || '';

if (accessToken) {
  sessionStorage.setItem('your_app_access_token', accessToken);
  history.replaceState(null, '', location.pathname + location.search);
}
```

### 步骤 3：用 app token 调你自己的后端

```js
fetch('/api/me', {
  headers: {
    Authorization: `Bearer ${accessToken}`
  }
});
```

> 建议读取完成后立刻清掉 URL 中的 hash，避免截图、复制链接时泄露 token。

---

## 方案 B：前端拿 token，后端换业务会话（更推荐）

适合：

- 对安全要求更高的系统
- 想让浏览器端尽量少长期持有 app token 的系统

### 流程

1. 前端从回调页拿到 `access_token`
2. 前端立即把它发给你的后端
3. 后端校验成功后，设置你自己的业务 Session Cookie
4. 前端删除临时 token

### 示例

前端：

```js
await fetch('/api/auth/exchange', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({ access_token: accessToken })
});
```

后端：

1. 校验 `access_token`
2. 读取 claims
3. 创建本地用户会话
4. 返回 HttpOnly 业务 Cookie

这样浏览器后续只使用你自己的业务会话，不再直接依赖 Invite Center 的 app token。

---

## App Token 校验方式

业务 App 有两种校验方式。

## 方式 1：本地验签

适合：

- 内网系统
- 高性能场景
- 你能安全共享密钥的场景

你需要持有：

```env
AUTH_CENTER_APP_TOKEN_SECRET=...
```

校验内容至少包括：

- 签名是否正确
- `purpose` 是否为 `app`
- `exp` 是否未过期
- `app` 是否等于当前应用 slug
- 如果实现了版本控制，还要检查 `ver`

### 优点

- 无需每次请求都访问 Invite Center
- 延迟低

### 缺点

- 密钥要安全分发到每个 App
- 如果你要做更强的实时撤销，需要结合中心侧回查或缩短 token TTL

---

## 方式 2：远程校验

适合：

- 不想在业务系统中保存共享密钥
- 想让 Invite Center 统一做校验逻辑

调用：

```http
GET /api/auth/verify?app_slug=your-app
Authorization: Bearer <app_token>
```

返回：

```json
{
  "status": "ok",
  "claims": {
    "purpose": "app",
    "sub": 1,
    "email": "user@example.com",
    "app": "your-app",
    "role": "member",
    "target": "dashboard",
    "metadata": {},
    "callback_url": "https://app.example.com/auth/callback",
    "ver": 3,
    "iat": 1710000000,
    "exp": 1710003600
  }
}
```

### 优点

- 业务侧更简单
- 不需要分发签名密钥

### 缺点

- 每次校验都依赖 Invite Center
- 有额外网络延迟

---

## claims 字段建议如何使用

Invite Center 当前 app token 常见字段：

- `sub`：中心用户 ID
- `email`：用户邮箱
- `app`：当前应用 slug
- `role`：应用内角色
- `target`：默认目标页面 / 功能入口
- `metadata`：扩展字段
- `callback_url`：该应用登记的回调地址
- `ver`：token 版本
- `iat`：签发时间
- `exp`：过期时间

### 建议映射

| claim | 业务用途 |
|---|---|
| `email` | 显示身份、审计日志、建立本地账号映射 |
| `role` | 基础权限控制 |
| `target` | 默认首页、默认工作台、默认路由 |
| `metadata` | 细粒度功能控制 |
| `sub` | 中心用户唯一标识 |

---

## 首次登录时本地用户怎么处理

推荐做法：

### 自动建档

当业务 App 第一次看到某个 `email` 或 `sub` 时：

1. 自动创建本地用户记录
2. 保存：
   - `auth_center_user_id`
   - `email`
   - 最近一次 `role`
   - 最近一次 `metadata`
3. 后续登录时做同步更新

### 不推荐

- 再让用户在业务系统里单独注册一次
- 再维护一套独立密码

---

## 权限控制建议

不要只判断“是否登录”，建议至少做两层：

### 1. 是否属于当前 App

```text
claims.app == your-app
```

### 2. 是否具备角色 / 功能权限

例如：

- `role=admin`
- `role=member`
- `metadata.features=["chat","billing"]`

---

## 登出建议

业务 App 的登出通常分两层：

### 1. App 本地登出

- 清理你自己的业务 Session
- 如果你把临时 token 放在前端，也一并清掉

### 2. 跳转到 Invite Center 登出

如果你希望统一退出中心登录态，可跳转：

```text
https://auth.example.com/logout?return_to=/login
```

> 当前 `return_to` 建议仅使用站内相对路径。

---

## 推荐的回调页实现

你的 App 最少准备一个：

```text
/auth/callback
```

建议它只做三件事：

1. 从 URL hash 读取 `access_token`
2. 发给后端换取业务会话
3. 清理地址栏并跳转到业务首页

---

## 前后端分离应用的推荐架构

推荐结构：

```text
Browser
  -> Invite Center 登录
  -> 回到 /auth/callback#access_token=...
  -> POST /api/auth/exchange
Backend
  -> 校验 app token
  -> 建立本地 session
  -> Set-Cookie
Browser
  -> 后续只带业务 Cookie
```

这样比长期在浏览器中保存 app token 更稳妥。

---

## 移动端 / 桌面端怎么接

也可以接，原则一样：

1. 打开 Invite Center 登录页
2. 登录成功后回跳到你的回调地址
3. 从 fragment 中取出 `access_token`
4. 本地校验或发后端换会话

如果是 App 端，建议使用：

- 自定义 scheme
- 或 universal link / app link

---

## 安全建议

### 必做

- `callback_url` 必须固定、可信
- 生产环境必须 HTTPS
- 不要把 `access_token` 放 query 参数
- 读取 hash 后立刻清理地址栏
- 后端必须校验 `app_slug`
- 对敏感接口做权限判断，不只判断是否登录

### 推荐

- 优先用“前端拿 token，后端换业务会话”的模式
- 本地 session 使用 `HttpOnly + Secure + SameSite`
- 记录登录审计日志
- 定期缩短 app token TTL

---

## 最小接入清单

如果你想最快接入，一个 App 至少需要：

### Invite Center 侧

- [ ] 创建 app
- [ ] 配置 `slug`
- [ ] 配置 `callback_url`
- [ ] 给测试用户开通权限

### App 侧

- [ ] 准备 `/auth/callback`
- [ ] 跳转到 `/login?app_slug=your-app`
- [ ] 读取 hash 中的 `access_token`
- [ ] 校验 token 或调用 `/api/auth/verify`
- [ ] 建立本地登录态
- [ ] 按 `role / metadata` 做权限控制

---

## 推荐环境变量

如果业务 App 走远程校验：

```env
AUTH_CENTER_BASE_URL=https://auth.example.com
AUTH_CENTER_VERIFY_URL=https://auth.example.com/api/auth/verify
AUTH_CENTER_APP_SLUG=your-app
AUTH_CENTER_MODE=remote_verify
```

如果业务 App 走本地验签：

```env
AUTH_CENTER_BASE_URL=https://auth.example.com
AUTH_CENTER_APP_SLUG=your-app
AUTH_CENTER_APP_TOKEN_SECRET=change-me
AUTH_CENTER_MODE=local_verify
```

---

## 一个完整例子

### 登录入口

```js
location.href = 'https://auth.example.com/login?app_slug=your-app';
```

### 回调页

```js
const hash = new URLSearchParams(location.hash.slice(1));
const accessToken = hash.get('access_token');

if (accessToken) {
  await fetch('/api/auth/exchange', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ access_token: accessToken })
  });
  history.replaceState(null, '', '/');
  location.href = '/';
}
```

### 后端换会话

```text
1. 收到 access_token
2. 校验签名 / 或远程 verify
3. 确认 claims.app == your-app
4. 读取 email / role / metadata
5. 创建或更新本地用户
6. Set-Cookie 返回业务 session
```

---

## 总结

对业务 App 来说，最推荐的模式是：

1. 跳转到 Invite Center 登录
2. 从回调页拿到 `#access_token`
3. 立即发给自己后端
4. 后端校验后建立本地业务会话

这样既能统一账号体系，也能把安全边界控制在业务系统内部。
