import { getToken } from "../iframe/bridge";

export interface AdminStats {
  conversations: number;
  messages: number;
  assistant_messages: number;
  feedback_positive: number;
  feedback_negative: number;
  supplier_accounts: number;
  kb_chunks: number;
  retrieval_hits: number;
  retrieval_miss: number;
  chat_sync: number;
  chat_stream: number;
}

function authHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  // 优先使用管理员登录令牌（JWT），否则回退到 iframe/演示密钥
  const adminTok =
    (window as any).__admin_token__ || localStorage.getItem("srm_admin_token") || "";
  const t = adminTok || getToken() || (import.meta as any).env?.VITE_API_KEY || "srm_dev_demo_key";
  if (t.split(".").length === 3) h["Authorization"] = `Bearer ${t}`;
  else h["X-API-Key"] = t;
  return h;
}

export async function fetchAdminStats(): Promise<AdminStats> {
  const r = await fetch("/api/admin/stats", { headers: authHeaders() });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return await r.json();
}

export async function adminLogin(username: string, password: string): Promise<string> {
  const r = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) throw new Error("用户名或密码错误");
  const j = await r.json();
  return j.access_token as string;
}
