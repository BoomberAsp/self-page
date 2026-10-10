/**
 * 共享 slug 工具：rehype-heading-math-toc（运行时）与 xref-registry 扫描器
 * （构建时）必须使用完全一致的算法，否则 xref 引用标题锚点时会校验失败。
 */

/**
 * 生成 URL 安全且唯一的 slug（保留中日韩文字，剔除 LaTeX 命令与标点）。
 * 有状态：同一文件内重名自动追加 -N 后缀，与 GitHub/Astro 行为一致。
 */
export function makeSlugger() {
  const used = new Map<string, number>();
  return (text: string): string => {
    const base =
      text
        .toLowerCase()
        .replace(/\$/g, "")
        .replace(/\\[a-zA-Z]+/g, " ")
        .replace(/[^\p{L}\p{N}\s_-]/gu, "")
        .trim()
        .replace(/\s+/g, "-") || "section";
    const n = used.get(base) ?? 0;
    used.set(base, n + 1);
    return n === 0 ? base : `${base}-${n}`;
  };
}

/** 单次 slug 化（无去重状态），用于定理括号名等一次性场景 */
export function slugify(text: string): string {
  return makeSlugger()(text);
}

// 公式占位哨兵：Unicode 私用区字符（U+E000/U+E001），正常 MDX 文本不会出现。
// 用 charCode 构造以避免源码中出现不可见字符。
const SENTINEL_OPEN = String.fromCharCode(0xe000);
const SENTINEL_CLOSE = String.fromCharCode(0xe001);
const SENTINEL_RE = new RegExp(SENTINEL_OPEN + "(\\d+)" + SENTINEL_CLOSE, "g");

/**
 * 将 MDX 标题行原文规整为与运行时 headingText() 等价的文本：
 * 剥离行内 Markdown 修饰（**粗体**、`代码`、[文本](链接) → 文本），
 * 保留 $…$ 公式定界符，供 makeSlugger 复现标题 slug。
 */
export function normalizeHeadingText(raw: string): string {
  // 先摘出 $…$ / $$…$$ 公式段（哨兵占位保护），避免公式内的 * _ ` [ 被
  // Markdown 剥离规则误伤（如 $v_1, \dots, v_n$ 中的下标）
  const mathSpans: string[] = [];
  let text = raw.replace(/\$\$[^$]+\$\$|\$[^$\n]+\$/g, (m) => {
    mathSpans.push(m);
    return SENTINEL_OPEN + (mathSpans.length - 1) + SENTINEL_CLOSE;
  });
  text = text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // [text](url) → text
    .replace(/(\*\*|__)(.*?)\1/g, "$2") // **bold** / __bold__
    .replace(/(\*|_)(.*?)\1/g, "$2") // *em* / _em_
    .replace(/`([^`]*)`/g, "$1") // `code`
    .replace(SENTINEL_RE, (_, i) => mathSpans[Number(i)]) // 还原公式
    .replace(/\s+/g, " ")
    .trim();
  return text;
}
