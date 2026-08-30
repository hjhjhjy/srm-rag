export default function QuickQuestions({ items, onPick }: { items: string[]; onPick: (q: string) => void }) {
  if (!items.length) return null;
  return (
    <div className="quick">
      {items.map((q, i) => (
        <button key={i} onClick={() => onPick(q)}>
          {q}
        </button>
      ))}
    </div>
  );
}
