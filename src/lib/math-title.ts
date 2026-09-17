import katex from 'katex';

// 与 remark-math 默认行内/块定界符保持一致；标题内一律按行内渲染避免破坏布局
const MATH_RE = /\$\$[^$]+\$\$|\$[^$\n]+\$|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]/g;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** 将含 LaTeX 定界符的标题转为安全 HTML：数学段交 KaTeX，其余转义。 */
export function titleHtml(title: string): string {
  let html = '';
  let last = 0;
  for (const m of title.matchAll(MATH_RE)) {
    const i = m.index ?? 0;
    html += escapeHtml(title.slice(last, i));
    const raw = m[0];
    const expr = raw.startsWith('$') ? raw.replace(/^\$+/, '').replace(/\$+$/, '') : raw.slice(2, -2);
    html += katex.renderToString(expr, { throwOnError: false, displayMode: false });
    last = i + raw.length;
  }
  html += escapeHtml(title.slice(last));
  return html;
}
