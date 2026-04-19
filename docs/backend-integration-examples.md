# 后端接入示例（Node / Python / Go）

这份文档补充一组 **通用后端接入示例**，方便任意业务 App 对接 `Invite Center`。

默认假设：

- Invite Center 地址：`https://auth.example.com`
- 业务 App slug：`your-app`
- 回调页会把 `#access_token=...` 发给业务后端的：

```text
POST /api/auth/exchange
```

---

## 推荐后端流程

推荐流程：

1. 前端从回调页拿到 `access_token`
2. 前端调用业务后端 `/api/auth/exchange`
3. 后端校验 token
4. 后端创建自己的业务会话
5. 后端返回自己的 `HttpOnly Cookie`

---

## 方案 1：远程校验

远程校验时，业务后端调用：

```http
GET https://auth.example.com/api/auth/verify?app_slug=your-app
Authorization: Bearer <access_token>
```

适合：

- 不想在业务端保存 `AUTH_CENTER_APP_TOKEN_SECRET`
- 想让 Invite Center 统一做验签与回查

---

## Node.js 示例（Express，远程校验）

```js
import express from 'express';

const app = express();
app.use(express.json());

const AUTH_CENTER_VERIFY_URL =
  process.env.AUTH_CENTER_VERIFY_URL || 'https://auth.example.com/api/auth/verify';
const AUTH_CENTER_APP_SLUG =
  process.env.AUTH_CENTER_APP_SLUG || 'your-app';

async function verifyWithAuthCenter(accessToken) {
  const url = new URL(AUTH_CENTER_VERIFY_URL);
  url.searchParams.set('app_slug', AUTH_CENTER_APP_SLUG);

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/json',
    },
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok || data?.status !== 'ok') {
    throw new Error(data?.detail || data?.error || 'verify failed');
  }

  return data.claims;
}

app.post('/api/auth/exchange', async (req, res) => {
  try {
    const accessToken = String(req.body?.access_token || '').trim();
    if (!accessToken) {
      return res.status(400).json({ error: 'missing access_token' });
    }

    const claims = await verifyWithAuthCenter(accessToken);
    if (claims.app !== AUTH_CENTER_APP_SLUG) {
      return res.status(403).json({ error: 'token app mismatch' });
    }

    // TODO: 根据 claims.email / claims.sub 建立本地用户
    // TODO: 设置你自己的业务 session

    res.cookie('your_app_session', 'replace-with-your-session-id', {
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      path: '/',
    });

    return res.json({
      status: 'ok',
      user: {
        email: claims.email,
        role: claims.role,
        target: claims.target,
        metadata: claims.metadata || {},
      },
    });
  } catch (err) {
    return res.status(401).json({ error: err.message || 'exchange failed' });
  }
});
```

---

## Python 示例（FastAPI，远程校验）

```python
import os
import httpx
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

app = FastAPI()

AUTH_CENTER_VERIFY_URL = os.getenv(
    "AUTH_CENTER_VERIFY_URL",
    "https://auth.example.com/api/auth/verify",
)
AUTH_CENTER_APP_SLUG = os.getenv("AUTH_CENTER_APP_SLUG", "your-app")


class ExchangeRequest(BaseModel):
    access_token: str


async def verify_with_auth_center(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            AUTH_CENTER_VERIFY_URL,
            params={"app_slug": AUTH_CENTER_APP_SLUG},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or str(data.get("status")) != "ok":
        raise ValueError(data.get("detail") or data.get("error") or "verify failed")
    return dict(data["claims"])


@app.post("/api/auth/exchange")
async def exchange(payload: ExchangeRequest, response: Response):
    token = payload.access_token.strip()
    if not token:
        raise HTTPException(400, "missing access_token")

    try:
        claims = await verify_with_auth_center(token)
    except ValueError as exc:
        raise HTTPException(401, str(exc)) from exc

    if claims.get("app") != AUTH_CENTER_APP_SLUG:
        raise HTTPException(403, "token app mismatch")

    # TODO: 根据 claims 建立或更新本地用户
    # TODO: 创建你的业务 session id
    session_id = "replace-with-your-session-id"

    response.set_cookie(
        "your_app_session",
        session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )

    return {
        "status": "ok",
        "user": {
            "email": claims.get("email"),
            "role": claims.get("role"),
            "target": claims.get("target"),
            "metadata": claims.get("metadata") or {},
        },
    }
```

---

## Go 示例（net/http，远程校验）

```go
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"net/http"
	"net/url"
	"os"
	"time"
)

var (
	authCenterVerifyURL = getenv("AUTH_CENTER_VERIFY_URL", "https://auth.example.com/api/auth/verify")
	authCenterAppSlug   = getenv("AUTH_CENTER_APP_SLUG", "your-app")
)

type ExchangeRequest struct {
	AccessToken string `json:"access_token"`
}

type VerifyResponse struct {
	Status string                 `json:"status"`
	Claims map[string]interface{} `json:"claims"`
	Detail string                 `json:"detail"`
	Error  string                 `json:"error"`
}

func getenv(name, fallback string) string {
	if v := os.Getenv(name); v != "" {
		return v
	}
	return fallback
}

func verifyWithAuthCenter(accessToken string) (map[string]interface{}, error) {
	u, err := url.Parse(authCenterVerifyURL)
	if err != nil {
		return nil, err
	}
	q := u.Query()
	q.Set("app_slug", authCenterAppSlug)
	u.RawQuery = q.Encode()

	req, err := http.NewRequest(http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+accessToken)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var data VerifyResponse
	if err := json.NewDecoder(resp.Body).Decode(&data); err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK || data.Status != "ok" {
		if data.Detail != "" {
			return nil, errors.New(data.Detail)
		}
		if data.Error != "" {
			return nil, errors.New(data.Error)
		}
		return nil, errors.New("verify failed")
	}
	return data.Claims, nil
}

func exchangeHandler(w http.ResponseWriter, r *http.Request) {
	var payload ExchangeRequest
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		http.Error(w, "bad request", http.StatusBadRequest)
		return
	}
	if payload.AccessToken == "" {
		http.Error(w, "missing access_token", http.StatusBadRequest)
		return
	}

	claims, err := verifyWithAuthCenter(payload.AccessToken)
	if err != nil {
		http.Error(w, err.Error(), http.StatusUnauthorized)
		return
	}

	if appValue, _ := claims["app"].(string); appValue != authCenterAppSlug {
		http.Error(w, "token app mismatch", http.StatusForbidden)
		return
	}

	http.SetCookie(w, &http.Cookie{
		Name:     "your_app_session",
		Value:    "replace-with-your-session-id",
		Path:     "/",
		HttpOnly: true,
		Secure:   true,
		SameSite: http.SameSiteLaxMode,
	})

	body, _ := json.Marshal(map[string]any{
		"status": "ok",
		"user": map[string]any{
			"email":    claims["email"],
			"role":     claims["role"],
			"target":   claims["target"],
			"metadata": claims["metadata"],
		},
	})

	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write(bytes.TrimSpace(body))
}

func main() {
	http.HandleFunc("/api/auth/exchange", exchangeHandler)
	_ = http.ListenAndServe(":8080", nil)
}
```

---

## 本地验签思路

如果你不想远程校验，可以在业务系统内本地验签。

需要：

```env
AUTH_CENTER_APP_TOKEN_SECRET=...
AUTH_CENTER_APP_SLUG=your-app
```

本地验签至少要做：

1. 拆出 token 的 body 和 signature
2. 使用 `AUTH_CENTER_APP_TOKEN_SECRET` 做 HMAC-SHA256 校验
3. 解析 JSON payload
4. 检查：
   - `purpose == "app"`
   - `app == your-app`
   - `exp > 当前时间`

> 如果你想完全复用 Invite Center 的逻辑，推荐把中心里的签名实现抽成共享库，或直接继续用远程校验。

---

## 业务后端落地时建议做的事

无论你用哪种语言，建议统一做这些步骤：

1. 校验 token
2. 读取 `claims.email / claims.sub / claims.role / claims.metadata`
3. 创建或更新本地用户
4. 建立本地业务 session
5. 返回本地 `HttpOnly Cookie`
6. 后续请求都走自己的 session，不再依赖浏览器长期保存 app token

---

## 推荐的本地用户表字段

建议至少保存：

- `auth_center_user_id`
- `email`
- `last_role`
- `last_target`
- `last_metadata_json`
- `last_login_at`

---

## 最简后端接入清单

- [ ] 提供 `/api/auth/exchange`
- [ ] 校验 `access_token`
- [ ] 检查 `claims.app == your-app`
- [ ] 建立本地 session
- [ ] 返回 `HttpOnly Cookie`
- [ ] 对业务接口按本地 session 鉴权
