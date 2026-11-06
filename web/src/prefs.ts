// Per-browser preferences (theme, language, followed players and editions). Browser storage only:
// nothing is sent to the server, and the site works the same when storage is unavailable.
import { useCallback, useSyncExternalStore } from "react";

export interface Followed { id: string; name: string; kind: "player" | "championship" }
interface Prefs { theme: "system" | "light" | "dark"; locale?: string; followed: Followed[] }
const KEY = "dqmj3p-portal";
const listeners = new Set<() => void>();
let prefs: Prefs = read();

function read(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    const p = raw ? JSON.parse(raw) : {};
    return { theme: p.theme ?? "system", locale: p.locale, followed: Array.isArray(p.followed) ? p.followed : [] };
  } catch {
    return { theme: "system", followed: [] };
  }
}

function write(next: Prefs) {
  prefs = next;
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* private mode: keep in memory */ }
  listeners.forEach((l) => l());
}

const subscribe = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l); }; };

export function usePrefs() {
  const value = useSyncExternalStore(subscribe, () => prefs);
  const update = useCallback((patch: Partial<Prefs>) => write({ ...prefs, ...patch }), []);
  return [value, update] as const;
}

export function useFollow(item: Followed) {
  const [p, update] = usePrefs();
  const on = p.followed.some((f) => f.id === item.id && f.kind === item.kind);
  const toggle = () => update({
    followed: on ? p.followed.filter((f) => !(f.id === item.id && f.kind === item.kind)) : [...p.followed, item].slice(-50),
  });
  return [on, toggle] as const;
}

export function applyTheme(theme: Prefs["theme"]) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

export function getPrefs() { return prefs; }
export function setLocalePref(locale: string) { write({ ...prefs, locale }); }
