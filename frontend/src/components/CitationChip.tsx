import { useState } from "react";
import { Citation } from "../api/client";

function labelOf(c: Citation): string {
  if (c.code) return c.code;
  if (c.flow_code) return c.flow_name ? `${c.flow_code} ${c.flow_name}` : c.flow_code;
  if (c.flow_name) return c.flow_name;
  return c.appendix_type || "来源";
}

export default function CitationChip({ c }: { c: Citation }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ display: "inline-block" }}>
      <button className="chip" onClick={() => setOpen((o) => !o)} title="点击查看出处片段">
        📎 {labelOf(c)}
      </button>
      {open && (
        <div
          style={{
            marginTop: 4,
            padding: "8px 10px",
            border: "1px solid var(--border)",
            borderRadius: 8,
            background: "var(--bg)",
            fontSize: 12,
            color: "var(--text-weak)",
            maxWidth: 480,
            whiteSpace: "pre-wrap",
          }}
        >
          {c.source_snippet}
        </div>
      )}
    </span>
  );
}
