import { useEffect, useState } from 'react';

export type MultiViewerTheme = 'dark' | 'light';

const STORAGE_KEY = 'multiviewer:theme';
const COOKIE_KEY = 'multiviewer_theme';
const THEME_EVENT = 'multiviewer-theme-change';

function readCookieTheme(): MultiViewerTheme | null {
  try {
    const prefix = `${COOKIE_KEY}=`;
    const raw = document.cookie
      .split(';')
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix));
    const value = raw ? decodeURIComponent(raw.slice(prefix.length)) : '';
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

function readStoredTheme(): MultiViewerTheme {
  const cookieTheme = readCookieTheme();
  if (cookieTheme) return cookieTheme;

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // Persistence can be unavailable; dark remains the safe default.
  }

  return 'dark';
}

function persistTheme(theme: MultiViewerTheme) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Cookie persistence below still provides a cross-port fallback.
  }

  try {
    document.cookie = `${COOKIE_KEY}=${encodeURIComponent(theme)}; Max-Age=31536000; Path=/; SameSite=Lax`;
  } catch {
    // In-memory document state remains functional if cookies are unavailable.
  }
}

export function applyMultiViewerTheme(theme: MultiViewerTheme, persist = true) {
  document.documentElement.dataset.mvTheme = theme;
  document.documentElement.style.colorScheme = theme;
  if (persist) persistTheme(theme);
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}

export function installMultiViewerThemeRuntime() {
  applyMultiViewerTheme(readStoredTheme(), false);
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<MultiViewerTheme>(() => readStoredTheme());

  useEffect(() => {
    const syncFromDocument = () => {
      const live = document.documentElement.dataset.mvTheme;
      if (live === 'light' || live === 'dark') setTheme(live);
    };

    const syncFromPersistence = () => {
      const persisted = readStoredTheme();
      const live = document.documentElement.dataset.mvTheme;
      if (persisted !== live) applyMultiViewerTheme(persisted, false);
      setTheme(persisted);
    };

    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) syncFromPersistence();
    };

    window.addEventListener(THEME_EVENT, syncFromDocument);
    window.addEventListener('storage', onStorage);

    // Cookies are shared across ports for the same host, while localStorage is not.
    // Polling keeps independently served MultiViewer apps aligned when both are open.
    const poll = window.setInterval(syncFromPersistence, 1000);

    syncFromDocument();
    return () => {
      window.removeEventListener(THEME_EVENT, syncFromDocument);
      window.removeEventListener('storage', onStorage);
      window.clearInterval(poll);
    };
  }, []);

  const nextTheme: MultiViewerTheme = theme === 'dark' ? 'light' : 'dark';

  return (
    <button
      type="button"
      className="mv-theme-toggle"
      data-theme={theme}
      onClick={() => applyMultiViewerTheme(nextTheme)}
      aria-label={`Switch to ${nextTheme} theme`}
      title={`Switch to ${nextTheme} theme`}
    >
      <span className="mv-theme-toggle__icon" aria-hidden="true">
        {theme === 'dark' ? '☀' : '☾'}
      </span>
      <span className="mv-theme-toggle__label">
        {theme === 'dark' ? 'Light' : 'Dark'}
      </span>
    </button>
  );
}
