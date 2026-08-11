import type { Root } from "hast";
import { visit } from "unist-util-visit";

export function rehypeRewriteImg() {
  return (tree: Root, file: any) => {
    const filePath: string = file.path ?? file.history?.[0] ?? "";
    const match = filePath.match(/src[/\\]content[/\\](posts|notes)[/\\](.+)\.\w+$/);
    if (!match) return;

    const [, collection, slug] = match;

    // HTML img elements (plain HTML in .md files)
    visit(tree, "element", (node: any) => {
      if (node.tagName !== "img") return;
      const src = (node.properties?.src as string) ?? "";
      if (src.startsWith("./")) {
        node.properties.src = `/images/${collection}/${slug}/${src.slice(2)}`;
      }
    });

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
