import { ThemeMode } from "../theme/theme";

export default function ThemeToggle({ theme, onToggle }: { theme: ThemeMode; onToggle: () => void }) {
  return (
    <button className="theme-btn" onClick={onToggle} title="切换明暗主题">
      {theme === "light" ? "🌙 暗色" : "☀️ 亮色"}
    </button>
  );
}
