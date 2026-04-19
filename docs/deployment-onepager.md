# Invite Center 一页部署手册

这是面向生产环境的最简部署手册。

---

## 1. 准备

服务器建议：

- Linux
- Docker / Docker Compose
- 反向代理：Nginx 或 Caddy
- 域名：例如 `auth.example.com`

---

## 2. 拉代码

```bash
git clone git@github.com:Tigercoll/invite-center.git
cd invite-center
```

---

## 3. 配置环境变量

```bash
cp .env.example .env
```

至少修改：

```env
AUTH_CENTER_SESSION_SECRET=请换成强随机字符串
AUTH_CENTER_APP_TOKEN_SECRET=请换成强随机字符串
AUTH_CENTER_ADMIN_KEY=请换成强随机字符串
AUTH_CENTER_ALLOW_ADMIN_KEY=0

AUTH_CENTER_BASE_URL=https://auth.example.com
AUTH_CENTER_PUBLIC_PORT=18010

AUTH_CENTER_ADMIN_EMAILS=admin@example.com
AUTH_CENTER_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
AUTH_CENTER_BOOTSTRAP_ADMIN_PASSWORD=ChangeThisPasswordNow

MAIL_API_URL=https://mail.tigerzsh.com/api/send_mail
MAIL_API_TOKEN=your-mail-api-token
MAIL_FROM_NAME=grok@tigerzsh.com
```

---

## 4. 启动

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
docker compose logs -f invite-center
```

---

## 5. 反向代理

反向代理转发到：

```text
127.0.0.1:18010
```

建议：

- 只开放 80 / 443
- 容器端口仅绑定本机
- 外部统一走 HTTPS

参考：

- `docs/reverse-proxy-examples.md`

---

## 6. 初始化检查

打开：

```text
https://auth.example.com/health
https://auth.example.com/login
https://auth.example.com/admin
```

确认：

- 健康检查正常
- 管理员可登录
- 能创建 app
- 能发邀请 / 提交申请 / 重置密码

---

## 7. 创建第一个业务 App

在后台创建：

- `slug`
- `name`
- `callback_url`

例如：

```text
slug: your-app
name: Your App
callback_url: https://app.example.com/auth/callback
```

---

## 8. 业务 App 接入

业务 App 登录入口：

```text
https://auth.example.com/login?app_slug=your-app
```

业务 App 回调页：

- 从 `#access_token=...` 读取 token
- 发给自己后端 `/api/auth/exchange`
- 后端换成本地业务 session

参考：

- `docs/app-integration-guide.md`
- `docs/backend-integration-examples.md`
- `docs/callback-template.html`

---

## 9. 安全建议

- `AUTH_CENTER_ALLOW_ADMIN_KEY=0`
- 生产必须 HTTPS
- 不要把 token 放 query 参数
- 定期轮换密钥
- 备份 `data/auth_center.db`
- 只把容器端口绑定到 `127.0.0.1`

---

## 10. 回归检查

每次升级后至少验证：

- 登录
- 申请开通
- 邀请注册
- 忘记密码 / 重置密码
- app token 跳转
- 管理后台审批

参考：

- `docs/pentest-checklist.md`
