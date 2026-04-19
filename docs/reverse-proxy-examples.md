# Production reverse proxy examples

下面给出适合生产环境的 **Nginx** 和 **Caddy** 配置示例。

假设：

- Invite Center 容器或进程监听：`127.0.0.1:18010`
- 对外域名：`auth.example.com`
- 程序中的环境变量：

```env
AUTH_CENTER_BASE_URL=https://auth.example.com
AUTH_CENTER_PUBLIC_PORT=18010
```

> 如果你是把反向代理直接转发到容器内网地址，也可以把 `127.0.0.1:18010` 换成对应容器地址。

---

## Nginx

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name auth.example.com;

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name auth.example.com;

    ssl_certificate     /etc/letsencrypt/live/auth.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/auth.example.com/privkey.pem;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:18010;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;

        proxy_connect_timeout 30s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

---

## Caddy

```caddy
auth.example.com {
    encode gzip zstd
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }

    reverse_proxy 127.0.0.1:18010 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-Port {server_port}
    }
}
```

---

## 部署建议

1. `AUTH_CENTER_BASE_URL` 必须与对外访问地址一致
2. 生产环境务必使用 HTTPS
3. `.env` 中的以下密钥必须替换为强随机值：
   - `AUTH_CENTER_SESSION_SECRET`
   - `AUTH_CENTER_APP_TOKEN_SECRET`
   - `AUTH_CENTER_ADMIN_KEY`
4. 建议限制服务器防火墙，仅开放：
   - `80/tcp`
   - `443/tcp`
5. 如果不需要外网直接访问容器端口，可只绑定到本机回环地址，例如：

```yaml
ports:
  - "127.0.0.1:18010:8010"
```

这样只能由本机 Nginx / Caddy 转发访问。
6. 如果后端已经加了 CSP / 安全响应头，建议不要在反向代理重复设置冲突版本。
