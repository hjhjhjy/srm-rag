# 嵌入 SRM 系统（iframe 集成指南）

本助手以独立 Web 应用形式开发，通过 **iframe 零代码嵌入** SRM 系统，作为供应商侧的智能问答入口。

## 1. 最简嵌入

```html
<iframe
  src="https://your-deploy-host/"
  width="420"
  height="720"
  style="border:0;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,.12)"
  title="青山利康 SRM 供应商智能助手"
  allow="clipboard-write">
</iframe>
```

## 2. 父页 ↔ 子应用 通信协议（postMessage）

子应用加载完成后向父页发送握手，父页可下发主题与认证令牌。

### 子应用 → 父页
| 消息 | 说明 |
|---|---|
| `{ type: "ready" }` | 子应用已就绪，可接收指令 |
| `{ type: "resize", height: <number> }` | 内容高度变化，父页可据此自适应 iframe 高度 |

### 父页 → 子应用
| 消息 | 说明 |
|---|---|
| `{ type: "theme", theme: "dark" \| "light", primary?: "#hex" }` | 同步 SRM 主题色 |
| `{ type: "auth", token: "<JWT>" }` | 下发供应商登录态 JWT，子应用据此调用问答接口 |

```javascript
// 父页示例：用户登录 SRM 后，把供应商令牌下发给助手
const frame = document.getElementById('srm-assistant');
frame.contentWindow.postMessage(
  { type: 'auth', token: supplierJwt },
  'https://your-deploy-host/'
);
// 同步主题
frame.contentWindow.postMessage({ type: 'theme', theme: 'light', primary: '#1f6feb' }, '*');

// 监听子应用高度自适应
window.addEventListener('message', (e) => {
  if (e.data?.type === 'resize') {
    frame.style.height = e.data.height + 'px';
  }
});
```

## 3. 认证模式建议

| 场景 | 做法 |
|---|---|
| 开发 / 演示 | 使用服务级 API Key（`VITE_API_KEY` 或 `X-API-Key`），开箱即用 |
| 生产（供应商登录态） | SRM 后端为该供应商签发 JWT，经 `postMessage` 下发；子应用以 `Authorization: Bearer` 调用 |
| 生产（后端服务调用） | SRM 后端直接用服务级 API Key 调用 `/api/chat/sync` 并渲染结果 |

> **安全**：生产务必将 `IFRAME_ALLOWED_ORIGINS` 限定为 SRM 域名，并将 `CORS_ORIGINS`、`API_KEYS`、`JWT_SECRET` 改为强随机值，禁用 `*`。

## 4. 反向代理（同域部署，免 CORS）

若与 SRM 同域部署，建议由网关将 `/srm-assistant` 反代到助手服务、`/srm-assistant/api` 反代到后端 `:8000`，前端请求相对路径 `/api` 即可，无需跨域。nginx 示例见 `deploy/nginx.conf`。

## 5. 主题定制

子应用支持通过 URL 参数或 postMessage 注入主色：
```
https://your-deploy-host/?theme=dark&primary=%231f6feb
```
UIColor 变量集中在 `frontend/src/styles.css` 的 `:root` 与 `[data-theme="dark"]`，可按品牌调整。
