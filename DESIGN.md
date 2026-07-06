# 个人网站详细设计规划

> 域名：oneweblog.cn | 部署：腾讯云轻量服务器 2C4G（已运行 QQ 机器人 + Streamlit 应用，可用内存余量 ~200MB）

---

## 1. 架构总览

### 核心原则

**静态优先，动态按需。构建时完成 90% 的工作，运行时只处理 PDF 生成和自动构建。**

```
┌──────────────────────────────────────────────────────────────────┐
│                    腾讯云轻量服务器 (2C4G)                         │
│                                                                  │
│   nginx (:80/:443)                                               │
│       │                                                          │
│       ├── /                     → 静态文件 (构建时生成)            │
│       ├── /posts/*              → 静态文件                        │
│       ├── /projects             → 静态文件                        │
│       ├── /download             → 静态文件                        │
│       ├── /_astro/*             → 静态资源 (JS/CSS, 长缓存)       │
│       ├── /downloads/pdf/*      → 静态文件 (PDF 缓存, 首次命中后) │
│       │                                                          │
│       └── /api/*                → proxy_pass 127.0.0.1:4321      │
│            │                         │                            │
│            ├── /api/pdf/[slug]        Astro Hybrid SSR           │
│            └── /api/rebuild           (PM2 守护, Node.js)        │
│                                                                  │
│   已有服务:                                                       │
│   · QQ 机器人 (进程1)                                             │
│   · Streamlit (进程2)                                             │
│   · 本网站 Node.js (进程3) ← 新增, ~120MB                        │
└──────────────────────────────────────────────────────────────────┘
```

### 静态 vs 动态划分

```
静态生成 (构建时, prerender)       SSR/API (请求时, prerender = false)
────────────────────────────      ──────────────────────────────────
/                                  /api/pdf/[slug]     按需生成 PDF
/posts                             /api/rebuild         接收 webhook
/posts/[slug]
/projects
/download
/download/md/[slug].md
/tags/[tag]
/search.json
/feed.xml
/rss.xml
/404.html
```

**划分逻辑**：所有页面内容在构建时确定 → 静态。PDF 按需生成避免 build 膨胀 → 动态。webhook 需要执行 shell → 动态。

### 为什么是 Hybrid 而不是纯 SSR

- 纯 SSR 下每次访问 `/posts/some-article` 都要服务端渲染，100 人看同一篇文章就是 100 次渲染，纯浪费 CPU
- Hybrid 下文章页 build 时就生成了 HTML，100 人访问 = nginx 直接返回 100 个静态文件
- SSR 仅用于两个 API 端点，占总请求量 < 1%

---

## 2. 技术选型

| 层 | 技术 | 选型理由 |
|----|------|---------|
| 框架 | **Astro 5 (Hybrid 模式)** | 静态页面 + 按需 SSR，两全其美 |
| 服务端适配器 | **@astrojs/node** | 将 Astro 运行在 Node.js 上 |
| UI 组件 | **React 19** | 交互岛屿，非静态部分 |
| 样式 | **Tailwind CSS 4** | 原子化 CSS，体积小 |
| 内容 | **MDX** | Markdown + 可嵌入 React 组件 |
| 图标 | **Lucide React** | tree-shakeable |
| PDF 生成 | **Puppeteer (服务端按需)** | 真渲染，排版质量高，首次生成后缓存为静态文件 |
| PDF 缓存 | **文件系统 (dist/ 目录)** | 零依赖，nginx 后续直接 serve |
| 搜索 | **客户端 Fuse.js** | 构建时生成 JSON 索引 |
| 语法高亮 | **Shiki** (Astro 内置) | 构建时完成 |
| 进程管理 | **PM2** | 守护 Node 进程，自动重启 |
| Webhook | **express 中间件** 或 Astro API 端点 | 接收 GitHub/Gitee push 事件 |

### 不选的

- ❌ 纯 SSR：浪费 CPU，服务端重复渲染不变的内容
- ❌ 纯 SSG：每次改文章要本地 build + rsync，无法远程发布
- ❌ 客户端 PDF：截图方案对代码块和分页处理差
- ❌ Docker：服务器资源不宽裕，直接跑更可控

---

## 3. 站点路由

```
/                             首页 — 个人简介 + 导航卡片 + 最近文章
/posts                        博文列表 — 分页 + 标签筛选 + 搜索
/posts/[slug]                 文章详情 — 正文 + TOC + 下载按钮
/projects                     项目展示 — 卡片网格 + 外链
/download                     下载中心 — 按分类浏览
/downloads/pdf/[slug].pdf     PDF 文件 (缓存 → 静态)
/downloads/md/[slug].md       Markdown 源文件 (构建时复制)
/tags/[tag]                   标签聚合页
/search.json                  搜索索引 (构建时)
/feed.xml / /rss.xml          RSS Feed (构建时)
/api/pdf/[slug]               PDF 生成端点 (prerender = false)
/api/rebuild                  自动构建 webhook (prerender = false)
/404.html                     自定义 404
```

---

## 4. 组件树

```
src/
├── pages/                          # Astro 页面
│   ├── index.astro                 # 首页 (prerender)
│   ├── posts/
│   │   ├── index.astro             # 文章列表 (prerender)
│   │   └── [slug].astro            # 文章详情 (prerender)
│   ├── projects/
│   │   └── index.astro             # 项目展示 (prerender)
│   ├── tags/
│   │   └── [tag].astro             # 标签聚合 (prerender)
│   ├── download/
│   │   └── index.astro             # 下载中心 (prerender)
│   ├── search.json.ts              # 搜索索引生成
│   ├── feed.xml.ts                 # RSS
│   ├── rss.xml.ts
│   ├── 404.astro
│   └── api/
│       ├── pdf/[slug].ts           # PDF 按需生成 (prerender = false)
│       └── rebuild.ts              # Webhook 端点 (prerender = false)
│
├── components/react/               # React 岛屿 (客户端交互)
│   ├── Navbar.tsx                  # 左侧导航栏
│   ├── MobileNav.tsx               # 移动端菜单
│   ├── SearchBar.tsx               # 搜索 (Fuse.js)
│   ├── TagFilter.tsx               # 标签筛选
│   ├── TableOfContents.tsx         # 文章目录 (滚动高亮)
│   ├── ThemeToggle.tsx             # 明暗切换
│   ├── BackToTop.tsx               # 返回顶部
│   └── PostCard.tsx                # 文章卡片
│
├── components/astro/               # Astro 组件 (构建时)
│   ├── BaseLayout.astro            # HTML shell + SEO
│   ├── PostLayout.astro            # 文章布局
│   ├── ArticleContent.astro        # MDX 渲染
│   ├── SEO.astro                   # Meta tags
│   ├── Hero.astro                  # 首页头部
│   ├── PostCard.astro              # 文章卡片 (静态版)
│   ├── ProjectCard.astro           # 项目卡片
│   ├── DownloadLinks.astro         # 下载链接组
│   └── Footer.astro                # 页脚 + 备案号
│
├── content/
│   ├── posts/*.mdx                 # 博文
│   └── config.ts                   # 集合 schema
│
├── data/
│   ├── projects.json               # 项目数据
│   └── site.json                   # 站点元信息
│
├── lib/
│   ├── pdf.ts                      # PDF 生成 + 缓存逻辑
│   ├── copy-source-files.ts        # 构建时复制 .mdx → public
│   └── utils.ts                    # 日期、阅读时间等
│
├── styles/
│   └── global.css                  # Tailwind + 自定义变量
│
└── public/
    ├── avatar.webp
    ├── favicon.svg
    └── downloads/
        ├── pdf/                    # PDF 缓存 (按需生成后累积)
        └── md/                     # .md 副本 (构建时生成)
```

---

## 5. 数据流

### 5.1 内容发布流程

```
任意设备 git push 到仓库
        │
        ▼
GitHub/Gitee 发送 POST webhook → https://oneweblog.cn/api/rebuild
        │
        ▼
/api/rebuild 验证签名 → 执行 shell:
  1. cd /var/www/oneweblog
  2. git pull origin main
  3. npm ci (仅依赖变更时)
  4. npm run build
  5. PM2 自动检测文件变更 → reload
        │
        ▼
网站已更新
```

### 5.2 页面访问流程 (静态页面)

```
用户访问 /posts/react-notes
        │
        ▼
nginx try_files → dist/posts/react-notes/index.html 存在
        │
        ▼
nginx 直接返回 HTML (不经过 Node.js)
        │
        ▼
浏览器解析:
  - 首屏 HTML/CSS 直接渲染 (零 JS)
  - 有水合标记的组件按需激活 React (SearchBar, ThemeToggle 等)
```

### 5.3 PDF 下载流程

```
用户点击 "下载 PDF" → GET /api/pdf/react-notes
        │
        ▼
nginx 发现 /api/ → proxy_pass 到 Node.js
        │
        ▼
Astro API 端点处理:
  1. 检查 dist/downloads/pdf/react-notes.pdf 是否存在？
  2. 存在 → 302 重定向到 /downloads/pdf/react-notes.pdf
               (nginx 直接 serve 静态文件, 极快)
  3. 不存在 → puppeteer 渲染 /posts/react-notes → 生成 PDF
             → 写入 dist/downloads/pdf/react-notes.pdf
             → 302 重定向
        │
        ▼
后续访问同一 PDF → nginx 静态文件直出, 零 Node.js 参与
```

### 5.4 Markdown 下载流程

```
用户点击 "下载 Markdown" → GET /downloads/md/react-notes.md
        │
        ▼
直接走 nginx 静态文件 (构建时已复制到 public/)
零 Node.js 参与
```

---

## 6. PDF 生成详细设计

### 6.1 按需生成 + 文件缓存

```typescript
// src/pages/api/pdf/[slug].ts

export const prerender = false;  // 关键：标记为 SSR

export async function GET({ params, redirect }) {
  const { slug } = params;
  const pdfPath = `dist/downloads/pdf/${slug}.pdf`;
  const publicPdfPath = `/downloads/pdf/${slug}.pdf`;

  // 缓存命中 → 直接重定向到静态文件
  if (existsSync(pdfPath)) {
    return redirect(publicPdfPath, 302);
  }

  // 验证文章存在
  const post = getCollection('posts').find(p => p.slug === slug);
  if (!post) return new Response('Not Found', { status: 404 });

  // 启动本地浏览器渲染
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(`http://127.0.0.1:4321/posts/${slug}?print=1`, {
    waitUntil: 'networkidle0',
  });

  // 生成 PDF
  await page.pdf({
    path: pdfPath,          // 直接写入 dist/ = 下次就是静态文件
    format: 'A4',
    margin: { top: '20mm', bottom: '20mm', left: '15mm', right: '15mm' },
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: `
      <div style="text-align:center; font-size:10px; width:100%;">
        第 <span class="pageNumber"></span> 页 / 共 <span class="totalPages"></span> 页
      </div>
    `,
  });

  await browser.close();

  return redirect(publicPdfPath, 302);
}
```

### 6.2 打印模式 (避免重复样式)

文章详情页检测 `?print=1` 查询参数时，渲染精简版：

```astro
---
// src/pages/posts/[slug].astro
const { slug } = Astro.params;
const { print } = Astro.url.searchParams;
const post = await getEntry('posts', slug);
---

{print ? (
  <!-- 打印模式：只有正文，无导航/页脚 -->
  <article class="print-content">
    <h1>{post.data.title}</h1>
    <Content />
  </article>
) : (
  <!-- 正常模式：完整布局 -->
  <PostLayout post={post}>
    <Content />
  </PostLayout>
)}
```

### 6.3 资源估算

| 指标 | 数值 |
|------|------|
| Puppeteer 启动内存 | ~80MB (随浏览器实例释放) |
| 单次 PDF 生成耗时 | ~2s |
| 并发 PDF 请求 | 极低 (个人站不会有人同时请求多个 PDF) |
| 缓存命中后延迟 | < 50ms (nginx 静态文件) |

---

## 7. Webhook 自动部署

### 7.1 端点设计

```typescript
// src/pages/api/rebuild.ts

export const prerender = false;

const SECRET = process.env.WEBHOOK_SECRET;

export async function POST({ request }) {
  // 验证签名
  const signature = request.headers.get('x-hub-signature-256');
  const body = await request.text();
  const hmac = createHmac('sha256', SECRET).update(body).digest('hex');

  if (`sha256=${hmac}` !== signature) {
    return new Response('Unauthorized', { status: 401 });
  }

  // 异步执行构建，立即返回 202
  exec('cd /var/www/oneweblog && git pull && npm run build', (err, stdout, stderr) => {
    console.log('[rebuild]', stdout, stderr);
  });

  return new Response('Accepted', { status: 202 });
}
```

### 7.2 GitHub Webhook 配置

- Payload URL: `https://oneweblog.cn/api/rebuild`
- Content type: `application/json`
- Secret: 与服务端 `WEBHOOK_SECRET` 一致
- Events: `Just the push event`

---

## 8. 设计系统

与上一版保持一致，无变化。

### 8.1 配色

```
浅色主题                     暗色主题
──────────────────────      ──────────────────────
背景:   #FFFBF5 (暖白)       背景:   #1A1A2E (深蓝灰)
卡片:   #FFF8ED (奶油)       卡片:   #252540
文字:   #3D3D3D (深灰)       文字:   #D4D4D4
主色:   #D4A574 (暖棕/橙)     主色:   #E0B88A (浅暖橙)
链接:   #B8783A               链接:   #D4A574
代码块: #F5F0E8               代码块: #222238
```

### 8.2 字体

```css
--font-sans:  'Noto Sans SC', 'Inter', system-ui, sans-serif;
--font-mono:  'JetBrains Mono', 'Fira Code', monospace;
--font-serif: 'Noto Serif SC', 'Georgia', serif;
```

### 8.3 布局

桌面端左侧固定导航栏 (240px) + 右侧内容，移动端顶部导航栏 + 汉堡菜单。与上一版设计一致。

---

## 9. 部署方案

### 9.1 服务器资源规划

| 进程 | 内存 | 备注 |
|------|------|------|
| QQ 机器人 | 已有 | 不变 |
| Streamlit | 已有 | 不变 |
| nginx | ~10MB | 新增 |
| Node.js (PM2) | ~120MB 空闲，峰值 ~200MB (PDF 生成时) | 新增 |
| **总增量** | **~130-210MB** | 在 200MB 余量内 |

PM2 配置限制 `max_memory_restart: 256M`，防止 PDF 生成时内存尖峰影响其他服务。

### 9.2 nginx 配置

```nginx
server {
    listen 443 ssl http2;
    server_name oneweblog.cn www.oneweblog.cn;

    ssl_certificate     /etc/ssl/oneweblog/fullchain.pem;
    ssl_certificate_key /etc/ssl/oneweblog/privkey.pem;

    root /var/www/oneweblog/dist/client;

    # 静态资源长缓存
    location /_astro/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # PDF 缓存目录
    location /downloads/ {
        expires 7d;
        add_header Cache-Control "public";
    }

    # API 路由 → Node.js
    location /api/ {
        proxy_pass http://127.0.0.1:4321;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;  # PDF 生成可能较慢
    }

    # 其他请求：先尝试静态文件，找不到走 Node.js (SSR fallback + 404)
    location / {
        try_files $uri $uri/ $uri.html @node;
    }

    location @node {
        proxy_pass http://127.0.0.1:4321;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml application/rss+xml text/markdown;
    gzip_min_length 256;
}

server {
    listen 80;
    server_name oneweblog.cn www.oneweblog.cn;
    return 301 https://$host$request_uri;
}
```

关键点：`try_files $uri $uri/ $uri.html @node` — 静态文件优先，找不到才走 Node.js。API 路由直接走 `proxy_pass`。

### 9.3 PM2 配置

```js
// ecosystem.config.cjs
module.exports = {
  apps: [{
    name: 'self-page',
    script: './dist/server/entry.mjs',
    env: {
      PORT: 4321,
      HOST: '127.0.0.1',
      NODE_ENV: 'production',
      WEBHOOK_SECRET: process.env.WEBHOOK_SECRET,
    },
    max_memory_restart: '256M',
    instances: 1,
    exec_mode: 'fork',
    watch: false,
  }],
};
```

### 9.4 Astro 配置

```js
// astro.config.mjs
import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import react from '@astrojs/react';
import mdx from '@astrojs/mdx';

export default defineConfig({
  output: 'hybrid',
  adapter: node({ mode: 'standalone' }),
  integrations: [react(), mdx()],
  site: 'https://oneweblog.cn',
});
```

`output: 'hybrid'` — 这是关键。所有页面默认 prerender，只有显式声明 `export const prerender = false` 的路由走 SSR。

### 9.5 首次部署步骤

```bash
# 服务器上
cd /var/www
git clone <repo-url> oneweblog
cd oneweblog
npm ci
npm run build
pm2 start ecosystem.config.cjs
pm2 save
sudo nginx -s reload
```

### 9.6 备案

- 页面底部显示 ICP 备案号，链接到 https://beian.miit.gov.cn
- 腾讯云控制台添加备案号白名单

---

## 10. 内容组织

### 10.1 文章 Frontmatter

```yaml
---
title: "React Server Components 学习笔记"
date: 2025-07-01
updated: 2025-07-03
tags: ["react", "前端", "rsc"]
summary: "RSC 的核心概念与实践中遇到的坑"
draft: false
---
```

### 10.2 项目数据

```json
// data/projects.json
[
  {
    "name": "项目名称",
    "description": "一句话简介",
    "url": "https://...",
    "github": "https://github.com/...",
    "tags": ["Python", "LLM"],
    "status": "maintaining"
  }
]
```

### 10.3 文件命名

```
content/posts/
├── 2025-07-01-react-server-components.mdx
├── 2025-07-03-python-asyncio.mdx
└── ...

格式: YYYY-MM-DD-slug.mdx
路由: /posts/slug
```

---

## 11. 开发阶段划分

### 第一阶段：基础框架

- [ ] Astro hybrid 项目初始化 + React + Tailwind
- [ ] BaseLayout + 左侧导航栏
- [ ] 首页 (Hero + 导航卡片 + 文章列表)
- [ ] 暗色主题切换 (localStorage 持久化)
- [ ] 移动端响应式

### 第二阶段：内容系统

- [ ] MDX 内容集合 + Frontmatter schema
- [ ] 文章列表页 (分页 + 标签筛选 + Fuse.js 搜索)
- [ ] 文章详情页 (TOC + Shiki 高亮 + 排版)
- [ ] 项目展示页
- [ ] 标签聚合页
- [ ] RSS Feed + sitemap

### 第三阶段：下载功能

- [ ] PDF 按需生成 API 端点 + 文件缓存
- [ ] 打印模式页面 (精简布局)
- [ ] 构建时 .md 文件复制
- [ ] 下载中心页面
- [ ] 文章页下载链接

### 第四阶段：自动部署

- [ ] Webhook 端点 + 签名验证
- [ ] PM2 配置
- [ ] nginx 配置 + SSL
- [ ] GitHub/Gitee webhook 配置
- [ ] 首次部署验证

### 第五阶段：打磨

- [ ] SEO (og:image, meta, sitemap)
- [ ] 图片懒加载 + WebP
- [ ] 可选：Giscus 评论
- [ ] 可选：GoatCounter 访问统计
- [ ] 备案号挂载

---

## 12. 关键依赖包

```jsonc
{
  "dependencies": {
    "@astrojs/mdx": "^5.x",
    "@astrojs/node": "^9.x",       // SSR 适配器
    "@astrojs/react": "^4.x",
    "@astrojs/rss": "^4.x",
    "@astrojs/sitemap": "^3.x",
    "react": "^19.x",
    "react-dom": "^19.x",
    "puppeteer": "^24.x",          // 服务端按需 PDF 生成
    "astro": "^5.x"
  },
  "devDependencies": {
    "tailwindcss": "^4.x",
    "@tailwindcss/typography": "^0.5.x",
    "lucide-react": "^0.400.x",
    "fuse.js": "^7.x",
    "typescript": "^5.x"
  }
}
```

---

## 13. 三种方案回顾

| | 纯 SSG | Hybrid (选定) | 纯 SSR |
|---|---|---|---|
| 发布方式 | 本地 build + rsync | git push → webhook | git push → webhook |
| 页面性能 | nginx 静态文件 | nginx 静态文件 (99%) | Node.js 渲染 |
| PDF 生成 | build 时全量预生成 | 按需 + 缓存 | 按需 |
| 服务器进程 | 无 | Node.js ~120MB | Node.js ~120MB |
| Build 时间 | 随文章数线性增长 | 恒定 (不含 PDF) | 恒定 |
| 跨设备发布 | 不支持 | 支持 | 支持 |
