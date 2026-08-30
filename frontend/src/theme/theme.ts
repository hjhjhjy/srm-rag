export type ThemeMode = "light" | "dark";

export function applyTheme(theme?: ThemeMode, primary?: string) {
  const root = document.documentElement;
  if (theme) root.setAttribute("data-theme", theme);
  if (primary) root.style.setProperty("--primary-color", primary);
}

export function readUrlTheme(): { theme?: ThemeMode; primary?: string } {
  const p = new URLSearchParams(location.search);
  const theme = p.get("theme") as ThemeMode | null;
  const primary = p.get("primary") || undefined;
  return {
    theme: theme === "dark" || theme === "light" ? theme : undefined,
    primary,
  };
}
