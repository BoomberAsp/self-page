/**
 * Vite 插件：构建启动时扫描 src/content 生成 .xref-registry.json（项目根）。
 * dev 模式每次启动重生成；build 模式每次构建重生成。
 * rehype-xref（构建期）与 /api/xref（运行时）读取同一份 JSON，单一数据源。
 *
 * 注意：dev 模式下修改文章后需重启 dev server 才能刷新注册表。
 */
import fs from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";
import { scanContent, REGISTRY_FILENAME } from "../lib/xref-registry";

export function viteXrefRegistry(): Plugin {
  let projectRoot = process.cwd();
  return {
    name: "vite-xref-registry",
    configResolved(config) {
      projectRoot = config.root || projectRoot;
    },
    buildStart() {
      const root = projectRoot;
      const registry = scanContent(root);
      const file = path.join(root, REGISTRY_FILENAME);
      fs.writeFileSync(file, JSON.stringify(registry, null, 2));
      const n = Object.keys(registry.entries).length;
      const a = Object.keys(registry.articles).length;
      console.log(`[xref] registry written: ${n} entries, ${a} articles`);
    },
  };
}
