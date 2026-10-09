import type { Root } from "mdast";
import { visit } from "unist-util-visit";

/**
 * micromark-extension-math（remark-math 底层）只把 `$$` 各自独占一行的写法
 * 解析为块级公式（math-flow）；单行 `$$x$$` 会走 math-text 规则变成
 * inlineMath，被 rehype-katex 按行内渲染。
 *
 * 本插件处理「inlineMath 节点在源码中独占一行且以 `$$` 开头」的情况：
 * 将其改写为块级 math 节点，并把所在段落从公式处拆分
 * （前文段落 + display 公式 + 后文段落），覆盖公式上一行紧贴文本、
 * 被 Markdown 合并进同一段落的场景。需注册在 remarkMath 之后。
 */

interface Node {
  type: string;
  value?: string;
  meta?: string | null;
  children?: Node[];
  position?: any;
  data?: any;
  [key: string]: any;
}

/** 把 inlineMath 改写为块级 math 节点（与多行 `$$` 块的产出保持一致） */
function toDisplayMath(child: Node): void {
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
}

/** 判断节点在源码中是否独占一行（所在行除它以外只有空白） */
function isOwnLine(child: Node, source: string): boolean {
  const start = child.position?.start.offset;
  const end = child.position?.end.offset;
  if (typeof start !== "number" || typeof end !== "number") return false;
  if (!source.slice(start, end).startsWith("$$")) return false;
  const lineStart = source.lastIndexOf("\n", start - 1) + 1;
  // 行首允许缩进与 blockquote 标记（> ），不允许其他文字（否则属于句中夹注）
  if (!/^[\s>]*$/.test(source.slice(lineStart, start))) return false;
  const nl = source.indexOf("\n", end);
  const lineEnd = nl === -1 ? source.length : nl;
  return source.slice(end, lineEnd).trim() === "";
}

/** 去掉段落片段首/尾的空白文本与硬换行，返回是否仍有内容 */
function trimSegment(seg: Node[]): boolean {
  while (seg.length > 0) {
    const first = seg[0];
    if (first.type === "break") { seg.shift(); continue; }
    if (first.type === "text") {
      first.value = first.value.replace(/^\s+/, "");
      if (first.value === "") { seg.shift(); continue; }
    }
    break;
  }
  while (seg.length > 0) {
    const last = seg[seg.length - 1];
    if (last.type === "break") { seg.pop(); continue; }
    if (last.type === "text") {
      last.value = last.value.replace(/\s+$/, "");
      if (last.value === "") { seg.pop(); continue; }
    }
    break;
  }
  return seg.length > 0;
}

export function remarkSingleLineDisplayMath() {
  return (tree: Root, file: any) => {
    const source = typeof file?.value === "string" ? file.value : "";
    if (!source) return;

    visit(tree, "paragraph", (node: Node, index?: number, parent?: Node) => {
      if (parent?.children == null || typeof index !== "number") return;

      const mathChildren = node.children!.filter(
        (c) => c.type === "inlineMath" && isOwnLine(c, source)
      );
      if (mathChildren.length === 0) return;

      const mathSet = new Set<Node>(mathChildren);
      mathChildren.forEach(toDisplayMath);

      // 以独占一行的公式为界，把段落子节点切成若干片段
      const segments: Node[][] = [[]];
      for (const child of node.children!) {
        if (mathSet.has(child)) {
          segments.push([child], []);
        } else {
          segments[segments.length - 1].push(child);
        }
      }

      const newNodes: Node[] = [];
      for (const seg of segments) {
        const isMathSeg = seg.length === 1 && seg[0].type === "math";
        if (!isMathSeg && !trimSegment(seg)) continue;
        if (isMathSeg) {
          newNodes.push(seg[0]);
        } else {
          newNodes.push({
            type: "paragraph",
            children: seg,
            position: {
              start: seg[0].position?.start,
              end: seg[seg.length - 1].position?.end,
            },
          });
        }
      }

      parent.children!.splice(index, 1, ...newNodes);
      return index + newNodes.length;
    });
  };
}
