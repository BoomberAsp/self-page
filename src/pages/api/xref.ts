/**
 * xref 悬浮卡片数据端点：GET /api/xref?key=thm:2.22
 * 返回渲染好的摘要 HTML（KaTeX 已展开），客户端直接 innerHTML 填充卡片。
 */
import type { APIRoute } from "astro";
import { loadRegistry, safeTruncate } from "../../lib/xref-registry";
import { titleHtml } from "../../lib/math-title";

const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "public, max-age=300",
};

export const GET: APIRoute = async ({ url }) => {
  const key = url.searchParams.get("key");
  if (!key) {
    return new Response(JSON.stringify({ error: "missing key" }), {
      status: 400,
      headers: JSON_HEADERS,
    });
  }

  const entry = loadRegistry().entries[key];
  if (!entry) {
    return new Response(JSON.stringify({ error: "unknown key", key }), {
      status: 404,
      headers: JSON_HEADERS,
    });
  }

  // 摘要去掉开头的 **标签**：（卡片已单独展示 label），再截断并渲染公式
  const body = entry.excerptRaw.replace(/^\*\*[^*]+\*\*\s*[:：]?\s*/, "");
  const excerptHtml = titleHtml(safeTruncate(body));

  return new Response(
    JSON.stringify({
      url: `${entry.url}#${entry.anchor}`,
      label: entry.label,
      articleTitle: entry.articleTitle,
      excerptHtml,
    }),
    { status: 200, headers: JSON_HEADERS }
  );
};
