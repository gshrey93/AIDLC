import { useCallback, useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

const OPTIONS = [
  { key: "light", label: "Light", icon: Sun },
  { key: "dark", label: "Dark", icon: Moon },
  { key: "auto", label: "Auto", icon: Monitor },
];

function resolve(theme) {
  if (theme === "auto") {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return theme;
}

function apply(theme) {
  const effective = resolve(theme);
  const root = document.documentElement;
  root.setAttribute("data-theme", effective);
  root.classList.toggle("dark", effective === "dark");
}

export const ThemeToggle = () => {
  const [theme, setTheme] = useState(() => window.localStorage.getItem("bg-theme") || "light");

  useEffect(() => {
    apply(theme);
    window.localStorage.setItem("bg-theme", theme);
    if (theme !== "auto" || !window.matchMedia) return undefined;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => apply("auto");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  const choose = useCallback((key) => setTheme(key), []);

  return (
    <div
      className="hidden items-center gap-0.5 rounded-xl p-0.5 sm:flex"
      style={{ background: "rgba(255,255,255,0.14)" }}
      role="group"
      aria-label="Colour theme"
      data-testid="theme-toggle"
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.key}
          type="button"
          onClick={() => choose(opt.key)}
          aria-label={`${opt.label} theme`}
          aria-pressed={theme === opt.key}
          data-testid={`theme-toggle-${opt.key}`}
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-lg transition-colors duration-150",
            theme === opt.key ? "bg-white text-[color:var(--primary-dark)]" : "text-white/80 hover:text-white",
          )}
        >
          <opt.icon className="h-3.5 w-3.5" />
        </button>
      ))}
    </div>
  );
};

export default ThemeToggle;
