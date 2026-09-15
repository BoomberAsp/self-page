import type { Root } from "hast";
import { visit } from "unist-util-visit";

export function rehypeRewriteImg() {
  return (tree: Root, file: any) => {
    const filePath: string = file.path ?? file.history?.[0] ?? "";
    const match = filePath.match(/src[/\\]content[/\\](posts|notes)[/\\](.+)\.\w+$/);
    if (!match) return;

    const [, collection, rawSlug] = match;
    // Windows 下 file.path 可能含反斜杠，统一为 URL 安全的正斜杠
    const slug = rawSlug.replace(/\\/g, "/");

    // HTML img elements (plain HTML in .md files, parsed into element nodes)
    visit(tree, "element", (node: any) => {
      if (node.tagName !== "img") return;
      const src = (node.properties?.src as string) ?? "";
      if (src.startsWith("./")) {
        node.properties.src = `/images/${collection}/${slug}/${src.slice(2)}`;
      }
    });

    // Raw HTML nodes (.md pipeline without rehype-raw: <img ...> stays as raw text)
    const rewriteRawHtml = (node: any) => {
      if (typeof node.value !== "string" || !node.value.includes("<img")) return;
      node.value = node.value.replace(
        /(<img[^>]*?\ssrc=["'])\.\/([^"']+)(["'])/gi,
        (_m: string, p1: string, p2: string, p3: string) =>
          `${p1}/images/${collection}/${slug}/${p2}${p3}`
      );
    };
    visit(tree, "raw", rewriteRawHtml);
    visit(tree, "html", rewriteRawHtml);

    // JSX img elements — block-level (standalone in .mdx files)
    visit(tree, "mdxJsxFlowElement", (node: any) => {
      if (node.name !== "img") return;
      for (const attr of node.attributes ?? []) {
        if (attr.name === "src" && String(attr.value ?? "").startsWith("./")) {
          attr.value = `/images/${collection}/${slug}/${String(attr.value).slice(2)}`;
        }
      }
    });

    // JSX img elements — inline (inside <a>/<p> in .mdx files)
    visit(tree, "mdxJsxTextElement", (node: any) => {
      if (node.name !== "img") return;
      for (const attr of node.attributes ?? []) {
        if (attr.name === "src" && String(attr.value ?? "").startsWith("./")) {
          attr.value = `/images/${collection}/${slug}/${String(attr.value).slice(2)}`;
        }
      }
    });
  };
}
