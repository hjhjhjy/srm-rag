// iframe 桥接：与父页（SRM）通过 postMessage 通信。
// 协议：子应用就绪后发 {type:"ready"}；父页可下发 {type:"theme"} / {type:"auth",token}；
// 子应用高度变化时发 {type:"resize", height}。仅接受可信父域消息。

import { applyTheme, ThemeMode } from "../theme/theme";

let token = "";
const allowedRaw =
  typeof window !== "undefined"
    ? (window as any).__IFRAME_ALLOWED_ORIGINS__ || "*"
    : "*";

function isTrusted(origin: string): boolean {
  if (allowedRaw === "*" || allowedRaw.includes("*")) return true;
  return allowedRaw.split(",").map((s: string) => s.trim()).includes(origin);
}

export function getToken(): string {
  return token;
}

export function initIframeBridge() {
  // URL 参数优先
  const url = new URLSearchParams(location.search);
  const t = url.get("theme") as ThemeMode | null;
  const p = url.get("primary");
  applyTheme(t === "dark" || t === "light" ? t : undefined, p || undefined);

  // 通知父页就绪
  try {
    window.parent?.postMessage({ type: "ready" }, "*");
  } catch {
    /* ignore */
  }

  window.addEventListener("message", (e: MessageEvent) => {
    if (!e.origin || !isTrusted(e.origin)) return;
    const data = e.data || {};
    if (data.type === "theme") {
      applyTheme(data.theme, data.primary);
    } else if (data.type === "auth") {
      token = data.token || "";
    }
  });

  // 高度自适应
  const notifyResize = () => {
    const h = document.documentElement.scrollHeight;
    try {
      window.parent?.postMessage({ type: "resize", height: h }, "*");
    } catch {
      /* ignore */
    }
  };
  window.addEventListener("resize", notifyResize);
  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(notifyResize);
    ro.observe(document.body);
  } else {
    setInterval(notifyResize, 500);
  }
  setTimeout(notifyResize, 300);
}
