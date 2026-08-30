import { useEffect, useRef, useState } from "react";
import { getSuggestions } from "./api/client";
import { useChat } from "./hooks/useChat";
import { useIframe } from "./hooks/useIframe";
import { useTheme } from "./hooks/useTheme";
import MessageBubble from "./components/MessageBubble";
import QuickQuestions from "./components/QuickQuestions";
import ThemeToggle from "./components/ThemeToggle";
import AdminPanel from "./components/AdminPanel";

export default function App() {
  useIframe();
  const { theme, toggle } = useTheme();
  const { messages, loading, send, rate } = useChat();
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [showAdmin, setShowAdmin] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getSuggestions().then(setSuggestions).catch(() => setSuggestions([]));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const submit = () => {
    if (!input.trim()) return;
    send(input);
    setInput("");
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="app">
      <div className="app-header">
        <div className="logo">Q</div>
        <div>
          <div className="title">青山利康 SRM 供应商智能助手</div>
          <div className="sub">基于《业务蓝图 V5.0》的检索增强问答 · RAG Agent</div>
        </div>
        <div className="spacer" />
        <button className="theme-btn" onClick={() => setShowAdmin(true)} title="运营数据">运营数据</button>
        <ThemeToggle theme={theme} onToggle={toggle} />
      </div>

      <div className="chat-scroll" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="welcome">
            <h2>您好，我是青山利康 SRM 供应商助手 👋</h2>
            <p>我可以帮您了解如何使用 SRM 系统：注册入驻、资质准入、报价投标、合同与订单、对账结算、整改与报表查询等。</p>
            <p>下方常见问题可点选，或直接输入您的问题。</p>
            <QuickQuestions items={suggestions} onPick={send} />
          </div>
        ) : (
          messages.map((m, i) => <MessageBubble key={i} m={m} onRate={rate} />)
        )}
      </div>

      <div className="composer">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="输入您的问题，例如：如何注册成为青山利康供应商？"
        />
        <button onClick={submit} disabled={loading || !input.trim()}>
          {loading ? "…" : "发送"}
        </button>
      </div>

      {showAdmin && <AdminPanel onClose={() => setShowAdmin(false)} />}
    </div>
  );
}
