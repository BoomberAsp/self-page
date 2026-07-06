import { useState, useEffect, useRef, useCallback } from 'react';
import Fuse from 'fuse.js';
import { Search, X } from 'lucide-react';

interface PostIndex {
  id: string;
  title: string;
  summary: string;
  tags: string[];
  date: string;
}

export default function SearchModal() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PostIndex[]>([]);
  const [index, setIndex] = useState<PostIndex[] | null>(null);
  const [fuse, setFuse] = useState<Fuse<PostIndex> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch('/search.json')
      .then((res) => res.json())
      .then((data: PostIndex[]) => {
        setIndex(data);
        setFuse(new Fuse(data, {
          keys: ['title', 'summary', 'tags'],
          threshold: 0.3,
          includeScore: true,
        }));
      });
  }, []);

  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden';
      inputRef.current?.focus();
    } else {
      document.body.style.overflow = '';
      setQuery('');
      setResults([]);
    }
    return () => { document.body.style.overflow = ''; };
  }, [open]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false);
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    function onSearchOpen() { setOpen(true); }
    window.addEventListener('keydown', onKey);
    window.addEventListener('search:open', onSearchOpen);
    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('search:open', onSearchOpen);
    };
  }, []);

  const search = useCallback(
    (q: string) => {
      setQuery(q);
      if (!fuse || q.trim().length === 0) {
        setResults(index?.slice(0, 8) ?? []);
        return;
      }
      const found = fuse.search(q.trim()).slice(0, 10);
      setResults(found.map((r) => r.item));
    },
    [fuse, index]
  );

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        class="flex items-center gap-2 w-full px-3 py-1.5 text-sm text-[var(--text-tertiary)] hover:text-[var(--text)] transition-colors rounded-lg bg-[var(--border-light)] hover:bg-[var(--border)]"
        aria-label="搜索 (Ctrl+K)"
      >
        <Search size={15} />
        <span class="flex-1 text-left">搜索</span>
        <kbd class="text-[0.65rem] opacity-40 tracking-wide">Ctrl+K</kbd>
      </button>

      {open && (
        <div
          class="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
          ref={modalRef}
          onClick={(e) => { if (e.target === modalRef.current) setOpen(false); }}
        >
          <div class="bg-[var(--bg)] border border-[var(--border)] rounded-xl shadow-lg w-full max-w-xl mx-4 overflow-hidden">
            <div class="flex items-center gap-2 px-4 py-3 border-b border-[var(--border-light)]">
              <Search size={17} class="text-[var(--text-tertiary)] shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onInput={(e) => search((e.target as HTMLInputElement).value)}
                placeholder="搜索文章..."
                class="flex-1 bg-transparent text-[var(--text)] outline-none text-base placeholder:text-[var(--text-tertiary)]"
              />
              <button
                onClick={() => setOpen(false)}
                class="p-1 rounded-md hover:bg-[var(--border-light)] text-[var(--text-tertiary)] shrink-0"
              >
                <X size={16} />
              </button>
            </div>

            <div class="max-h-80 overflow-y-auto p-2">
              {results.length === 0 ? (
                <p class="text-center text-sm text-[var(--text-tertiary)] py-8">
                  {query ? '无结果' : '输入关键词搜索文章'}
                </p>
              ) : (
                results.map((post) => (
                  <a
                    key={post.id}
                    href={`/posts/${post.id}`}
                    onClick={() => setOpen(false)}
                    class="flex flex-col px-3 py-2.5 rounded-lg hover:bg-[var(--border-light)] transition-colors no-underline"
                  >
                    <span class="text-sm font-medium text-[var(--heading)]">{post.title}</span>
                    {post.summary && (
                      <span class="text-xs text-[var(--text-tertiary)] mt-0.5 line-clamp-1">{post.summary}</span>
                    )}
                    <span class="flex gap-1.5 mt-1.5">
                      {post.tags.map((t) => (
                        <span class="text-[0.65rem] text-[var(--primary)] bg-[var(--primary-light)] px-1.5 py-0.5 rounded-full">
                          {t}
                        </span>
                      ))}
                    </span>
                  </a>
                ))
              )}
            </div>

            <div class="flex items-center gap-3 px-4 py-2 border-t border-[var(--border-light)] text-[0.7rem] text-[var(--text-tertiary)]">
              <span><kbd class="px-1 py-0.5 rounded bg-[var(--border-light)]">ESC</kbd> 关闭</span>
              <span><kbd class="px-1 py-0.5 rounded bg-[var(--border-light)]">Ctrl+K</kbd> 切换</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}