import { useCallback, useRef, useState } from "react";
import { chatStream, Citation, ChatMessage, sendFeedback } from "../api/client";

function genSession(): string {
  const s = localStorage.getItem("srm_session");
  if (s) return s;
  const n = Math.random().toString(36).slice(2) + Date.now().toString(36);
  localStorage.setItem("srm_session", n);
  return n;
}

export function useChat() {
  const [sessionId, setSessionId] = useState<string>(() => genSession());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const assistantIdx = useRef<number>(-1);

  const send = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || loading) return;
      setLoading(true);
      const userMsg: ChatMessage = { session_id: sessionId, role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      const botMsg: ChatMessage = {
        session_id: sessionId,
        role: "assistant",
        content: "",
        citations: [],
      };
      setMessages((prev) => {
        assistantIdx.current = prev.length + 1;
        return [...prev, botMsg];
      });

      const patch = (fn: (m: ChatMessage) => ChatMessage) =>
        setMessages((prev) =>
          prev.map((m, i) => (i === assistantIdx.current ? fn(m) : m))
        );

      try {
        await chatStream(sessionId, content, {
          onCitation: (items: Citation[]) => patch((m) => ({ ...m, citations: items })),
          onDelta: (t: string) => patch((m) => ({ ...m, content: m.content + t })),
          onDone: (d) => patch((m) => ({ ...m, id: d.message_id })),
        });
      } catch (e) {
        patch((m) => ({ ...m, content: "⚠️ 服务暂时不可用，请稍后重试。" }));
      } finally {
        setLoading(false);
      }
    },
    [sessionId, loading]
  );

  const reset = useCallback(() => {
    const n = Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("srm_session", n);
    setSessionId(n);
    setMessages([]);
  }, []);

  const rate = useCallback(
    (messageId: number, rating: number) => {
      sendFeedback(sessionId, messageId, rating);
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, rating } : m))
      );
    },
    [sessionId]
  );

  return { sessionId, messages, loading, send, reset, rate };
}
