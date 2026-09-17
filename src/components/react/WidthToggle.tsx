import { useState, useEffect } from 'react';

const PRESETS = [
  { label: '标准', value: '56rem' },
  { label: '宽', value: '72rem' },
  { label: '全宽', value: '100rem' },
] as const;

const DEFAULT = '56rem';
const STORAGE_KEY = 'contentWidth';

export default function WidthToggle() {
  const [current, setCurrent] = useState<string>(DEFAULT);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && PRESETS.some((p) => p.value === stored)) setCurrent(stored);
  }, []);

  function select(value: string) {
    setCurrent(value);
    document.documentElement.style.setProperty('--content-width', value);
    localStorage.setItem(STORAGE_KEY, value);
  }

  return (
    <div
      class="hidden lg:flex fixed top-3 right-6 z-40 items-center gap-0.5 p-1 rounded-full bg-[var(--bg)] border border-[var(--border)] shadow-sm"
      role="group"
      aria-label="调整正文宽度"
    >
      {PRESETS.map((p) => (
        <button
          key={p.value}
          onClick={() => select(p.value)}
          class={`px-2.5 py-1 rounded-full text-xs transition-colors ${
            current === p.value
              ? 'bg-[var(--primary-light)] text-[var(--primary)] font-medium'
              : 'text-[var(--text-tertiary)] hover:text-[var(--text)] hover:bg-[var(--border-light)]'
          }`}
          aria-pressed={current === p.value}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
