import { getToken } from "../iframe/bridge";

export interface Citation {
  flow_code: string;
  flow_name: string;
  appendix_type: string;
  code: string;
  module: string;
  source_snippet: string;
}

export interface ChatMessage {
  id?: number;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations?: Citation[];
  rating?: number;
}

export interface StreamHandlers {
  onSession?: (sessionId: string) => void;
  onCitation?: (items: Citation[]) => void;
  onDelta?: (text: string) => void;
  onDone?: (msg: { message_id: number; intent: string }) => void;
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  // 鉴权优先级：iframe 父页下发的令牌 > 构建期注入的 VITE_API_KEY（开发演示用）
  const t = getToken() || (import.meta as any).env?.VITE_API_KEY || "srm_dev_demo_key";
  if (!t) return h;
  // JWT（三段 base64）走标准 Authorization；其余按服务级 API Key 处理
  if (t.split(".").length === 3) h["Authorization"] = `Bearer ${t}`;
  else h["X-API-Key"] = t;
  return h;
}

/** 解析单条 SSE `data:` 行为事件对象；非 data 行或非法 JSON 返回 null。 */
export function parseSseEvent(line: string): any | null {
  const s = line.trim();
  if (!s.startsWith("data:")) return null;
  const payload = s.slice(5).trim();
  if (!payload) return null;
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

export async function chatStream(
  sessionId: string,
  message: string,
  handlers: StreamHandlers
) {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!resp.body) throw new Error("no stream");
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      const ev = parseSseEvent(line);
      if (!ev) continue;
      if (ev.type === "session") handlers.onSession?.(ev.session_id);
      else if (ev.type === "citation") handlers.onCitation?.(ev.items || []);
      else if (ev.type === "delta") handlers.onDelta?.(ev.content || "");
      else if (ev.type === "done") handlers.onDone?.({ message_id: ev.message_id, intent: ev.intent });
    }
  }
}

export async function getSuggestions(): Promise<string[]> {
  const r = await fetch("/api/suggestions");
  const j = await r.json();
  return (j.items || []).map((x: any) => x.q);
}

export async function sendFeedback(
  sessionId: string,
  messageId: number,
  rating: number,
  comment = ""
) {
  await fetch("/api/feedback", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ session_id: sessionId, message_id: messageId, rating, comment }),
  });
}

export async function healthCheck(): Promise<any> {
  try {
    const r = await fetch("/api/health");
    return await r.json();
  } catch {
    return { status: "down" };
  }
}
