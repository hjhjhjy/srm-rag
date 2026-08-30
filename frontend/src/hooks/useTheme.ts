import { useEffect, useState } from "react";
import { applyTheme, readUrlTheme, ThemeMode } from "../theme/theme";

export function useTheme() {
  const [theme, setTheme] = useState<ThemeMode>(
    () => (localStorage.getItem("srm_theme") as ThemeMode) || "light"
  );

  useEffect(() => {
    const url = readUrlTheme();
    const initial = url.theme || theme;
    applyTheme(initial);
  }, []);

  const toggle = () => {
    const next: ThemeMode = theme === "light" ? "dark" : "light";
    setTheme(next);
    localStorage.setItem("srm_theme", next);
    applyTheme(next);
  };

  return { theme, toggle };
}
