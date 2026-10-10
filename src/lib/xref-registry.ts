/**
 * 站内引用（xref）注册表：单一数据源。
 *
 * - 构建期：vite-xref-registry 插件调用 scanContent() 生成 .xref-registry.json
 * - 构建期：rehype-xref 插件调用 loadRegistry() + labelToKey() 注入锚点/解析链接
 * - 运行时：/api/xref 调用 loadRegistry() + safeTruncate() 返回悬浮卡片摘要
 *
 * labelToKey 必须由扫描器与 rehype 插件共用，保证两侧生成一致的 key。
 */
import fs from "node:fs";
import path from "node:path";
import { makeSlugger, normalizeHeadingText, slugify } from "./slug";

export interface XrefEntry {
  key: string;
  /** 展示用标签，如 "Theorem 2.22" / "Definition (Finite-Dimensional)" */
  label: string;
  /** 文章 URL，如 /posts/advanced-linear-algebra/lecture-3 */
  url: string;
  /** 文章内锚点（定理块 id） */
  anchor: string;
  /** content collection 条目 id，如 advanced-linear-algebra/lecture-3 */
  articleId: string;
  articleTitle: string;
  /** 定理所在段落原文（含 $…$ 公式与 **标签**），用于摘要渲染 */
  excerptRaw: string;
}

export interface XrefArticle {
  url: string;
  title: string;
  /** id 的最后一段，用于 xref:basename#heading 匹配 */
  basename: string;
  /** 文件内全部标题 slug（按出现顺序，含 -N 去重后缀） */
  headings: string[];
}

export interface XrefRegistry {
  entries: Record<string, XrefEntry>;
  articles: Record<string, XrefArticle>;
}

export const REGISTRY_FILENAME = ".xref-registry.json";

const THEOREM_WORDS =
  "Theorem|Lemma|Definition|Proposition|Corollary|定理|引理|定义|命题|推论";

/** 匹配段落开头的加粗定理标签，捕获 **…** 内的完整标签文本 */
const THEOREM_LINE_RE = new RegExp(
  `^\\*\\*((?:${THEOREM_WORDS})\\s*[\\d.]*\\s*(?:\\([^)]*\\))?)\\*\\*`
);

/** 解析标签文本：类型词 + 可选编号 + 可选括号名 */
const LABEL_RE = new RegExp(
  `^(${THEOREM_WORDS})\\s*([\\d.]+)?\\s*(?:\\(([^)]*)\\))?$`,
  "i"
);

const NAMESPACE: Record<string, string> = {
  theorem: "thm",
  定理: "thm",
  lemma: "lem",
  引理: "lem",
  definition: "def",
  定义: "def",
  proposition: "prop",
  命题: "prop",
  corollary: "cor",
  推论: "cor",
};

/**
 * 标签文本 → 注册 key。
 * "Theorem 2.22" → thm:2.22；"Definition (Finite-Dimensional)" →
 * def:finite-dimensional；无编号且无括号名 → null（不注册）。
 */
export function labelToKey(labelText: string): string | null {
  const m = LABEL_RE.exec(labelText.trim());
  if (!m) return null;
  const ns = NAMESPACE[m[1].toLowerCase()] ?? NAMESPACE[m[1]];
  if (!ns) return null;
  const num = m[2]?.replace(/\.+$/, "");
  if (num) return `${ns}:${num}`;
  const name = m[3]?.trim();
  if (name) return `${ns}:${slugify(name)}`;
  return null;
}

function walk(dir: string, out: string[] = []): string[] {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (/\.(mdx?|md)$/.test(ent.name)) out.push(p);
  }
  return out;
}

function extractFrontmatter(lines: string[]): Record<string, string> {
  const fm: Record<string, string> = {};
  if (!/^---\s*$/.test(lines[0] ?? "")) return fm;
  for (let i = 1; i < lines.length; i++) {
    if (/^---\s*$/.test(lines[i])) break;
    const m = /^([A-Za-z_][\w-]*):\s*(.*)$/.exec(lines[i]);
    if (m) fm[m[1]] = m[2].trim().replace(/^["']|["']$/g, "");
  }
  return fm;
}

/** 扫描 src/content/{posts,notes} 全部文章，生成注册表 */
export function scanContent(rootDir: string): XrefRegistry {
  const registry: XrefRegistry = { entries: {}, articles: {} };
  const contentDir = path.join(rootDir, "src", "content");

  for (const collection of ["posts", "notes"] as const) {
    const base = path.join(contentDir, collection);
    if (!fs.existsSync(base)) continue;

    for (const file of walk(base).sort()) {
      const rel = path.relative(base, file).split(path.sep).join("/");
      const id = rel.replace(/\.(mdx?|md)$/, "");
      const raw = fs.readFileSync(file, "utf8");
      const lines = raw.split(/\r?\n/);
      const fm = extractFrontmatter(lines);
      if (fm.draft === "true") continue;

      const url = `/${collection}/${id}`;
      const slug = makeSlugger();
      const headings: string[] = [];
      let inCode = false;
      let inFrontmatter = /^---\s*$/.test(lines[0] ?? "");

      for (let i = inFrontmatter ? 1 : 0; i < lines.length; i++) {
        const line = lines[i];
        if (inFrontmatter) {
          if (/^---\s*$/.test(line)) inFrontmatter = false;
          continue;
        }
        if (/^\s*(```|~~~)/.test(line)) {
          inCode = !inCode;
          continue;
        }
        if (inCode) continue;

        // 标题行：复现运行时 headingText + slug
        const h = /^(#{1,6})\s+(.+)$/.exec(line);
        if (h) {
          headings.push(slug(normalizeHeadingText(h[2])));
          continue;
        }

        // 定理标签行
        const t = THEOREM_LINE_RE.exec(line);
        if (!t) continue;
        const label = t[1].trim().replace(/\s+/g, " ");
        const key = labelToKey(label);
        if (!key) continue;
        // 摘录 = 标签所在段落原文（到空行为止）
        const excerptLines: string[] = [line];
        for (let j = i + 1; j < lines.length; j++) {
          if (/^\s*$/.test(lines[j])) break;
          excerptLines.push(lines[j]);
        }
        if (registry.entries[key]) {
          console.warn(
            `[xref] duplicate key "${key}" in ${rel} (kept: ${registry.entries[key].articleId})`
          );
          continue;
        }
        registry.entries[key] = {
          key,
          label,
          url,
          anchor: key,
          articleId: id,
          articleTitle: fm.title ?? id,
          excerptRaw: excerptLines.join("\n"),
        };
      }

      registry.articles[id] = {
        url,
        title: fm.title ?? id,
        basename: id.split("/").pop() ?? id,
        headings,
      };
    }
  }

  return registry;
}

/**
 * 截断摘要，避免切在 $…$ 公式中间（否则 titleHtml 渲染出残缺公式）。
 * 截断点前 $ 数量为奇数说明落在公式内，回退到该 $ 之前。
 */
export function safeTruncate(raw: string, max = 160): string {
  const flat = raw.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  let cut = flat.slice(0, max);
  const dollars = [...cut.matchAll(/(?<!\\)\$/g)];
  if (dollars.length % 2 === 1) {
    cut = cut.slice(0, dollars[dollars.length - 1].index);
  }
  return cut.trimEnd().replace(/[:：,，;；、\s]+$/, "") + "…";
}

let registryCache: XrefRegistry | null = null;

/** 读取构建期生成的 .xref-registry.json（内存缓存；缺失时返回空表） */
export function loadRegistry(rootDir = process.cwd()): XrefRegistry {
  if (registryCache) return registryCache;
  const file = path.join(rootDir, REGISTRY_FILENAME);
  try {
    registryCache = JSON.parse(fs.readFileSync(file, "utf8")) as XrefRegistry;
  } catch {
    console.warn(`[xref] registry not found at ${file}, xrefs disabled`);
    registryCache = { entries: {}, articles: {} };
  }
  return registryCache;
}
