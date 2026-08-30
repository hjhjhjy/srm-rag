import { useEffect, useState } from "react";
import { AdminStats, adminLogin, fetchAdminStats } from "../api/admin";

export default function AdminPanel({ onClose }: { onClose: () => void }) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string>("");
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");

  const load = () => {
    setError("");
    fetchAdminStats()
      .then(setStats)
      .catch((e) => {
        setStats(null);
        setError(e.message.includes("403") || e.message.includes("401")
          ? "需要管理员权限，请先登录"
          : "加载失败，请确认后端已启动");
      });
  };

  useEffect(load, []);

  const login = async () => {
    try {
      const token = await adminLogin(user, pass);
      // 写入桥接令牌，后续请求以 Bearer 携带
      (window as any).__admin_token__ = token;
      window.localStorage.setItem("srm_admin_token", token);
      setUser("");
      setPass("");
      load();
    } catch (e: any) {
      setError(e.message || "登录失败");
    }
  };

  const cards: [string, number | undefined][] = stats
    ? [
        ["会话数", stats.conversations],
        ["消息数", stats.messages],
        ["助手回复", stats.assistant_messages],
        ["👍 正向反馈", stats.feedback_positive],
        ["👎 负向反馈", stats.feedback_negative],
        ["供应商账号", stats.supplier_accounts],
        ["知识库片段", stats.kb_chunks],
        ["检索命中", stats.retrieval_hits],
        ["检索未命中", stats.retrieval_miss],
      ]
    : [];

  return (
    <div className="admin-mask" onClick={onClose}>
      <div className="admin-panel" onClick={(e) => e.stopPropagation()}>
        <div className="admin-head">
          <strong>运营数据（管理员）</strong>
          <button className="theme-btn" onClick={onClose}>关闭</button>
        </div>
        {error && <div className="admin-err">{error}</div>}
        {!stats && (
          <div className="admin-login">
            <input placeholder="管理员账号" value={user} onChange={(e) => setUser(e.target.value)} />
            <input placeholder="密码" type="password" value={pass} onChange={(e) => setPass(e.target.value)} />
            <button className="send-btn" onClick={login}>登录</button>
          </div>
        )}
        {stats && (
          <div className="admin-grid">
            {cards.map(([k, v]) => (
              <div className="admin-card" key={k}>
                <div className="ac-num">{v ?? "-"}</div>
                <div className="ac-label">{k}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
