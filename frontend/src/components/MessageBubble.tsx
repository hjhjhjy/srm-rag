import { ChatMessage } from "../api/client";
import CitationChip from "./CitationChip";
import FeedbackBar from "./FeedbackBar";

export default function MessageBubble({ m, onRate }: { m: ChatMessage; onRate: (id: number, r: number) => void }) {
  const isUser = m.role === "user";
  return (
    <div className={`msg ${isUser ? "user" : "bot"}`}>
      <div className={`avatar ${isUser ? "user" : "bot"}`}>{isUser ? "我" : "AI"}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="bubble">
          {m.content || <span className="typing" />}
        </div>
        {!isUser && m.citations && m.citations.length > 0 && (
          <div className="chips">
            {m.citations.map((c, i) => (
              <CitationChip key={i} c={c} />
            ))}
          </div>
        )}
        {!isUser && m.id ? <FeedbackBar messageId={m.id} rating={m.rating || 0} onRate={onRate} /> : null}
      </div>
    </div>
  );
}
