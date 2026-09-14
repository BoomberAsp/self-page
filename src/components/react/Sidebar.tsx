import { useState } from 'react';

interface Section {
  label: string;
  defaultOpen?: boolean;
  items: { href: string; label: string }[];
}

interface SidebarProps {
  currentPath: string;
  columns?: { href: string; label: string }[];
}

export default function Sidebar({ currentPath, columns = [] }: SidebarProps) {
  const sections: Section[] = [
    {
      label: '导航',
      defaultOpen: true,
      items: [
        { href: '/', label: '首页' },
        { href: '/notes', label: '笔记' },
        { href: '/posts', label: '博文' },
      ],
    },
    ...(columns.length > 0
      ? [
          {
            label: '栏目',
            defaultOpen: true,
            items: [
              { href: '/columns', label: '全部栏目' },
              ...columns,
            ],
          },
        ]
      : []),
    {
      label: '其他',
      defaultOpen: true,
      items: [
        { href: '/projects', label: '项目' },
        { href: '/download', label: '下载' },
      ],
    },
  ];

  const [open, setOpen] = useState<Record<string, boolean>>(
    Object.fromEntries(sections.map((s) => [s.label, s.defaultOpen ?? true]))
  );

  return (
    <nav>
      {sections.map((sec) => (
        <div key={sec.label} style={{ marginBottom: '1rem' }}>
          <button
            onClick={() => setOpen((prev) => ({ ...prev, [sec.label]: !prev[sec.label] }))}
            class="sidebar-section-header"
            type="button"
          >
            {sec.label}
            <svg
              class={`chevron ${open[sec.label] ? 'open' : ''}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
          {open[sec.label] && (
            <div style={{ marginLeft: '0.375rem', marginTop: '0.125rem' }}>
              {sec.items.map((item) => {
                const isActive =
                  currentPath === item.href ||
                  (item.href !== '/' && currentPath.startsWith(item.href));
                return (
                  <a
                    key={item.href}
                    href={item.href}
                    class={`sidebar-nav-item ${isActive ? 'active' : ''}`}
                  >
                    {item.label}
                  </a>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </nav>
  );
}