import type { Element, Root } from "hast";
import { visit } from "unist-util-visit";

export function rehypeRewriteImg() {
  return (tree: Root, file: any) => {
    const filePath: string = file.path ?? file.history?.[0] ?? "";
    const match = filePath.match(/src[/\\]content[/\\](posts|notes)[/\\](.+)\.\w+$/);
    if (!match) return;

    const [, collection, slug] = match;

    visit(tree, "element", (node: Element) => {
      if (node.tagName !== "img") return;
      const src = (node.properties?.src as string) ?? "";
      if (!src.startsWith("./")) return;

      node.properties!.src = `/images/${collection}/${slug}/${src.slice(2)}`;
    });
  };
}
