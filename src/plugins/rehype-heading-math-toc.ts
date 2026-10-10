import type { Root, Element } from "hast";
import { visit } from "unist-util-visit";
import { makeSlugger } from "../lib/slug";

/**
 * Astro 内置的 rehypeHeadingIds 在所有用户 rehype 插件之后运行，且会拼接
 * 标题元素内的全部 text 节点。rehype-katex 先行运行后，标题里的公式已变成
 * KaTeX DOM（MathML 文本 + annotation 源码 + 视觉文本三份），导致 headings
 * 的 text 是乱码，TOC 无法渲染公式。
 *
 * 本插件注册在 rehypeKatex 之后：
 * 1. 从标题内 KaTeX 子树的 annotation[encoding=application/x-tex] 反提取
 *    LaTeX 源码，生成带 $ 定界符的干净标题文本；
 * 2. 自行生成干净 slug 并写入 properties.id（Astro 收集器尊重已有 id，
 *    正文标题锚点与 TOC href 保持一致）；
 * 3. 将 [{depth, slug, text}] 存入 file.data.astro.frontmatter.__tocHeadings，
 *    模板经 render().remarkPluginFrontmatter 读取，再用 titleHtml() 渲染。
 */

export interface TocHeading {
  depth: number;
  slug: string;
  text: string;
}

/** 从 katex 子树中提取 LaTeX 源码（annotation 元素文本） */
function katexToTeX(node: Element): string | null {
  let tex: string | null = null;
  visit(node, "element", (el: any) => {
    if (tex !== null || el.tagName !== "annotation") return;
    tex = (el.children ?? [])
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.value)
      .join("");
  });
  return tex;
}

/** 标题转干净文本：KaTeX 子树还原为 $tex$，其余节点取纯文本 */
function headingText(node: Element): string {
  let out = "";
  const walk = (n: any) => {
    if (n.type === "text") {
      out += n.value;
      return;
    }
    if (n.type !== "element") return;
    const cls = (n.properties?.className as unknown) ?? [];
    if (
      Array.isArray(cls) &&
      (cls.includes("katex-display") || cls.includes("katex"))
    ) {
      const tex = katexToTeX(n);
      if (tex) out += `$${tex}$`;
      return;
    }
    (n.children ?? []).forEach(walk);
  };
  (node.children ?? []).forEach(walk);
  return out.replace(/\s+/g, " ").trim();
}

export function rehypeHeadingMathToc() {
  return (tree: Root, file: any) => {
    const toc: TocHeading[] = [];
    const slug = makeSlugger();
    visit(tree, "element", (node: Element) => {
      const m = /^h([1-6])$/.exec(node.tagName);
      if (!m) return;
      const text = headingText(node);
      const id = slug(text);
      node.properties = node.properties ?? {};
      node.properties.id = id;
      toc.push({ depth: Number(m[1]), slug: id, text });
    });
    const fm = file.data?.astro?.frontmatter;
    if (fm && typeof fm === "object") {
      fm.__tocHeadings = toc;
    }
  };
}
