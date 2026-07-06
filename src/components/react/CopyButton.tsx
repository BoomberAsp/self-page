import { useEffect, useRef } from 'react';

export default function CopyButton() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = ref.current;
    if (!container) return;

    const pres = container.querySelectorAll('pre');
    pres.forEach((pre) => {
      if (pre.parentElement?.classList.contains('code-block-wrapper')) return;

      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';
      pre.parentNode!.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);

      const btn = document.createElement('button');
      btn.className = 'copy-btn';
      btn.textContent = '复制';

      btn.addEventListener('click', async () => {
        const code = pre.querySelector('code')?.textContent ?? pre.textContent ?? '';
        try {
          await navigator.clipboard.writeText(code);
          btn.textContent = '已复制';
          setTimeout(() => { btn.textContent = '复制'; }, 2000);
        } catch {
          btn.textContent = '失败';
          setTimeout(() => { btn.textContent = '复制'; }, 2000);
        }
      });

      wrapper.appendChild(btn);
    });
  }, []);

  return <div ref={ref} class="hidden" aria-hidden="true" />;
}