/**
 * 站内引用（xref）rehype 插件，注册顺序：
 * rehypeKatex → rehypeHeadingMathToc → rehypeXref → rehypeRewriteImg
 *
 * Pass A —— 定理锚点注入：
 *   段落首个 element 子节点为 <strong> 且文本匹配定理标签（Theorem 2.22 /
 *   Definition (Finite-Dimensional) / 定理 2.22 …）时，为 <p> 设 id=key
 *   与 data-xref-label，不加任何视觉样式（现有文章外观不变）。
 *
 * Pass B —— xref 链接解析：
 *   a[href^="xref:"] 查注册表改写为真实 URL：
 *   - xref:thm:2.22            → 定理条目（key 全局唯一）
 *   - xref:lecture-a#31-lemma  → 文章标题锚点（basename 匹配 + slug 校验）
 *   命中：href 改写、加 class xref-link、data-xref-key、title=文章标题，
 *         空链接文本自动填 label；
 *   未命中：console.warn 并解包为纯文本（不留死链）。
 */
import type { Root, Element } from "hast";
import { visit, SKIP } from "unist-util-visit";
import { visitParents } from "unist-util-visit-parents";
import { labelToKey, loadRegistry, type XrefRegistry } from "../lib/xref-registry";

/** 取元素纯文本；跳过 katex 子树（其内部文本是 MathML/annotation 的三份拼接） */
function plainText(node: Element): string {
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
      (cls.includes("katex") || cls.includes("katex-display"))
    ) {
      return; // 标签内公式不参与 key 判定
    }
    (n.children ?? []).forEach(walk);
  };
  (node.children ?? []).forEach(walk);
  return out.replace(/\s+/g, " ").trim();
}

function hasClass(node: any, name: string): boolean {
  const cls = node?.properties?.className;
  return Array.isArray(cls) && cls.includes(name);
}

/** 祖先中是否有 pre/code/a/.katex（这些子树内的 xref 链接不处理） */
function inSkipSubtree(parents: any[]): boolean {
  return parents.some(
    (p) =>
      p?.type === "element" &&
      (p.tagName === "pre" ||
        p.tagName === "code" ||
        p.tagName === "a" ||
        hasClass(p, "katex") ||
        hasClass(p, "katex-display"))
  );
}

function addClass(node: Element, name: string) {
  const cls = ((node.properties!.className as unknown) ?? []) as string[];
  if (!cls.includes(name)) cls.push(name);
  node.properties!.className = cls;
}

interface Resolved {
  url: string;
  anchor: string;
  label: string;
  articleTitle: string;
}

/** 解析 xref: 后的键；未命中返回 null */
function resolveKey(raw: string, registry: XrefRegistry): Resolved | null {
  const hashIdx = raw.indexOf("#");
  if (hashIdx !== -1) {
    // 标题锚点引用：basename（或完整 id）匹配文章 + slug 校验
    const base = raw.slice(0, hashIdx);
    const frag = raw.slice(hashIdx + 1);
    const article = Object.values(registry.articles).find(
      (a) => a.basename === base || a.url.endsWith(`/${base}`)
    );
    if (article && article.headings.includes(frag)) {
      return {
        url: article.url,
        anchor: frag,
        label: article.title,
        articleTitle: article.title,
      };
    }
    return null;
  }
  const entry = registry.entries[raw];
  if (!entry) return null;
  return {
    url: entry.url,
    anchor: entry.anchor,
    label: entry.label,
    articleTitle: entry.articleTitle,
  };
}

export function rehypeXref() {
  let registry: XrefRegistry | null = null;
  return (tree: Root, file: any) => {
    if (!registry) registry = loadRegistry();

    // ── Pass A：定理块锚点注入 ──
    visit(tree, "element", (node: Element) => {
      if (node.tagName !== "p") return;
      const first = (node.children ?? []).find((c: any) => c.type === "element");
      if (!first || (first as Element).tagName !== "strong") return;
      const text = plainText(first as Element);
      if (!text) return;
      const key = labelToKey(text);
      if (!key) return;
      node.properties = node.properties ?? {};
      if (!node.properties.id) node.properties.id = key;
      (node.properties as any).dataXrefLabel = text;
      addClass(node, "theorem-block");
    });

    // ── Pass B：xref 链接解析 ──
    visitParents(tree, "element", (node: Element, ancestors) => {
      if (node.tagName !== "a") return;
      const href = String((node.properties?.href as string) ?? "");
      if (!href.startsWith("xref:")) return;
      if (inSkipSubtree(ancestors)) return;

      const parent = ancestors[ancestors.length - 1];
      const raw = href.slice("xref:".length);
      const hit = resolveKey(raw, registry!);
      node.properties = node.properties ?? {};

      if (!hit) {
        const where = file?.history?.[0] ?? file?.path ?? "?";
        console.warn(`[xref] unresolved: ${raw} (in ${where})`);
        // 降级：解包为纯文本，不留死链；空文本时保留键名可见
        const children = (node.children ?? []) as any[];
        if (children.length === 0) {
          children.push({ type: "text", value: raw });
        }
        if (parent) {
          const index = (parent.children as any[]).indexOf(node);
          if (index !== -1) {
            (parent.children as any[]).splice(index, 1, ...children);
            return [SKIP, index + children.length - 1] as const;
          }
        }
        return;
      }

      node.properties.href = `${hit.url}#${hit.anchor}`;
      (node.properties as any).dataXrefKey = raw;
      node.properties.title = hit.articleTitle;
      addClass(node, "xref-link");
      if ((node.children ?? []).length === 0) {
        node.children = [{ type: "text", value: hit.label }];
      }
    });
  };
}
