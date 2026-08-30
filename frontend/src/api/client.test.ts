import { describe, expect, it } from "vitest";
import { parseSseEvent } from "./client";

describe("parseSseEvent", () => {
  it("解析合法的 data: 事件", () => {
    const ev = parseSseEvent('data: {"type":"delta","content":"你好"}');
    expect(ev).toEqual({ type: "delta", content: "你好" });
  });

  it("忽略非 data 行", () => {
    expect(parseSseEvent(": keep-alive")).toBeNull();
    expect(parseSseEvent("event: ping")).toBeNull();
  });

  it("空 data 负载返回 null", () => {
    expect(parseSseEvent("data:")).toBeNull();
    expect(parseSseEvent("data: ")).toBeNull();
  });

  it("非法 JSON 返回 null", () => {
    expect(parseSseEvent("data: {bad json")).toBeNull();
  });

  it("解析 done 事件携带 message_id", () => {
    const ev = parseSseEvent('data: {"type":"done","message_id":7,"intent":"rag"}');
    expect(ev.message_id).toBe(7);
    expect(ev.intent).toBe("rag");
  });
});
