export default function FeedbackBar({
  messageId,
  rating,
  onRate,
}: {
  messageId: number;
  rating: number;
  onRate: (id: number, r: number) => void;
}) {
  if (rating !== 0) {
    return <div className="feedback"><span className="done">已反馈，感谢！</span></div>;
  }
  return (
    <div className="feedback">
      <span style={{ fontSize: 12, color: "var(--text-weak)" }}>有帮助吗？</span>
      <button onClick={() => onRate(messageId, 1)} title="有帮助">👍</button>
      <button onClick={() => onRate(messageId, -1)} title="没帮助">👎</button>
    </div>
  );
}
