import { useState } from 'react';
import { Menu, Search, X } from 'lucide-react';

const links = [
  { href: '/', label: '首页' },
  { href: '/posts', label: '博文' },
  { href: '/projects', label: '项目' },
  { href: '/download', label: '下载' },
];

export default function MobileNav() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        class="lg:hidden fixed top-3 left-3 z-50 p-2 rounded-full bg-[var(--bg)] border border-[var(--border)] shadow-sm active:scale-95 transition-transform"
        aria-label="菜单"
      >
        {open ? <X size={18} /> : <Menu size={18} />}
      </button>

      {open && (
        <div class="lg:hidden fixed inset-0 z-40 bg-[var(--bg)] flex flex-col pt-20 px-5">
          <button
            onClick={() => { window.dispatchEvent(new CustomEvent('search:open')); setOpen(false); }}
            class="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm text-[var(--text-tertiary)] bg-[var(--border-light)] hover:text-[var(--text)] transition-colors mb-2"
          >
            <Search size={15} />
            搜索文章...
          </button>
          <nav class="flex flex-col gap-1">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                class="text-base py-2.5 px-4 rounded-lg text-[var(--text-secondary)] hover:bg-[var(--border-light)] hover:text-[var(--text)] transition-colors"
                style={{ textDecoration: 'none' }}
              >
                {link.label}
              </a>
            ))}
          </nav>
          <div class="mt-auto pb-10 text-center">
            <a href="/rss.xml" class="text-sm text-[var(--text-tertiary)] hover:text-[var(--text)] transition-colors" style={{ textDecoration: 'none' }}>RSS</a>
          </div>
        </div>
      )}
    </>
  );
}
