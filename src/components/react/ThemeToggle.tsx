import { useState, useEffect } from 'react';
import { Sun, Moon } from 'lucide-react';

export default function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (typeof window === 'undefined') return false;
    const stored = localStorage.getItem('theme');
    return stored === 'dark' || (!stored && window.matchMedia('(prefers-color-scheme: dark)').matches);
  });

  useEffect(() => {
    const stored = localStorage.getItem('theme');
    const prefers = window.matchMedia('(prefers-color-scheme: dark)').matches;
    setDark(stored === 'dark' || (!stored && prefers));
  }, []);

  function toggle() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
  }

  return (
    <button
      onClick={toggle}
      class="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-sm text-[var(--text-tertiary)] hover:bg-[var(--border-light)] hover:text-[var(--text)] transition-colors"
      aria-label="切换主题"
    >
      {dark ? <Sun size={16} /> : <Moon size={16} />}
      <span>{dark ? '亮色模式' : '暗色模式'}</span>
    </button>
  );
}