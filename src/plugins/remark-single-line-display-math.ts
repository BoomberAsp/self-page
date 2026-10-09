import type { Root } from "mdast";
import { visit } from "unist-util-visit";

/**
 * micromark-extension-math（remark-math 底层）只把 `$$` 各自独占一行的写法
 * 解析为块级公式（math-flow）；单行 `$$x$$` 会走 math-text 规则变成
 * inlineMath，被 rehype-katex 按行内渲染。
 *
 * 本插件处理「段落中仅有一个 inlineMath 节点，且原文以 `$$` 开头」的情况，
 * 将其改写为块级 math 节点（与多行 `$$` 块的产出保持一致），使单行 `$$x$$`
 * 独占一段时按 displayMode 渲染。需注册在 remarkMath 之后。
 */
export function remarkSingleLineDisplayMath() {
  return (tree: Root, file: any) => {
    const source = typeof file?.value === "string" ? file.value : "";
    if (!source) return;

    visit(tree, "paragraph", (node: any) => {
      if (node.children.length !== 1) return;
      const child = node.children[0];
      if (child.type !== "inlineMath") return;

      // 通过 position 回溯原文，区分 `$$x$$` 与 `$x$`
      const start = child.position?.start.offset;
      const end = child.position?.end.offset;
      if (start == null || end == null) return;
      if (!source.slice(start, end).startsWith("$$")) return;

      child.type = "math";
      child.meta = null;
      // 解析阶段已写死 math-inline 的 className，需同步改为 math-display，
      // rehype-katex 依据它决定 displayMode
      const cls = child.data?.hProperties?.className;
      if (Array.isArray(cls)) {
        child.data.hProperties.className = cls.map((c: string) =>
          c === "math-inline" ? "math-display" : c
        );
      }
    });
  };
}
